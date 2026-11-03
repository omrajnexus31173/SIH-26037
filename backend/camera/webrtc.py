"""Server-side WebRTC receiver for the paired Android phone camera.

The phone gathers a complete SDP offer and posts it with its pairing token.
aiortc creates an answer; incoming video frames are decoded to BGR and passed
to the same perception pipeline as every other camera source. If aiortc is not
installed, the /pair page automatically uses the authenticated MJPEG WebSocket
fallback instead.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

try:
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import MediaStreamError
    AIORTC_AVAILABLE = True
    AIORTC_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on optional install
    AIORTC_AVAILABLE = False
    AIORTC_ERROR = str(exc)
    RTCConfiguration = None  # type: ignore
    RTCPeerConnection = None  # type: ignore
    RTCSessionDescription = None  # type: ignore
    MediaStreamError = Exception  # type: ignore

from .manager import CameraHub
from .pairing import PairingManager


class WebRTCManager:
    def __init__(self, hub: CameraHub, pairing: PairingManager):
        self.hub = hub
        self.pairing = pairing
        self.connections: Dict[str, List[Any]] = {}
        self.tasks: set = set()
        self.last_error = ""

    @staticmethod
    def status() -> Dict[str, Any]:
        return {
            "available": AIORTC_AVAILABLE,
            "library": "aiortc" if AIORTC_AVAILABLE else None,
            "message": AIORTC_ERROR or "WebRTC receiver ready",
            "transport": "recvonly video; non-trickle ICE with empty ICE server list for LAN",
        }

    async def _wait_for_ice(self, pc, timeout: float = 8.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if getattr(pc, "iceGatheringState", "complete") == "complete":
                return True
            await asyncio.sleep(0.05)
        return False

    async def create_answer(self, offer: Dict[str, Any]) -> Dict[str, Any]:
        token = str(offer.get("token", ""))
        peer_id = str(offer.get("peer_id", "")) or None
        sdp = str(offer.get("sdp", ""))
        sdp_type = str(offer.get("type", "offer"))
        if not AIORTC_AVAILABLE:
            return {"error": f"WebRTC backend unavailable: {AIORTC_ERROR}",
                    "fallback": "mjpeg_websocket", "available": False}
        session = self.pairing.validate(token, peer_id=peer_id, bind=True)
        if not session:
            return {"error": "Invalid, expired, revoked or already-bound pairing token",
                    "fallback": "regenerate_token", "available": False}
        if sdp_type != "offer" or "v=0" not in sdp:
            return {"error": "A complete SDP offer is required", "available": False}
        try:
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            self.connections.setdefault(token, []).append(pc)
            self.hub.select("phone", {"token": token, "transport": "webrtc"})
            self.pairing.mark_connected(
                token, "webrtc",
                facing=str(offer.get("facing", "environment")),
                width=offer.get("width"), height=offer.get("height"))

            @pc.on("track")
            async def on_track(track):
                if track.kind == "video":
                    task = asyncio.create_task(self._consume_track(track, token))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                state = pc.connectionState
                if state in {"failed", "closed"}:
                    await self.close_token(token)
                elif state == "connected":
                    self.pairing.mark_connected(token, "webrtc")

            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=sdp_type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            gathered = await self._wait_for_ice(pc)
            local = pc.localDescription
            return {
                "sdp": local.sdp,
                "type": local.type,
                "ice_gathering_complete": gathered,
                "transport": "webrtc",
                "available": True,
                "message": "WebRTC answer created. The phone page falls back to MJPEG if ICE fails." if not gathered else "WebRTC answer created.",
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.pairing.set_error(token, str(exc))
            await self.close_token(token)
            return {"error": f"Could not create WebRTC answer: {exc}",
                    "fallback": "mjpeg_websocket", "available": False}

    async def _consume_track(self, track, token: str) -> None:
        try:
            while True:
                frame = await track.recv()
                if not self.pairing.validate(token):
                    break
                image = frame.to_ndarray(format="bgr24")
                await asyncio.to_thread(self.hub.ingest_phone_frame,
                                        image, token, "webrtc", None)
        except (MediaStreamError, asyncio.CancelledError):
            pass
        except Exception as exc:
            self.last_error = str(exc)
            self.pairing.set_error(token, f"WebRTC track error: {exc}")

    async def close_token(self, token: str) -> None:
        pcs = self.connections.pop(token, [])
        for pc in pcs:
            try:
                await pc.close()
            except Exception:
                pass
        self.pairing.disconnect()

    async def close_all(self) -> None:
        for token in list(self.connections):
            await self.close_token(token)
        for task in list(self.tasks):
            task.cancel()
