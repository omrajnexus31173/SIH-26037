"""Small shared helpers."""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence, Tuple

import numpy as np


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def polyline_length(points: Sequence[Sequence[float]]) -> float:
    if len(points) < 2:
        return 0.0
    arr = np.asarray(points, dtype=float)
    return float(np.linalg.norm(np.diff(arr, axis=0), axis=1).sum())


def path_smoothness(points: Sequence[Sequence[float]]) -> float:
    """Mean absolute heading change in radians. Lower is smoother."""
    if len(points) < 3:
        return 0.0
    arr = np.asarray(points, dtype=float)
    d = np.diff(arr, axis=0)
    angles = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return float(np.mean(np.abs(np.diff(angles))))


def resample_polyline(points: Sequence[Sequence[float]], spacing: float = 1.0) -> List[Tuple[float, float]]:
    if len(points) < 2:
        return [(float(p[0]), float(p[1])) for p in points]
    arr = np.asarray(points, dtype=float)
    seg = np.linalg.norm(np.diff(arr, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cumulative[-1])
    if total <= 1e-6:
        return [(float(arr[0, 0]), float(arr[0, 1])), (float(arr[-1, 0]), float(arr[-1, 1]))]
    targets = np.linspace(0.0, total, max(2, int(math.ceil(total / spacing)) + 1))
    out: List[Tuple[float, float]] = []
    for t in targets:
        i = int(np.searchsorted(cumulative, t, side="right") - 1)
        i = max(0, min(i, len(arr) - 2))
        span = max(1e-9, cumulative[i + 1] - cumulative[i])
        u = float((t - cumulative[i]) / span)
        p = arr[i] * (1 - u) + arr[i + 1] * u
        out.append((float(p[0]), float(p[1])))
    return out


def chaikin(points: Sequence[Sequence[float]], iterations: int = 2) -> List[Tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) < 3:
        return pts
    for _ in range(iterations):
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            new.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            new.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        new.append(pts[-1])
        pts = new
    return pts


def json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, (float, int, str, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        return json_safe(value.to_dict())
    return str(value)


def rate_limiter(interval_seconds: float):
    last = [0.0]

    def allowed() -> bool:
        t = time.monotonic()
        if t - last[0] >= interval_seconds:
            last[0] = t
            return True
        return False

    return allowed
