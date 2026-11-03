"""Multi-object tracking with IoU + centroid assignment and optical motion cues.

Distance and velocity for a monocular camera are image-plane quantities only.
The tracker explicitly labels relative-motion estimates as uncalibrated.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from backend.perception.types import Detection
from backend.utils import clamp


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    id: int
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[float, float]
    velocity: Tuple[float, float] = (0.0, 0.0)  # pixels/second in image plane
    class_id: int = 0
    label: str = "object"
    confidence: float = 0.0
    hits: int = 1
    age: float = 0.0
    misses: int = 0
    last_seen: float = 0.0
    area: float = 0.0
    scale_rate_per_s: float = 0.0
    direction: str = "unknown"
    history: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "bbox": list(self.bbox),
            "centroid": [round(self.centroid[0], 1), round(self.centroid[1], 1)],
            "velocity_px_s": [round(self.velocity[0], 1), round(self.velocity[1], 1)],
            "class_id": self.class_id,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "hits": self.hits,
            "age_s": round(self.age, 2),
            "misses": self.misses,
            "area_px2": round(self.area, 1),
            "scale_rate_per_s": round(self.scale_rate_per_s, 4),
            "direction": self.direction,
            "distance_basis": "uncalibrated_image_plane",
            "trail": [[round(float(x), 1), round(float(y), 1)] for x, y in self.history[-15:]],
        }


class CentroidTracker:
    def __init__(self, max_missed: int = 5, match_threshold: float = 0.72,
                 max_center_distance: float = 140.0, velocity_smoothing: float = 0.65):
        self.max_missed = int(max_missed)
        self.match_threshold = float(match_threshold)
        self.max_center_distance = float(max_center_distance)
        self.velocity_smoothing = float(velocity_smoothing)
        self._next_id = 1
        self._tracks: Dict[int, Track] = {}

    @property
    def tracks(self) -> List[Track]:
        return [self._tracks[k] for k in sorted(self._tracks)]

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def _new_track(self, det: Detection, t: float) -> Track:
        x1, y1, x2, y2 = det.bbox
        tr = Track(
            id=self._next_id, bbox=det.bbox, centroid=det.center,
            class_id=det.class_id, label=det.label, confidence=det.confidence,
            last_seen=t, area=det.area, history=[det.center],
        )
        det.track_id = tr.id
        self._tracks[tr.id] = tr
        self._next_id += 1
        return tr

    def _direction(self, track: Track, new_centroid: Tuple[float, float],
                   new_area: float, dt: float) -> str:
        dx = new_centroid[0] - track.centroid[0]
        dy = new_centroid[1] - track.centroid[1]
        if new_area > track.area * 1.06 or dy > 8:
            return "approaching"
        if new_area < track.area * 0.94 or dy < -8:
            return "receding"
        if dx < -6:
            return "moving_left"
        if dx > 6:
            return "moving_right"
        return "steady"

    def update(self, detections: List[Detection], timestamp: Optional[float] = None) -> List[Track]:
        t = float(timestamp if timestamp is not None else time.monotonic())
        if not self._tracks:
            for det in detections:
                self._new_track(det, t)
            return self.tracks

        ids = list(self._tracks.keys())
        for tr in self._tracks.values():
            tr.age += 0.0
            tr.misses += 1
        if not detections:
            for tid in list(self._tracks):
                if self._tracks[tid].misses > self.max_missed:
                    del self._tracks[tid]
            return self.tracks

        costs = np.ones((len(ids), len(detections)), dtype=np.float32) * 2.0
        predicted: List[Tuple[float, float]] = []
        dts: List[float] = []
        for row, tid in enumerate(ids):
            tr = self._tracks[tid]
            dt = max(1e-3, min(1.0, t - tr.last_seen))
            dts.append(dt)
            pred = (tr.centroid[0] + tr.velocity[0] * dt,
                    tr.centroid[1] + tr.velocity[1] * dt)
            predicted.append(pred)
            for col, det in enumerate(detections):
                px_dist = math.hypot(pred[0] - det.center[0], pred[1] - det.center[1])
                box_iou = iou(tr.bbox, det.bbox)
                class_penalty = 0.0 if det.class_id == tr.class_id else 0.22
                cost = 0.48 * (1.0 - box_iou) + 0.48 * min(1.0, px_dist / self.max_center_distance) + class_penalty
                costs[row, col] = cost
        rows, cols = linear_sum_assignment(costs)
        matched_tracks, matched_dets = set(), set()
        for r, c in zip(rows, cols):
            if costs[r, c] > self.match_threshold:
                continue
            tid = ids[r]
            det = detections[c]
            tr = self._tracks[tid]
            dt = dts[r]
            new_centroid = det.center
            vx = (new_centroid[0] - tr.centroid[0]) / dt
            vy = (new_centroid[1] - tr.centroid[1]) / dt
            a = self.velocity_smoothing
            tr.velocity = (a * tr.velocity[0] + (1 - a) * vx,
                           a * tr.velocity[1] + (1 - a) * vy)
            if tr.area > 0 and det.area > 0 and dt > 0:
                rate = (math.log(det.area) - math.log(tr.area)) / dt
                tr.scale_rate_per_s = a * tr.scale_rate_per_s + (1 - a) * clamp(rate, -3.0, 3.0)
            tr.direction = self._direction(tr, new_centroid, det.area, dt)
            tr.bbox = det.bbox
            tr.centroid = new_centroid
            tr.class_id = det.class_id
            tr.label = det.label
            tr.confidence = det.confidence
            tr.area = det.area
            tr.hits += 1
            tr.age += dt
            tr.misses = 0
            tr.last_seen = t
            tr.history.append(new_centroid)
            if len(tr.history) > 30:
                tr.history = tr.history[-30:]
            det.track_id = tid
            matched_tracks.add(r)
            matched_dets.add(c)
        for c, det in enumerate(detections):
            if c not in matched_dets:
                self._new_track(det, t)
        for tid in list(self._tracks):
            if self._tracks[tid].misses > self.max_missed:
                del self._tracks[tid]
        return self.tracks
