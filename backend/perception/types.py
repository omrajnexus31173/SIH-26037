"""Perception data contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int
    label: str
    track_id: Optional[int] = None
    calibrated_distance: Optional[Dict[str, Any]] = None

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, float((x2 - x1) * (y2 - y1)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "confidence": round(float(self.confidence), 4),
            "class_id": int(self.class_id),
            "label": self.label,
            "track_id": self.track_id,
            "calibrated_distance": self.calibrated_distance,
        }


@dataclass
class DetectorResult:
    detections: List[Detection] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str = "none"
    backend: str = "none"
    available: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detections": [d.to_dict() for d in self.detections],
            "latency_ms": round(self.latency_ms, 2),
            "model": self.model,
            "backend": self.backend,
            "available": self.available,
            "message": self.message,
        }
