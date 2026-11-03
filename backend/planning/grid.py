"""Occupancy/cost grid shared by camera and simulation planners."""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt

from .types import Obstacle


class OccupancyGrid:
    """A forward-planning grid: x is lateral, y is forward from the ego vehicle.

    cost = 0 is ideal free space; cost >= 0.88 is treated as blocked. For a real
    monocular camera the coordinates are an uncalibrated image-plane proxy, not
    physical metres. For simulation they are metres.
    """

    def __init__(self, x_min: float = -10.0, x_max: float = 10.0,
                 y_min: float = 0.0, y_max: float = 60.0, resolution: float = 0.5):
        self.x_min, self.x_max = float(x_min), float(x_max)
        self.y_min, self.y_max = float(y_min), float(y_max)
        self.resolution = float(resolution)
        self.cols = int(round((self.x_max - self.x_min) / self.resolution)) + 1
        self.rows = int(round((self.y_max - self.y_min) / self.resolution)) + 1
        self.cost = np.zeros((self.rows, self.cols), dtype=np.float32)

    def reset(self, base_cost: float = 0.04) -> None:
        self.cost.fill(float(base_cost))

    @property
    def shape(self) -> Tuple[int, int]:
        return self.cost.shape

    def world_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        col = int(round((x - self.x_min) / self.resolution))
        row = int(round((y - self.y_min) / self.resolution))
        return max(0, min(self.rows - 1, row)), max(0, min(self.cols - 1, col))

    def cell_to_world(self, row: int, col: int) -> Tuple[float, float]:
        return self.x_min + col * self.resolution, self.y_min + row * self.resolution

    def cost_at(self, x: float, y: float) -> float:
        r, c = self.world_to_cell(x, y)
        return float(self.cost[r, c])

    def apply_road_bounds(self, bounds: Sequence[Tuple[float, float, float]], margin: float = 0.25) -> None:
        """bounds: samples (forward_y, left_x, right_x)."""
        if not bounds:
            return
        ys = np.array([b[0] for b in bounds], dtype=float)
        lefts = np.array([b[1] for b in bounds], dtype=float)
        rights = np.array([b[2] for b in bounds], dtype=float)
        xs = self.x_min + np.arange(self.cols) * self.resolution
        for row in range(self.rows):
            y = self.y_min + row * self.resolution
            left = float(np.interp(y, ys, lefts))
            right = float(np.interp(y, ys, rights))
            inside = (xs >= left + margin) & (xs <= right - margin)
            self.cost[row, ~inside] = np.maximum(self.cost[row, ~inside], 1.0)
            # Soft penalty near the road boundary.
            dl = np.abs(xs - left)
            dr = np.abs(xs - right)
            edge = np.clip(1.0 - np.minimum(dl, dr) / 1.8, 0.0, 1.0) * 0.25
            self.cost[row] = np.maximum(self.cost[row], edge)

    def apply_drivable_polygon(self, polygon: Sequence[Tuple[float, float]],
                               horizon_y: float = 28.0, penalty: float = 0.78) -> None:
        """Apply a normalized image polygon to near-field grid cells.

        polygon points use (u,v) in [0,1], v=0 at top and v=1 at bottom.
        Only cells within horizon_y are constrained: a camera cannot observe the
        full route, so farther cells remain governed by the road model.
        """
        if len(polygon) < 3:
            return
        mask = np.zeros((self.rows, self.cols), dtype=np.uint8)
        pts = []
        for u, v in polygon:
            x = (float(u) * 2.0 - 1.0) * max(abs(self.x_min), abs(self.x_max))
            y = (1.0 - float(v)) * self.y_max
            r, c = self.world_to_cell(x, y)
            pts.append([c, r])
        cv2.fillPoly(mask, [np.asarray(pts, dtype=np.int32)], 1)
        near_rows = int(min(self.rows, horizon_y / self.resolution))
        outside = mask[:near_rows] == 0
        self.cost[:near_rows][outside] = np.maximum(self.cost[:near_rows][outside], penalty)
        inside = mask[:near_rows] > 0
        self.cost[:near_rows][inside] = np.minimum(self.cost[:near_rows][inside], 0.18)

    def add_obstacle(self, obstacle: Obstacle, inflation: float = 1.15,
                     prediction_horizon: float = 1.6, predicted_weight: float = 0.60) -> None:
        positions = [(obstacle.x, obstacle.y, 1.0)]
        if abs(obstacle.vx) + abs(obstacle.vy) > 1e-4:
            positions.append((obstacle.x + obstacle.vx * prediction_horizon,
                              obstacle.y + obstacle.vy * prediction_horizon,
                              predicted_weight))
        for ox, oy, weight in positions:
            radius = max(self.resolution, obstacle.radius + inflation)
            r0, c0 = self.world_to_cell(ox, oy)
            span = int(math.ceil(radius / self.resolution)) + 2
            r1, r2 = max(0, r0 - span), min(self.rows, r0 + span + 1)
            c1, c2 = max(0, c0 - span), min(self.cols, c0 + span + 1)
            if r1 >= r2 or c1 >= c2:
                continue
            yy = (self.y_min + np.arange(r1, r2) * self.resolution)[:, None]
            xx = (self.x_min + np.arange(c1, c2) * self.resolution)[None, :]
            dist = np.hypot(xx - ox, yy - oy)
            # A conservative Gaussian-like field extends beyond the physical radius
            # so A* prefers a genuine safe corridor rather than a grazing path.
            field = np.clip(1.40 - dist / (radius * 1.8), 0.0, 1.0) * weight
            self.cost[r1:r2, c1:c2] = np.maximum(self.cost[r1:r2, c1:c2], field.astype(np.float32))
            core = dist <= max(self.resolution * 0.6, obstacle.radius * 0.65)
            self.cost[r1:r2, c1:c2][core] = np.maximum(self.cost[r1:r2, c1:c2][core], 0.98 * weight + 0.02)

    def clearance(self) -> np.ndarray:
        free = self.cost < 0.72
        return distance_transform_edt(free) * self.resolution

    def downsample(self, factor: int = 4, max_values: int = 1800) -> List[List[float]]:
        f = max(1, int(factor))
        while (self.rows // f + 1) * (self.cols // f + 1) > max_values:
            f += 1
        small = self.cost[::f, ::f]
        return [[round(float(v), 2) for v in row] for row in small]
