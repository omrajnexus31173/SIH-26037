"""Expiring, single-peer camera pairing tokens and pairing URL discovery.

Security properties:
  - Token is random, short-lived, and regenerating it revokes the previous one.
  - Every WebRTC offer and every camera frame requires a valid token.
  - The first peer to connect is bound to the token; later peers are rejected.
  - No endpoint accepts an arbitrary camera stream without such a token.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.config import local_ipv4_addresses, primary_lan_ip, settings
from backend.utils import now_iso


@dataclass
class PairingSession:
    token: str
    created_at: float
    expires_at: float
    created_iso: str = field(default_factory=now_iso)
    revoked: bool = False
    peer_id: Optional[str] = None
    connected: bool = False
    transport: str = "none"
    facing: str = "environment"
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    latency_ms: Optional[float] = None
    last_seen: Optional[float] = None
    frames_received: int = 0
    error: str = ""


class PairingManager:
    def __init__(self, ttl_seconds: Optional[int] = None):
        self.ttl_seconds = int(ttl_seconds or settings.pairing_ttl_seconds)
        self._lock = threading.RLock()
        self.session: Optional[PairingSession] = None

    def create(self) -> PairingSession:
        with self._lock:
            if self.session:
                self.session.revoked = True
            self.session = PairingSession(
                token=secrets.token_urlsafe(24),
                created_at=time.time(),
                expires_at=time.time() + self.ttl_seconds,
            )
            return self.session

    @property
    def current(self) -> PairingSession:
        with self._lock:
            if self.session is None or self.session.revoked or self.session.expires_at <= time.time():
                return self.create()
            return self.session

    def validate(self, token: str, peer_id: Optional[str] = None,
                 bind: bool = False) -> Optional[PairingSession]:
        with self._lock:
            s = self.session
            if not s or s.revoked or s.token != token or s.expires_at <= time.time():
                return None
            if peer_id:
                if s.peer_id is None and bind:
                    s.peer_id = peer_id
                elif s.peer_id and s.peer_id != peer_id:
                    return None
            return s

    def mark_connected(self, token: str, transport: str, facing: str = "environment",
                       width: Optional[int] = None, height: Optional[int] = None) -> bool:
        with self._lock:
            s = self.validate(token)
            if not s:
                return False
            s.connected = True
            s.transport = transport
            s.facing = facing
            s.width = width or s.width
            s.height = height or s.height
            s.last_seen = time.time()
            return True

    def mark_frame(self, token: str, width: int, height: int,
                   transport: Optional[str] = None, fps: Optional[float] = None,
                   latency_ms: Optional[float] = None) -> bool:
        with self._lock:
            s = self.validate(token)
            if not s:
                return False
            s.frames_received += 1
            s.width, s.height = int(width), int(height)
            s.last_seen = time.time()
            s.connected = True
            if transport:
                s.transport = transport
            if fps is not None:
                s.fps = float(fps)
            if latency_ms is not None:
                s.latency_ms = float(latency_ms)
            return True

    def set_latency(self, token: str, latency_ms: float) -> None:
        with self._lock:
            s = self.validate(token)
            if s:
                s.latency_ms = max(0.0, float(latency_ms))
                s.last_seen = time.time()

    def set_error(self, token: str, error: str) -> None:
        with self._lock:
            s = self.validate(token)
            if s:
                s.error = str(error)[:300]

    def disconnect(self) -> None:
        with self._lock:
            s = self.session
            if s:
                s.connected = False
                s.transport = "none"
                s.fps = None
                s.latency_ms = None
                s.error = ""

    def revoke(self) -> None:
        with self._lock:
            if self.session:
                self.session.revoked = True
                self.session.connected = False

    def status(self) -> Dict[str, Any]:
        with self._lock:
            s = self.session
            if not s:
                return {"active": False, "token": None, "expires_in_s": 0}
            remaining = max(0, int(s.expires_at - time.time()))
            return {
                "active": not s.revoked and remaining > 0,
                "token": s.token if not s.revoked and remaining > 0 else None,
                "created_at": s.created_iso,
                "expires_in_s": remaining,
                "revoked": s.revoked,
                "connected": s.connected,
                "transport": s.transport,
                "facing": s.facing,
                "fps": None if s.fps is None else round(s.fps, 2),
                "resolution": [s.width, s.height] if s.width and s.height else None,
                "latency_ms": None if s.latency_ms is None else round(s.latency_ms, 1),
                "frames_received": s.frames_received,
                "last_seen": s.last_seen,
                "peer_bound": bool(s.peer_id),
                "error": s.error,
                "ttl_seconds": self.ttl_seconds,
                "security": "expiring single-peer token; required for all phone frame ingestion",
            }

    def pairing_urls(self, token: str, request_host: Optional[str] = None,
                     request_scheme: Optional[str] = None,
                     frontend_origin: Optional[str] = None) -> List[Dict[str, str]]:
        """Return candidate origins. The dashboard lets the operator choose the one that is actually reachable."""
        urls: List[Dict[str, str]] = []

        def add(url: str, label: str, note: str) -> None:
            url = url.rstrip("/")
            if url not in [u["base_url"] for u in urls]:
                urls.append({"base_url": url, "label": label, "note": note,
                             "pair_url": f"{url}/pair?token={token}"})

        if frontend_origin:
            add(frontend_origin, "Dashboard origin", "Recommended when the dashboard itself is reachable from the phone.")
        if settings.public_pair_base_url:
            add(settings.public_pair_base_url, "Configured public URL", "From SIH_PUBLIC_PAIR_BASE_URL.")
        lan = primary_lan_ip()
        scheme = "https" if settings.use_https else "http"
        add(f"{scheme}://{lan}:{settings.frontend_port}", "Local network",
            "Use when phone and laptop are on the same Wi-Fi. HTTPS is required for camera access on a LAN IP.")
        if request_host and request_host not in {"localhost", "127.0.0.1"}:
            host = request_host.split(",")[0].strip()
            proto = request_scheme or ("https" if settings.use_https else "http")
            add(f"{proto}://{host}", "Current request host", "Useful behind a reverse proxy or Arena preview.")
        for ip in local_ipv4_addresses():
            add(f"{scheme}://{ip}:{settings.frontend_port}", f"LAN {ip}", "Additional detected network interface.")
        add(f"http://localhost:{settings.frontend_port}", "This laptop only",
            "localhost is a browser secure context; useful for laptop webcam testing, not a separate phone.")
        return urls
