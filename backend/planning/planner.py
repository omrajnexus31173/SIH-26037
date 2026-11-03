"""Adaptive A*-based path planner shared by simulation and camera pipelines.

Design:
  1. Build a forward occupancy/cost grid from road boundaries, a learned
     drivable-area polygon (camera only), and current/predicted obstacles.
  2. A* finds the least-cost route to the goal; a soft cost near obstacles and
     boundaries creates a safe corridor rather than a razor-thin shortest path.
  3. Chaikin smoothing is collision-checked; narrow passages keep the exact grid
     route if smoothing would clip an obstacle.
  4. A second A* run with the first path penalised yields an alternative route.
  5. Replanning latency, smoothness, clearance and cost are measured, not guessed.

This is a research prototype planner, not a safety-certified vehicle controller.
"""
from __future__ import annotations

import time
from typing import List, Optional, Sequence, Tuple

import numpy as np

from backend.utils import path_smoothness, polyline_length
from .astar import astar, path_clearance, path_costs, smooth_world_path
from .grid import OccupancyGrid
from .types import Obstacle, PlanResult


class AdaptivePlanner:
    def __init__(self, x_min: float = -10.0, x_max: float = 10.0,
                 y_max: float = 60.0, resolution: float = 0.5,
                 inflation: float = 1.15, prediction_horizon: float = 1.6):
        self.grid = OccupancyGrid(x_min, x_max, 0.0, y_max, resolution)
        self.inflation = float(inflation)
        self.prediction_horizon = float(prediction_horizon)

    def plan(self,
             obstacles: Sequence[Obstacle],
             goal: Tuple[float, float] = (0.0, 58.0),
             start: Tuple[float, float] = (0.0, 0.0),
             road_bounds: Optional[Sequence[Tuple[float, float, float]]] = None,
             drivable_polygon: Optional[Sequence[Tuple[float, float]]] = None,
             units: str = "simulation_metric_m",
             replan_reason: str = "initial",
             include_alternative: bool = True) -> PlanResult:
        t0 = time.perf_counter()
        g = self.grid
        g.reset()
        if road_bounds:
            g.apply_road_bounds(road_bounds)
        if drivable_polygon and len(drivable_polygon) >= 3:
            g.apply_drivable_polygon(drivable_polygon, horizon_y=min(30.0, g.y_max * 0.55))
        for obs in obstacles:
            g.add_obstacle(obs, inflation=self.inflation, prediction_horizon=self.prediction_horizon)

        start_cell = g.world_to_cell(*start)
        goal_cell = g.world_to_cell(*goal)
        cells, expanded = astar(g.cost, start_cell, goal_cell)
        result = PlanResult(
            goal=(float(goal[0]), float(goal[1])), units=units,
            replan_reason=replan_reason, grid_shape=list(g.shape),
            expanded_nodes=expanded,
        )
        if not cells:
            result.status = "blocked"
            result.message = "No collision-free route to goal; safety controller should stop."
            result.waypoint = (float(start[0]), float(start[1]))
            result.latency_ms = (time.perf_counter() - t0) * 1000.0
            result.grid_cost_downsample = g.downsample(4)
            return result

        raw = [g.cell_to_world(r, c) for r, c in cells]
        path = smooth_world_path(raw, g.cost, g, spacing=1.1)
        result.status = "ok"
        result.path = path
        result.path_costs = path_costs(path, g)
        result.length = polyline_length(path)
        result.smoothness_rad = path_smoothness(path)
        clearance = g.clearance()
        result.min_clearance, result.mean_clearance = path_clearance(path, clearance, g)
        result.waypoint = path[min(len(path) - 1, max(2, int(len(path) * 0.16)))]

        if include_alternative:
            alt_cost = g.cost.copy()
            for x, y in path[::2]:
                r, c = g.world_to_cell(x, y)
                r1, r2 = max(0, r - 2), min(g.rows, r + 3)
                c1, c2 = max(0, c - 2), min(g.cols, c + 3)
                alt_cost[r1:r2, c1:c2] = np.minimum(1.0, alt_cost[r1:r2, c1:c2] + 0.42)
            alt_cells, _ = astar(alt_cost, start_cell, goal_cell)
            if alt_cells:
                alt_raw = [g.cell_to_world(r, c) for r, c in alt_cells]
                alt = smooth_world_path(alt_raw, alt_cost, g, spacing=1.5)
                # Only show a genuinely different option.
                if len(alt) > 2 and polyline_length(alt) < result.length * 1.8:
                    if np.mean([np.linalg.norm(np.array(a) - np.array(b)) for a, b in
                                zip(alt[::max(1, len(alt)//8)], path[::max(1, len(path)//8)])]) > 0.5:
                        result.alternative_path = alt
        result.message = "A* route with dynamic obstacle inflation and collision-checked smoothing"
        result.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.grid_cost_downsample = g.downsample(4)
        return result
