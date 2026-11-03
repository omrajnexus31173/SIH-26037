"""Application-wide runtime state, background loops and telemetry broadcast."""
from __future__ import annotations

import asyncio
import base64
import copy
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

import cv2
import numpy as np
import psutil
from fastapi import WebSocket

from backend.camera.manager import CameraHub
from backend.camera.pairing import PairingManager
from backend.camera.webrtc import WebRTCManager
from backend.config import OUTPUTS_DIR, settings
from backend.pipeline import PerceptionPipeline
from backend.simulation.engine import SimulationEngine
from backend.utils import now_iso


class AppState:
    def __init__(self):
        settings.ensure_dirs()
        self.started_at = time.time()
        self.pairing = PairingManager()
        self.pipeline = PerceptionPipeline()
        self.hub = CameraHub(self.pipeline, self.pairing)
        self.engine = SimulationEngine("unmarked_village", settings.sim_fps)
        self.webrtc = WebRTCManager(self.hub, self.pairing)
        self.telemetry_clients: Set[WebSocket] = set()
        self.phone_sockets: Dict[str, WebSocket] = {}
        self._tasks: List[asyncio.Task] = []
        self._started = False
        self.system_cache = self._read_system()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.hub.ensure_worker()
        self.system_cache = self._read_system()
        self._tasks = [
            asyncio.create_task(self._simulation_loop(), name="sih-simulation"),
            asyncio.create_task(self._broadcast_loop(), name="sih-broadcast"),
            asyncio.create_task(self._system_loop(), name="sih-system"),
        ]

    async def stop(self) -> None:
        self._started = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.webrtc.close_all()
        for ws in list(self.telemetry_clients):
            try:
                await ws.close(code=1001)
            except Exception:
                pass
        self.telemetry_clients.clear()
        self.hub.close()

    async def _simulation_loop(self) -> None:
        while self._started:
            tick = 1.0 / max(1.0, settings.sim_fps)
            t0 = time.monotonic()
            self.engine.step(tick)
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.001, tick - elapsed))

    async def _broadcast_loop(self) -> None:
        while self._started:
            interval = 1.0 / max(1.0, settings.broadcast_fps)
            if self.telemetry_clients:
                snapshot = self.telemetry_snapshot()
                await self.broadcast(snapshot)
            await asyncio.sleep(interval)

    async def _system_loop(self) -> None:
        while self._started:
            self.system_cache = self._read_system()
            await asyncio.sleep(1.0)

    # ------------------------------------------------------------------ system
    @staticmethod
    def _read_gpu() -> Dict[str, Any]:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=1.5, text=True).strip()
            if not out:
                raise RuntimeError("empty nvidia-smi output")
            parts = [p.strip() for p in out.splitlines()[0].split(",")]
            return {"available": True, "utilization_percent": float(parts[0]),
                    "memory_used_mb": float(parts[1]), "memory_total_mb": float(parts[2]),
                    "name": parts[3] if len(parts) > 3 else "NVIDIA GPU"}
        except Exception:
            return {"available": False, "utilization_percent": None,
                    "memory_used_mb": None, "memory_total_mb": None,
                    "message": "No NVIDIA GPU utilization available (nvidia-smi not found or no compatible GPU)."}

    def _read_system(self) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        return {
            "timestamp": now_iso(),
            "uptime_s": round(time.time() - self.started_at, 1),
            "cpu_percent": round(float(psutil.cpu_percent(interval=None)), 1),
            "ram_percent": round(float(vm.percent), 1),
            "ram_used_gb": round(float(vm.used) / (1024 ** 3), 2),
            "ram_total_gb": round(float(vm.total) / (1024 ** 3), 2),
            "gpu": self._read_gpu(),
            "backend_status": "online",
            "simulation_status": self.engine.state()["status"],
            "camera_status": self.hub.status()["source_type"],
            "websocket_clients": len(self.telemetry_clients),
            "https_enabled": settings.use_https,
            "https_note": ("Browsers allow camera access only in a secure context: HTTPS with a trusted certificate, "
                           "or http://localhost on the same machine. A plain http://192.168.x.x LAN page will NOT work."),
        }

    def system_status(self) -> Dict[str, Any]:
        return {**self.system_cache, "models": self.pipeline.status(),
                "websocket_clients": len(self.telemetry_clients)}

    # ------------------------------------------------------------------ config
    def config(self) -> Dict[str, Any]:
        return {
            "detector_backend": self.pipeline.detector_backend,
            "confidence_threshold": settings.conf_threshold,
            "ai_fps": self.hub.ai_fps,
            "camera_fps": self.hub.camera_fps,
            "sim_fps": settings.sim_fps,
            "broadcast_fps": settings.broadcast_fps,
            "simulation_quality": self.engine.quality,
            "simulation_difficulty": self.engine.difficulty,
            "overlays": dict(self.pipeline.overlay_config),
            "use_cuda": settings.use_cuda,
            "https_enabled": settings.use_https,
            "pairing_ttl_seconds": settings.pairing_ttl_seconds,
        }

    def apply_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "detector_backend" in payload:
            self.pipeline.set_detector_backend(str(payload["detector_backend"]))
        if "confidence_threshold" in payload:
            self.pipeline.set_confidence(float(payload["confidence_threshold"]))
        if "ai_fps" in payload:
            self.hub.set_ai_fps(float(payload["ai_fps"]))
        if "camera_fps" in payload:
            self.hub.camera_fps = max(1.0, min(30.0, float(payload["camera_fps"])))
        if "sim_fps" in payload:
            settings.sim_fps = max(5.0, min(60.0, float(payload["sim_fps"])))
            self.engine.sim_fps = settings.sim_fps
        if "broadcast_fps" in payload:
            settings.broadcast_fps = max(1.0, min(20.0, float(payload["broadcast_fps"])))
        if "simulation_quality" in payload:
            self.engine.set_quality(str(payload["simulation_quality"]))
        if "simulation_difficulty" in payload or "difficulty" in payload:
            value = payload.get("simulation_difficulty", payload.get("difficulty", ""))
            self.engine.set_difficulty(str(value))
        if "overlays" in payload and isinstance(payload["overlays"], dict):
            self.pipeline.set_overlays(payload["overlays"])
        return self.config()

    # ------------------------------------------------------------------ telemetry
    @staticmethod
    def _compact_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(plan)
        p.pop("grid_cost_downsample", None)
        return p

    @staticmethod
    def _compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
        m = dict(metrics)
        m["history"] = list(m.get("history", []))[-60:]
        m["events"] = list(m.get("events", []))[-12:]
        return m

    def telemetry_snapshot(self) -> Dict[str, Any]:
        sim = copy.deepcopy(self.engine.state())
        sim["plan"] = self._compact_plan(sim.get("plan", {}))
        sim["metrics"] = self._compact_metrics(sim.get("metrics", {}))
        perception = copy.deepcopy(self.hub.latest_result)
        if "plan" in perception:
            perception["plan"] = self._compact_plan(perception["plan"])
        perception.pop("model_status", None)
        evaluation = self.engine.evaluation_report()
        evaluation["history"] = evaluation.get("history", [])[-60:]
        evaluation["events"] = evaluation.get("events", [])[-12:]
        return {
            "type": "telemetry",
            "timestamp": now_iso(),
            "simulation": sim,
            "camera": self.hub.status(),
            "perception": perception,
            "system": self.system_status(),
            "pairing": self.pairing.status(),
            "evaluation": evaluation,
            "config": self.config(),
        }

    async def broadcast(self, message: Dict[str, Any]) -> None:
        if not self.telemetry_clients:
            return
        sockets = list(self.telemetry_clients)
        results = await asyncio.gather(
            *[ws.send_json(message) for ws in sockets], return_exceptions=True)
        for ws, result in zip(sockets, results):
            if isinstance(result, Exception):
                self.telemetry_clients.discard(ws)

    async def add_telemetry_client(self, ws: WebSocket) -> None:
        await ws.accept()
        self.telemetry_clients.add(ws)
        await ws.send_json(self.telemetry_snapshot())

    def remove_telemetry_client(self, ws: WebSocket) -> None:
        self.telemetry_clients.discard(ws)

    # ------------------------------------------------------------------ phone websocket
    def register_phone_socket(self, token: str, ws: WebSocket, peer_id: Optional[str],
                              transport: str) -> Optional[Any]:
        session = self.pairing.validate(token, peer_id=peer_id, bind=True)
        if not session:
            return None
        old = self.phone_sockets.get(token)
        self.phone_sockets[token] = ws
        return old

    def unregister_phone_socket(self, token: str, ws: WebSocket) -> None:
        if self.phone_sockets.get(token) is ws:
            self.phone_sockets.pop(token, None)
            self.pairing.disconnect()

    async def handle_phone_message(self, token: str, ws: WebSocket,
                                   data: Dict[str, Any]) -> None:
        kind = str(data.get("type", ""))
        if not self.pairing.validate(token):
            await ws.send_json({"type": "error", "message": "Pairing token expired or revoked"})
            await ws.close(code=4401)
            return
        if kind == "hello":
            self.pairing.mark_connected(
                token, str(data.get("transport", "mjpeg_websocket")),
                str(data.get("facing", "environment")),
                data.get("width"), data.get("height"))
            self.hub.select("phone", {"token": token, "transport": data.get("transport", "mjpeg_websocket")})
            await ws.send_json({"type": "hello_ack", "server_time": time.time(),
                                "token_valid": True, "message": "Pairing accepted"})
            return
        if kind == "ping":
            await ws.send_json({"type": "pong", "client_time": data.get("client_time"),
                                "server_time": time.time()})
            return
        if kind == "latency":
            rtt = float(data.get("rtt_ms", 0))
            self.hub.set_phone_latency(token, rtt)
            return
        if kind == "status":
            if data.get("fps") is not None:
                self.pairing.mark_frame(token, int(data.get("width") or 0),
                                        int(data.get("height") or 0),
                                        fps=float(data["fps"]))
            if data.get("error"):
                self.pairing.set_error(token, str(data["error"]))
            return
        if kind == "frame":
            raw = str(data.get("jpeg", ""))
            if "," in raw and raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            if not raw or len(raw) > 3_000_000:
                await ws.send_json({"type": "error", "message": "Frame missing or too large"})
                return
            try:
                binary = base64.b64decode(raw, validate=False)
                arr = np.frombuffer(binary, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("invalid JPEG")
                sent_at = float(data.get("sent_at", 0)) or None
                await asyncio.to_thread(self.hub.ingest_phone_frame, frame, token,
                                        "mjpeg_websocket", sent_at)
                await ws.send_json({"type": "frame_ack", "sent_at": sent_at,
                                    "server_recv_at": time.time(),
                                    "frames_received": self.pairing.status()["frames_received"]})
            except Exception as exc:
                await ws.send_json({"type": "error", "message": f"Frame decode failed: {exc}"})
            return
        if kind == "disconnect":
            await ws.send_json({"type": "disconnected", "message": "Phone disconnected"})
            self.pairing.disconnect()
            await ws.close(code=1000)
            return
        await ws.send_json({"type": "error", "message": f"Unknown message type: {kind}"})

    async def close_phone_connections(self, token: Optional[str] = None,
                                      revoke: bool = False) -> None:
        targets = [token] if token else list(self.phone_sockets.keys())
        for tok in targets:
            ws = self.phone_sockets.pop(tok, None)
            if ws:
                try:
                    await ws.send_json({"type": "disconnected", "message": "Disconnected by dashboard"})
                    await ws.close(code=4400)
                except Exception:
                    pass
            await self.webrtc.close_token(tok)
        if not token:
            await self.webrtc.close_all()
        if revoke:
            self.pairing.revoke()
        else:
            self.pairing.disconnect()
        if self.hub.source_type == "phone":
            self.hub.select("none")


app_state = AppState()
