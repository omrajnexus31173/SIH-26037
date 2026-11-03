"""Road understanding with a real lightweight pretrained segmentation model.

Model: TwinLiteNet (0.4M parameters) exported to ONNX. It predicts two classes
for drivable area and two for lane lines at 640x360. Outputs are logits and are
converted with a softmax. OpenCV DNN executes it on CPU; optional CUDA is used
only when explicitly enabled.

If model weights are absent, a clearly-labelled classical free-space estimator is
used. It is NOT described as an AI detection and is never represented as a
learned segmentation result.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class RoadSegmentation:
    drivable_mask: np.ndarray
    lane_mask: np.ndarray
    drivable_probability: np.ndarray
    lane_probability: np.ndarray
    free_space_polygon: List[Tuple[float, float]]
    free_space_ratio: float
    horizon_y: float
    latency_ms: float
    source: str
    available: bool
    message: str = ""
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "available": self.available,
            "message": self.message,
            "free_space_ratio": round(float(self.free_space_ratio), 4),
            "horizon_y": round(float(self.horizon_y), 4),
            "free_space_polygon": [[round(float(x), 4), round(float(y), 4)] for x, y in self.free_space_polygon],
            "lane_pixel_ratio": round(float(self.lane_mask.mean()), 5),
            "latency_ms": round(float(self.latency_ms), 2),
            "resolution": [self.width, self.height],
        }


def _softmax2(logits: np.ndarray) -> np.ndarray:
    """Stable softmax over the two-class axis of [2,H,W]."""
    x = np.asarray(logits, dtype=np.float32)
    m = np.max(x, axis=0, keepdims=True)
    e = np.exp(x - m)
    return e / np.maximum(1e-7, e.sum(axis=0, keepdims=True))


def _runs(row: np.ndarray) -> List[Tuple[int, int]]:
    padded = np.concatenate([[0], (row > 0).astype(np.uint8), [0]])
    d = np.diff(padded)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def free_space_polygon(mask: np.ndarray, rows: int = 9) -> List[Tuple[float, float]]:
    """Convert a binary drivable mask to a normalized [0..1] trapezoid polygon.

    The polygon starts at the bottom-left, runs up the left boundary, across the
    far edge, then down the right boundary. Coordinates are image-normalized and
    are not physical distances.
    """
    h, w = mask.shape[:2]
    if h == 0 or w == 0:
        return []
    left_edge: List[Tuple[float, float]] = []
    right_edge: List[Tuple[float, float]] = []
    for v in np.linspace(0.96, 0.48, rows):
        y = min(h - 1, int(round(v * (h - 1))))
        candidates = _runs(mask[y])
        candidates = [(a, b) for a, b in candidates if (b - a) >= max(8, int(w * 0.04))]
        if not candidates:
            continue
        # Prefer a wide run near the image centre, then the widest run.
        a, b = max(candidates, key=lambda r: (r[1] - r[0]) - 0.25 * abs((r[0] + r[1]) / 2 - w / 2))
        left_edge.append((a / max(1, w - 1), float(v)))
        right_edge.append((b / max(1, w - 1), float(v)))
    if not left_edge:
        return []
    return left_edge + list(reversed(right_edge))


class TwinLiteNetSegmenter:
    def __init__(self, model_path: Path, drivable_threshold: float = 0.48,
                 lane_threshold: float = 0.38, use_cuda: bool = False):
        self.model_path = Path(model_path)
        self.drivable_threshold = float(drivable_threshold)
        self.lane_threshold = float(lane_threshold)
        self.net: Optional[cv2.dnn.Net] = None
        self.backend = "opencv-dnn-cpu"
        self.error = ""
        self._load(use_cuda)

    def _load(self, use_cuda: bool) -> None:
        if not self.model_path.exists():
            self.error = f"Segmentation model missing: {self.model_path}"
            return
        try:
            net = cv2.dnn.readNetFromONNX(str(self.model_path))
            cuda_count = 0
            try:
                cuda_count = int(cv2.cuda.getCudaEnabledDeviceCount()) if hasattr(cv2, "cuda") else 0
            except Exception:
                cuda_count = 0
            if use_cuda and cuda_count > 0:
                try:
                    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    self.backend = "opencv-dnn-cuda"
                except Exception as exc:
                    self.error = f"CUDA backend unavailable; using CPU ({exc})"
                    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.net = net
        except Exception as exc:
            self.error = f"Could not load segmentation ONNX: {exc}"

    @property
    def available(self) -> bool:
        return self.net is not None

    def status(self) -> dict:
        return {"model": self.model_path.name, "backend": self.backend,
                "available": self.available, "message": self.error,
                "input_size": [640, 360], "classes": ["drivable_area", "lane_line"]}

    def segment(self, frame: np.ndarray) -> RoadSegmentation:
        h, w = frame.shape[:2]
        if not self.available or self.net is None:
            return heuristic_segmentation(frame, message=self.error)
        t0 = time.perf_counter()
        try:
            resized = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_LINEAR)
            blob = cv2.dnn.blobFromImage(resized, 1.0 / 255.0, (640, 360),
                                         (0, 0, 0), swapRB=True, crop=False)
            self.net.setInput(blob)
            da_raw, ll_raw = self.net.forward(["da", "ll"])
            da_prob_small = _softmax2(da_raw[0])[1]
            ll_prob_small = _softmax2(ll_raw[0])[1]
            da_prob = cv2.resize(da_prob_small, (w, h), interpolation=cv2.INTER_LINEAR)
            ll_prob = cv2.resize(ll_prob_small, (w, h), interpolation=cv2.INTER_LINEAR)
            drivable = (da_prob >= self.drivable_threshold).astype(np.uint8)
            lane = (ll_prob >= self.lane_threshold).astype(np.uint8)
            # Remove isolated speckle while preserving road boundaries.
            kernel = np.ones((3, 3), np.uint8)
            drivable = cv2.morphologyEx(drivable, cv2.MORPH_OPEN, kernel)
            drivable = cv2.morphologyEx(drivable, cv2.MORPH_CLOSE, kernel)
            # Sky/buildings are not drivable; keep the lower 65% of the frame.
            drivable[: int(h * 0.32), :] = 0
            lane[: int(h * 0.38), :] = 0
            rows_with_road = np.flatnonzero(drivable.mean(axis=1) > 0.08)
            horizon = float(rows_with_road[0] / max(1, h - 1)) if len(rows_with_road) else 0.45
            polygon = free_space_polygon(drivable)
            ratio = float(drivable[int(h * 0.45):, :].mean())
            return RoadSegmentation(
                drivable_mask=drivable, lane_mask=lane,
                drivable_probability=da_prob, lane_probability=ll_prob,
                free_space_polygon=polygon, free_space_ratio=ratio,
                horizon_y=horizon, latency_ms=(time.perf_counter() - t0) * 1000.0,
                source="twinlitenet-onnx", available=True, message=self.error,
                width=w, height=h)
        except Exception as exc:
            return heuristic_segmentation(frame, message=f"Segmentation inference failed: {exc}")


def heuristic_segmentation(frame: np.ndarray, message: str = "") -> RoadSegmentation:
    """Explicit non-learned fallback. It is labelled 'heuristic_fallback'."""
    h, w = frame.shape[:2]
    t0 = time.perf_counter()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Low saturation, low-to-medium brightness road-like pixels in lower frame.
    lower = np.array([0, 0, 35], dtype=np.uint8)
    upper = np.array([180, 85, 210], dtype=np.uint8)
    candidate = cv2.inRange(hsv, lower, upper)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 130)
    candidate[edges > 0] = 0
    candidate[: int(h * 0.35), :] = 0
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx((candidate > 0).astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    prob = mask.astype(np.float32) * 0.65
    return RoadSegmentation(
        drivable_mask=mask, lane_mask=np.zeros_like(mask),
        drivable_probability=prob, lane_probability=np.zeros_like(prob),
        free_space_polygon=free_space_polygon(mask), free_space_ratio=float(mask[int(h * 0.45):].mean()),
        horizon_y=0.4, latency_ms=(time.perf_counter() - t0) * 1000.0,
        source="heuristic_fallback", available=False,
        message=message or "Learned segmentation model unavailable; using labelled classical fallback.",
        width=w, height=h)
