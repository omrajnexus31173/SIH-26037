"""Optional pinhole camera calibration for physical ground-plane estimates.

IMPORTANT: without this calibration file, the camera pipeline reports only
image-plane/perspective proxies and never claims physical distance. Even with
this file, estimates assume a flat road, an accurately measured camera height
and pitch, and correct intrinsic calibration. They are labelled as calibrated
estimates rather than ground-truth range measurements.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from backend.config import ROOT

CALIBRATION_PATH = ROOT / "config" / "camera_calibration.json"


@dataclass
class CameraCalibration:
    image_width: int
    image_height: int
    fx: float
    fy: float
    cx: float
    cy: float
    camera_height_m: float
    pitch_deg: float
    calibration_date: str = ""
    checkerboard: str = ""
    square_size_m: float = 0.0
    rms_reprojection_error: float = 0.0
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraCalibration":
        required = ["image_width", "image_height", "fx", "fy", "cx", "cy",
                    "camera_height_m", "pitch_deg"]
        missing = [k for k in required if data.get(k) is None]
        if missing:
            raise ValueError(f"Missing calibration fields: {', '.join(missing)}")
        obj = cls(
            image_width=int(data["image_width"]), image_height=int(data["image_height"]),
            fx=float(data["fx"]), fy=float(data["fy"]), cx=float(data["cx"]), cy=float(data["cy"]),
            camera_height_m=float(data["camera_height_m"]), pitch_deg=float(data["pitch_deg"]),
            calibration_date=str(data.get("calibration_date", "")),
            checkerboard=str(data.get("checkerboard", "")),
            square_size_m=float(data.get("square_size_m", 0.0) or 0.0),
            rms_reprojection_error=float(data.get("rms_reprojection_error", 0.0) or 0.0),
            notes=str(data.get("notes", "")),
        )
        obj.validate()
        return obj

    def validate(self) -> None:
        if self.image_width < 64 or self.image_height < 64:
            raise ValueError("Calibration image dimensions must be at least 64 px")
        if self.fx <= 0 or self.fy <= 0:
            raise ValueError("Focal lengths fx/fy must be positive")
        if not (0 < self.cx < self.image_width and 0 < self.cy < self.image_height):
            raise ValueError("Principal point must lie inside the calibration image")
        if not (0.2 < self.camera_height_m < 5.0):
            raise ValueError("Camera height must be between 0.2 m and 5.0 m")
        if not (0.0 < self.pitch_deg < 45.0):
            raise ValueError("Downward pitch must be between 0 and 45 degrees")

    def scaled_intrinsics(self, frame_width: int, frame_height: int) -> Tuple[float, float, float, float]:
        sx = float(frame_width) / float(self.image_width)
        sy = float(frame_height) / float(self.image_height)
        return self.fx * sx, self.fy * sy, self.cx * sx, self.cy * sy

    def estimate_from_bbox(self, bbox: Sequence[float], frame_width: int,
                           frame_height: int) -> Optional[Dict[str, Any]]:
        """Flat-ground inverse perspective from the bottom-centre of a box."""
        x1, y1, x2, y2 = [float(v) for v in bbox]
        u = (x1 + x2) / 2.0
        v = max(y1, y2)
        fx, fy, cx, cy = self.scaled_intrinsics(frame_width, frame_height)
        pitch = math.radians(self.pitch_deg)
        alpha = math.atan2(v - cy, fy)
        angle_below_horizontal = pitch + alpha
        if angle_below_horizontal <= math.radians(1.0):
            return None
        distance = self.camera_height_m / math.tan(angle_below_horizontal)
        lateral = (u - cx) / fx * distance
        if not (0.3 < distance < 250.0):
            return None
        return {
            "distance_m": round(float(distance), 2),
            "lateral_m": round(float(lateral), 2),
            "basis": "calibrated_flat_ground_inverse_perspective",
            "assumptions": "flat road; known intrinsics, camera height and pitch; object touches ground plane",
            "confidence": "estimate_only_not_ground_truth",
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CalibrationManager:
    def __init__(self, path: Path = CALIBRATION_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.calibration: Optional[CameraCalibration] = None
        self.error = ""
        self.load()

    def load(self) -> Optional[CameraCalibration]:
        with self._lock:
            self.calibration = None
            self.error = ""
            if not self.path.exists():
                return None
            try:
                self.calibration = CameraCalibration.from_dict(
                    json.loads(self.path.read_text(encoding="utf-8")))
                return self.calibration
            except Exception as exc:
                self.error = f"Calibration file invalid: {exc}"
                return None

    def save(self, data: Dict[str, Any]) -> CameraCalibration:
        calibration = CameraCalibration.from_dict(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(calibration.to_dict(), indent=2), encoding="utf-8")
        with self._lock:
            self.calibration = calibration
            self.error = ""
        return calibration

    def clear(self) -> None:
        with self._lock:
            self.calibration = None
            self.error = ""
        if self.path.exists():
            self.path.unlink()

    def estimate(self, bbox: Sequence[float], frame_width: int,
                 frame_height: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            calibration = self.calibration
        return calibration.estimate_from_bbox(bbox, frame_width, frame_height) if calibration else None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "calibrated": self.calibration is not None,
                "path": str(self.path),
                "calibration": self.calibration.to_dict() if self.calibration else None,
                "error": self.error,
                "basis": ("calibrated_flat_ground_inverse_perspective" if self.calibration
                          else "uncalibrated_image_plane_proxy"),
                "note": ("Physical-distance estimates are enabled but still require flat-road assumptions."
                         if self.calibration else
                         "No calibration supplied: physical distance is NOT claimed."),
                "how_to_calibrate": ("Use OpenCV calibrateCamera with a checkerboard, then enter fx, fy, cx, cy, "
                                     "image size, measured camera height and downward pitch in the dashboard."),
            }
