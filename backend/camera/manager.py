"""Camera source management and real frame processing.

Supported sources:
  phone  - tokenised WebRTC or MJPEG-over-WebSocket frames from /pair
  usb    - a real UVC device index, or an ADB-reverse/IP-Webcam URL
  ip     - HTTP/RTSP camera stream
  webcam - laptop camera through OpenCV
  video  - uploaded video or bundled demo clip
  synthetic - clearly-labelled generated test frames (NOT a camera)
"""
from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np

from backend.config import ROOT, settings
from backend.pipeline import FRAME_HEIGHT, FRAME_WIDTH, PerceptionPipeline
from backend.utils import now_iso

from .pairing import PairingManager
from .windows_devices import enumerate_windows_camera_devices

SOURCE_CATALOG: List[Dict[str, Any]] = [
    {"id": "phone", "label": "Phone Camera via QR / Wi-Fi", "icon": "qr",
     "description": "Scan the dashboard QR code. Uses WebRTC with an authenticated MJPEG-over-WebSocket fallback."},
    {"id": "usb", "label": "Phone Camera via USB", "icon": "usb",
     "description": "Use a real UVC camera device index, or ADB reverse + IP Webcam over a USB tether. Ordinary MTP file transfer does NOT create a camera stream."},
    {"id": "ip", "label": "IP Webcam", "icon": "wifi",
     "description": "HTTP/MJPEG or RTSP stream URL, e.g. http://PHONE_IP:8080/video."},
    {"id": "webcam", "label": "Laptop Webcam", "icon": "camera",
     "description": "OpenCV VideoCapture device, normally index 0."},
    {"id": "video", "label": "Video Upload / Demo Clip", "icon": "video",
     "description": "Process an uploaded recording or the bundled sample-derived demo clip."},
    {"id": "synthetic", "label": "Synthetic Test Pattern", "icon": "grid",
     "description": "Generated frames for automated tests. Explicitly labelled as NOT a real camera."},
    {"id": "none", "label": "Disconnect", "icon": "stop", "description": "Stop all camera input."},
]

USB_GUIDE = {
    "title": "Android phone as a camera over USB — reliable options",
    "important": "Standard USB file transfer (MTP/PTP) does not expose a camera stream. A phone is not automatically a UVC webcam.",
    "options": [
        {
            "id": "adb_ip_webcam",
            "name": "Recommended: USB tether + ADB reverse + IP Webcam",
            "steps": [
                "Install an IP Webcam / camera-streaming app on the Android phone and Platform ADB tools on Windows.",
                "Enable USB debugging, connect by USB, and accept the RSA prompt.",
                "Run: adb reverse tcp:8080 tcp:8080",
                "Start the phone app's camera server on port 8080.",
                "In the dashboard choose 'Phone Camera via USB', mode 'ADB reverse IP webcam', URL http://127.0.0.1:8080/video, then Verify.",
            ],
            "verification": "The backend opens the URL with OpenCV; a live preview and real YOLO boxes confirm success.",
        },
        {
            "id": "uvc",
            "name": "Direct UVC camera (device dependent)",
            "steps": [
                "Only works if Android exposes a USB webcam/UVC gadget, or with an external USB webcam.",
                "Select the detected OpenCV device index and click Connect.",
                "Windows Device Manager should list the device under Cameras or Imaging devices.",
            ],
            "verification": "The devices endpoint reports available indices and the preview shows frames.",
        },
        {
            "id": "adb_forward_wifi",
            "name": "Alternative: ADB over USB with Wi-Fi pairing page",
            "steps": [
                "Use adb reverse to expose the HTTPS frontend port to the phone, then open the QR pairing URL on the phone.",
                "The phone browser uses WebRTC over the USB network tunnel; no MTP camera assumption is made.",
            ],
            "verification": "Phone status changes to connected and WebRTC/MJPEG frames appear on the laptop.",
        },
    ],
    "software": ["Android Platform Tools (adb)", "IP Webcam-style app or a UVC-capable camera", "OpenCV (installed by setup_windows.bat)"],
    "disconnect": "Click Disconnect in Camera Controls, stop the phone camera server, and optionally run adb reverse --remove-all.",
}


class FrameSource:
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        return False, None

    def close(self) -> None:
        pass


class OpenCVCaptureSource(FrameSource):
    def __init__(self, target, loop: bool = False, backend: Optional[int] = None):
        self.target = target
        self.loop = bool(loop)
        self.cap = cv2.VideoCapture(target, backend) if backend is not None else cv2.VideoCapture(target)
        self.opened = bool(self.cap.isOpened())
        self.error = "" if self.opened else f"OpenCV could not open {target!r}"
        if self.opened:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.opened:
            return False, None
        ok, frame = self.cap.read()
        if not ok and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return ok, frame if ok else None

    def close(self) -> None:
        try:
            self.cap.release()
        except Exception:
            pass


class SyntheticSource(FrameSource):
    """Generated test pattern. Never represented as a real camera."""

    def __init__(self):
        self.t = 0.0

    def read(self) -> Tuple[bool, np.ndarray]:
        self.t += 1.0 / max(1.0, settings.camera_fps)
        img = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        img[:] = (28, 32, 38)
        cv2.rectangle(img, (0, 220), (FRAME_WIDTH, FRAME_HEIGHT), (48, 52, 58), -1)
        cv2.line(img, (150, FRAME_HEIGHT), (285, 220), (90, 100, 110), 2)
        cv2.line(img, (490, FRAME_HEIGHT), (355, 220), (90, 100, 110), 2)
        x = int(260 + 90 * np.sin(self.t * 0.7))
        cv2.rectangle(img, (x, 250), (x + 80, 315), (40, 90, 210), -1)
        cv2.putText(img, "SYNTHETIC TEST PATTERN - NOT A REAL CAMERA", (22, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (60, 200, 240), 2, cv2.LINE_AA)
        cv2.putText(img, f"t={self.t:.1f}s", (22, 66), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (180, 200, 220), 1, cv2.LINE_AA)
        return True, img


class CameraHub:
    def __init__(self, pipeline: PerceptionPipeline, pairing: PairingManager):
        self.pipeline = pipeline
        self.pairing = pairing
        self._lock = threading.RLock()
        self._ai_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_stop = threading.Event()
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._pending_process = False
        self._thread: Optional[threading.Thread] = None
        self._worker_thread = threading.Thread(target=self._processing_loop,
                                               name="sih-ai-worker", daemon=True)
        self._worker_thread.start()
        self._source: Optional[FrameSource] = None
        self.source_type = "none"
        self.source_config: Dict[str, Any] = {}
        self.latest_raw: Optional[np.ndarray] = None
        self.latest_annotated: Optional[np.ndarray] = None
        self.latest_result: Dict[str, Any] = pipeline.empty_result("No camera source selected")
        self.error = ""
        self.last_frame_at: Optional[float] = None
        self.last_processed_at: Optional[float] = None
        self.frame_count = 0
        self.processed_count = 0
        self.fps = 0.0
        self.processed_fps = 0.0
        self.resolution: List[int] = [0, 0]
        self.latency_ms: Optional[float] = None
        self.clock_skew_one_way_ms: Optional[float] = None
        self.transport = "none"
        self.ai_fps = settings.ai_fps
        self.camera_fps = settings.camera_fps

    @staticmethod
    def catalog() -> List[Dict[str, Any]]:
        return SOURCE_CATALOG

    def _stop_current(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        if self._source:
            self._source.close()
        self._source = None
        self._thread = None
        self._stop_event = threading.Event()
        # Drop stale frames from the previous source.
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._pending_process = False

    def select(self, source_type: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = dict(config or {})
        source_type = str(source_type)
        if source_type not in {s["id"] for s in SOURCE_CATALOG}:
            raise ValueError(f"Unknown camera source: {source_type}")
        self._stop_current()
        with self._lock:
            self.source_type = source_type
            self.source_config = config
            self.error = ""
            self.transport = "none"
            self.latest_raw = None
            self.latest_annotated = None
            self.latest_result = self.pipeline.empty_result("Waiting for camera frames")
            self.last_frame_at = None
            self.last_processed_at = None
            self.fps = 0.0
            self.processed_fps = 0.0
            self.latency_ms = None
            self.clock_skew_one_way_ms = None
            self.resolution = [0, 0]
            # Counters are per selected source; never carry stale frame totals
            # into a newly selected source's status.
            self.frame_count = 0
            self.processed_count = 0
        self.pipeline.reset_tracking()
        if source_type == "none":
            return self.status()
        if source_type == "phone":
            with self._lock:
                self.transport = "awaiting_phone"
            return self.status()
        if source_type == "synthetic":
            self._source = SyntheticSource()
        elif source_type in {"webcam", "usb", "ip", "video"}:
            self._source = self._build_cv_source(source_type, config)
            if self._source and getattr(self._source, "error", ""):
                with self._lock:
                    self.error = self._source.error
                return self.status()
        self._thread = threading.Thread(target=self._capture_loop, args=(self._source,),
                                        name="sih-camera-capture", daemon=True)
        self._thread.start()
        return self.status()

    def _build_cv_source(self, source_type: str, config: Dict[str, Any]) -> OpenCVCaptureSource:
        backend = None
        if os.name == "nt" and config.get("dshow", True) and source_type in {"webcam", "usb"}:
            backend = cv2.CAP_DSHOW
        if source_type == "usb" and config.get("mode") == "adb_ip":
            url = str(config.get("url", "http://127.0.0.1:8080/video"))
            self._validate_url(url)
            return OpenCVCaptureSource(url, loop=False)
        if source_type == "ip":
            url = str(config.get("url", "")).strip()
            self._validate_url(url)
            return OpenCVCaptureSource(url, loop=False)
        if source_type == "video":
            raw = str(config.get("path") or (settings.assets_dir / "demo_drive.avi"))
            path = Path(raw)
            if not path.is_absolute():
                path = ROOT / path
            allowed = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}
            if path.suffix.lower() not in allowed or not path.exists():
                raise ValueError(f"Video file not found or unsupported: {path}")
            return OpenCVCaptureSource(str(path), loop=True)
        index = int(config.get("device_index", 0))
        return OpenCVCaptureSource(index, loop=False, backend=backend)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https", "rtsp"} or not parsed.netloc:
            raise ValueError("Camera URL must be an http(s) or rtsp URL")

    def _capture_loop(self, source: Optional[FrameSource]) -> None:
        if source is None:
            return
        interval = 1.0 / max(1.0, self.camera_fps)
        while not self._stop_event.is_set():
            try:
                ok, frame = source.read()
                if ok and frame is not None:
                    self._ingest(frame, transport=self.source_type)
                else:
                    with self._lock:
                        self.error = getattr(source, "error", "") or "No frame returned by camera source"
            except Exception as exc:
                with self._lock:
                    self.error = f"Capture error: {exc}"
            self._stop_event.wait(interval)

    def _ingest(self, frame: np.ndarray, transport: str = "camera",
                token: Optional[str] = None, sent_at: Optional[float] = None,
                forced: bool = False) -> None:
        if frame is None or frame.size == 0:
            return
        now = time.time()
        h, w = frame.shape[:2]
        with self._lock:
            self.latest_raw = frame.copy()
            self.resolution = [int(w), int(h)]
            self.frame_count += 1
            self.transport = transport
            if self.source_type == "phone":
                self.error = ""
            if self.last_frame_at:
                inst = 1.0 / max(1e-3, now - self.last_frame_at)
                self.fps = inst if self.fps == 0 else 0.85 * self.fps + 0.15 * inst
            self.last_frame_at = now
            if sent_at:
                # Device clocks can differ; this is an approximate one-way value.
                self.clock_skew_one_way_ms = max(0.0, (now - float(sent_at)) * 1000.0)
        if token:
            self.pairing.mark_frame(token, w, h, transport=transport, fps=self.fps)
        min_interval = 1.0 / max(0.5, self.ai_fps)
        with self._lock:
            should_enqueue = (forced or not self._pending_process) and (
                self.last_processed_at is None or now - self.last_processed_at >= min_interval)
            if self.latest_annotated is None:
                self.latest_annotated = frame.copy()
        if should_enqueue:
            item = (frame.copy(), self.source_type, token, sent_at, now)
            # Keep only the newest pending frame: low latency matters more than
            # processing every captured frame on a CPU-only laptop.
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._frame_queue.put_nowait(item)
                with self._lock:
                    self._pending_process = True
            except queue.Full:
                pass

    def _processing_loop(self) -> None:
        """Background AI worker so camera capture/preview FPS is not blocked by YOLO."""
        while not self._worker_stop.is_set():
            try:
                frame, source_type, token, sent_at, enqueued_at = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if source_type != self.source_type:
                    continue
                with self._lock:
                    fps, ai_fps = self.fps, self.processed_fps
                self.pipeline.set_runtime_stats(fps, ai_fps)
                with self._ai_lock:
                    result = self.pipeline.process_frame(frame, source_type=source_type,
                                                         timestamp=enqueued_at)
                now = time.time()
                with self._lock:
                    if source_type == self.source_type:
                        self.latest_annotated = result.annotated
                        self.latest_result = result.data
                        self.processed_count += 1
                        if self.last_processed_at:
                            inst = 1.0 / max(1e-3, now - self.last_processed_at)
                            self.processed_fps = (inst if self.processed_fps == 0 else
                                                  0.8 * self.processed_fps + 0.2 * inst)
                        self.last_processed_at = now
                        self.error = ""
            except Exception as exc:
                with self._lock:
                    self.error = f"AI pipeline error: {exc}"
            finally:
                with self._lock:
                    self._pending_process = False

    def ingest_phone_frame(self, frame: np.ndarray, token: str, transport: str,
                           sent_at: Optional[float] = None) -> bool:
        if not self.pairing.validate(token):
            return False
        if self.source_type != "phone":
            self.select("phone", {"token": token, "transport": transport})
        self._ingest(frame, transport=transport, token=token, sent_at=sent_at)
        return True

    def set_phone_latency(self, token: str, rtt_ms: float) -> bool:
        if not self.pairing.validate(token):
            return False
        self.pairing.set_latency(token, float(rtt_ms))
        with self._lock:
            self.latency_ms = max(0.0, float(rtt_ms))
        return True

    def disconnect(self) -> Dict[str, Any]:
        self.pairing.disconnect()
        return self.select("none")

    def save_upload(self, filename: str, content: bytes) -> Path:
        safe = Path(filename).name.replace(" ", "_")
        allowed = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}
        if Path(safe).suffix.lower() not in allowed:
            raise ValueError("Unsupported video extension")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"Upload exceeds {settings.max_upload_mb} MB")
        upload_dir = ROOT / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{int(time.time())}_{safe}"
        path.write_bytes(content)
        return path

    def devices(self, max_index: int = 5) -> Dict[str, Any]:
        opencv_devices = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            ok = bool(cap.isOpened())
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if ok else 0
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if ok else 0
            cap.release()
            opencv_devices.append({"index": i, "available": ok,
                                   "resolution": [width, height] if ok else None,
                                   "connected_to_pipeline": ok and self.source_type in {"webcam", "usb"}
                                   and self.last_frame_at is not None})
        windows = enumerate_windows_camera_devices()
        return {"opencv_devices": opencv_devices, "windows_devices": windows.get("devices", []),
                "windows_platform": windows.get("platform"), "windows_note": windows.get("note"),
                "windows_error": windows.get("error"),
                "note": "A listed PnP device is diagnostic only. A camera is reported connected only after real frames are processed."}

    def jpeg_snapshot(self) -> bytes:
        with self._lock:
            frame = self.latest_annotated
        if frame is None:
            frame = self.pipeline.placeholder("NO CAMERA SIGNAL")
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            return b""
        return encoded.tobytes()

    async def stream_generator(self):
        boundary = b"--sihframe"
        while True:
            jpeg = await asyncio.to_thread(self.jpeg_snapshot)
            yield (boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                   str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
            await asyncio.sleep(1.0 / max(1.0, self.camera_fps))

    def set_ai_fps(self, value: float) -> None:
        self.ai_fps = max(0.5, min(15.0, float(value)))

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "source_type": self.source_type,
                "source_config": {k: str(v) for k, v in self.source_config.items()},
                "connected": self.source_type == "phone" and bool(self.pairing.current.connected) or
                             self.last_frame_at is not None and (time.time() - self.last_frame_at) < 5.0,
                "transport": self.transport,
                "resolution": self.resolution,
                "fps": round(self.fps, 2),
                "processed_fps": round(self.processed_fps, 2),
                "ai_fps_target": self.ai_fps,
                "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
                "one_way_clock_skew_ms": None if self.clock_skew_one_way_ms is None else round(self.clock_skew_one_way_ms, 1),
                "frames_received": self.frame_count,
                "frames_processed": self.processed_count,
                "last_frame_at": now_iso() if self.last_frame_at else None,
                "error": self.error,
                "phone": self.pairing.status(),
                "models": self.pipeline.status(),
                "sources": SOURCE_CATALOG,
                "usb_guide": USB_GUIDE,
            }

    def ensure_worker(self) -> None:
        """Restart the AI worker after a test/application lifespan restart."""
        if self._worker_stop.is_set() or not self._worker_thread.is_alive():
            self._worker_stop = threading.Event()
            self._worker_thread = threading.Thread(target=self._processing_loop,
                                                   name="sih-ai-worker", daemon=True)
            self._worker_thread.start()

    def close(self) -> None:
        self._stop_current()
        self._worker_stop.set()
        if self._worker_thread.is_alive() and self._worker_thread is not threading.current_thread():
            self._worker_thread.join(timeout=2.0)
