"""Real pretrained object detection.

Default: YOLOv8n exported to ONNX, executed with OpenCV DNN on CPU. Optional
CUDA acceleration is attempted only when explicitly requested. An optional
Ultralytics backend is provided for users who already have PyTorch installed.

No detections are synthesized. If a model cannot be loaded, the result is empty
and the model status explains why.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from .labels import class_name
from .types import Detection, DetectorResult


def _letterbox(image: np.ndarray, size: int = 640, color=(114, 114, 114)):
    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), color, dtype=np.uint8)
    top = (size - nh) // 2
    left = (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, scale, left, top


class YoloOnnxDetector:
    """YOLOv8 ONNX detector using cv2.dnn; output shape is [1, 84, 8400]."""

    def __init__(self, model_path: Path, conf_threshold: float = 0.35,
                 iou_threshold: float = 0.45, use_cuda: bool = False):
        self.model_path = Path(model_path)
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.input_size = 640
        self.net: Optional[cv2.dnn.Net] = None
        self.backend = "opencv-dnn-cpu"
        self.error = ""
        self._load(use_cuda)

    def _load(self, use_cuda: bool) -> None:
        if not self.model_path.exists():
            self.error = f"Model file missing: {self.model_path}"
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
            self.error = f"Could not load ONNX detector: {exc}"

    @property
    def available(self) -> bool:
        return self.net is not None

    def status(self) -> dict:
        return {
            "model": self.model_path.name,
            "backend": self.backend,
            "available": self.available,
            "message": self.error,
            "input_size": self.input_size,
            "confidence_threshold": self.conf_threshold,
        }

    def detect(self, frame: np.ndarray) -> DetectorResult:
        if not self.available or self.net is None or frame is None or frame.size == 0:
            return DetectorResult(model=self.model_path.name, backend=self.backend,
                                  message=self.error or "Detector unavailable")
        t0 = time.perf_counter()
        h, w = frame.shape[:2]
        inp, scale, pad_x, pad_y = _letterbox(frame, self.input_size)
        blob = cv2.dnn.blobFromImage(inp, 1.0 / 255.0, (self.input_size, self.input_size),
                                     (0, 0, 0), swapRB=True, crop=False)
        self.net.setInput(blob)
        try:
            raw = self.net.forward()
        except Exception as exc:
            self.error = f"Inference failed: {exc}"
            return DetectorResult(model=self.model_path.name, backend=self.backend,
                                  latency_ms=(time.perf_counter() - t0) * 1000.0,
                                  message=self.error)
        # [1, 84, 8400] -> [8400, 84]
        pred = np.asarray(raw).squeeze(0).T if np.asarray(raw).ndim == 3 else np.asarray(raw).reshape(-1, 84)
        if pred.shape[1] < 6:
            return DetectorResult(model=self.model_path.name, backend=self.backend,
                                  latency_ms=(time.perf_counter() - t0) * 1000.0,
                                  message="Unexpected detector output shape")
        boxes, scores, class_ids = [], [], []
        cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
        class_scores = pred[:, 4:]
        best_ids = np.argmax(class_scores, axis=1)
        best_scores = class_scores[np.arange(len(best_ids)), best_ids]
        valid = best_scores >= self.conf_threshold
        for i in np.flatnonzero(valid):
            x1 = float((cx[i] - bw[i] / 2 - pad_x) / scale)
            y1 = float((cy[i] - bh[i] / 2 - pad_y) / scale)
            x2 = float((cx[i] + bw[i] / 2 - pad_x) / scale)
            y2 = float((cy[i] + bh[i] / 2 - pad_y) / scale)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            scores.append(float(best_scores[i]))
            class_ids.append(int(best_ids[i]))
        indices: List[int] = []
        if boxes:
            try:
                nms = cv2.dnn.NMSBoxes(boxes, scores, self.conf_threshold, self.iou_threshold)
                if len(nms):
                    indices = [int(i) for i in np.asarray(nms).reshape(-1)]
            except Exception:
                indices = list(range(len(boxes)))
        detections = []
        for i in indices:
            x, y, bw_, bh_ = boxes[i]
            cid = class_ids[i]
            detections.append(Detection(
                bbox=(int(round(x)), int(round(y)), int(round(x + bw_)), int(round(y + bh_))),
                confidence=scores[i], class_id=cid, label=class_name(cid)))
        return DetectorResult(
            detections=detections,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            model=self.model_path.name,
            backend=self.backend,
            available=True,
            message=self.error,
        )


class UltralyticsDetector:
    """Optional PyTorch/Ultralytics backend; does not auto-fabricate results."""

    def __init__(self, model_path: str = "yolov8n.pt", conf_threshold: float = 0.35,
                 iou_threshold: float = 0.45, use_cuda: bool = False):
        self.model_path = model_path
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.model = None
        self.error = ""
        self.backend = "ultralytics-pytorch"
        try:
            from ultralytics import YOLO  # type: ignore
            self.model = YOLO(model_path)
            if not use_cuda:
                # Ultralytics accepts device at predict time; CPU is selected there.
                pass
            self.device = "cuda" if use_cuda else "cpu"
        except Exception as exc:
            self.error = f"Ultralytics backend unavailable: {exc}"
            self.device = "cpu"

    @property
    def available(self) -> bool:
        return self.model is not None

    def status(self) -> dict:
        return {"model": self.model_path, "backend": self.backend,
                "available": self.available, "message": self.error, "device": self.device}

    def detect(self, frame: np.ndarray) -> DetectorResult:
        if not self.available or self.model is None:
            return DetectorResult(model=self.model_path, backend=self.backend, message=self.error)
        t0 = time.perf_counter()
        try:
            results = self.model.predict(frame, conf=self.conf_threshold, iou=self.iou_threshold,
                                         device=self.device, verbose=False)
            detections: List[Detection] = []
            for result in results:
                names = result.names if hasattr(result, "names") else {}
                for box in getattr(result, "boxes", []):
                    xyxy = [float(v) for v in box.xyxy[0].tolist()]
                    cid = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    label = names.get(cid, class_name(cid)) if isinstance(names, dict) else class_name(cid)
                    detections.append(Detection(
                        bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                        confidence=conf, class_id=cid, label=str(label)))
            return DetectorResult(detections=detections,
                                  latency_ms=(time.perf_counter() - t0) * 1000.0,
                                  model=self.model_path, backend=self.backend,
                                  available=True, message=self.error)
        except Exception as exc:
            return DetectorResult(model=self.model_path, backend=self.backend,
                                  latency_ms=(time.perf_counter() - t0) * 1000.0,
                                  message=f"Inference failed: {exc}")
