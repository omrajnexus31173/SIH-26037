"""Central configuration for SIH-26037.

All paths are relative to the project root so the app works from a ZIP extraction
on Windows or from the development workspace on Linux.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
MODELS_DIR = ROOT / "models"
ASSETS_DIR = ROOT / "assets"
OUTPUTS_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def local_ipv4_addresses() -> List[str]:
    """Best-effort list of private IPv4 addresses, without requiring Internet."""
    found: List[str] = []
    try:
        import psutil

        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                ip = addr.address
                if addr.family == socket.AF_INET and ip and not ip.startswith("127."):
                    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                        if ip not in found:
                            found.append(ip)
    except Exception:
        pass
    if not found:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                found.append(ip)
        except Exception:
            pass
    if not found:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            if ip and not ip.startswith("127."):
                found.append(ip)
        except Exception:
            pass
    return found


def primary_lan_ip() -> str:
    ips = local_ipv4_addresses()
    return ips[0] if ips else "127.0.0.1"


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("SIH_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SIH_BACKEND_PORT") or os.getenv("PORT") or "8000"))
    frontend_port: int = field(default_factory=lambda: int(os.getenv("SIH_FRONTEND_PORT", "5173")))
    use_https: bool = field(default_factory=lambda: _env_bool("SIH_USE_HTTPS", False))
    ssl_cert: Path = field(default_factory=lambda: ROOT / "certs" / "sih-26037.crt")
    ssl_key: Path = field(default_factory=lambda: ROOT / "certs" / "sih-26037.key")

    ai_fps: float = field(default_factory=lambda: float(os.getenv("SIH_AI_FPS", "8")))
    camera_fps: float = field(default_factory=lambda: float(os.getenv("SIH_CAMERA_FPS", "20")))
    sim_fps: float = field(default_factory=lambda: float(os.getenv("SIH_SIM_FPS", "20")))
    broadcast_fps: float = field(default_factory=lambda: float(os.getenv("SIH_BROADCAST_FPS", "8")))
    pairing_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("SIH_PAIRING_TTL", "900")))

    yolo_model: Path = field(default_factory=lambda: MODELS_DIR / os.getenv("SIH_YOLO_MODEL", "yolov8n.onnx"))
    segmentation_model: Path = field(default_factory=lambda: MODELS_DIR / os.getenv("SIH_SEG_MODEL", "twinlitenet_da.onnx"))
    detector_backend: str = field(default_factory=lambda: os.getenv("SIH_DETECTOR", "opencv_onnx"))
    conf_threshold: float = field(default_factory=lambda: float(os.getenv("SIH_CONF", "0.35")))
    iou_threshold: float = field(default_factory=lambda: float(os.getenv("SIH_IOU", "0.45")))
    use_cuda: bool = field(default_factory=lambda: _env_bool("SIH_USE_CUDA", False))

    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("SIH_MAX_UPLOAD_MB", "200")))
    public_pair_base_url: str = field(default_factory=lambda: os.getenv("SIH_PUBLIC_PAIR_BASE_URL", ""))
    model_dir: Path = MODELS_DIR
    assets_dir: Path = ASSETS_DIR
    outputs_dir: Path = OUTPUTS_DIR
    docs_dir: Path = DOCS_DIR

    def ensure_dirs(self) -> None:
        for d in (MODELS_DIR, ASSETS_DIR, OUTPUTS_DIR, DOCS_DIR, ROOT / "config", ROOT / "certs", ROOT / "uploads"):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
