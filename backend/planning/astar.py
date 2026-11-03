"""A* search and path smoothing for the shared cost grid."""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.utils import chaikin, path_smoothness, polyline_length, resample_polyline


def nearest_free(cost: np.ndarray, cell: Tuple[int, int], radius: int = 12) -> Tuple[int, int]:
    rows, cols = cost.shape
    r0, c0 = cell
    if 0 <= r0 < rows and 0 <= c0 < cols and cost[r0, c0] < 0.88:
        return r0, c0
    best = None
    best_score = float("inf")
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            r, c = r0 + dr, c0 + dc
            if not (0 <= r < rows and 0 <= c < cols):
                continue
            if cost[r, c] >= 0.88:
                continue
            score = dr * dr + dc * dc + cost[r, c] * 8
            if score < best_score:
                best_score, best = score, (r, c)
    return best or (max(0, min(rows - 1, r0)), max(0, min(cols - 1, c0)))


def astar(cost: np.ndarray, start: Tuple[int, int], goal: Tuple[int, int],
          max_iterations: int = 30000) -> Tuple[List[Tuple[int, int]], int]:
    """8-connected A*. Returns cell path and number of expanded nodes."""
    rows, cols = cost.shape
    start = nearest_free(cost, start)
    goal = nearest_free(cost, goal)
    if start == goal:
        return [start], 1
    blocked_threshold = 0.88
    g_score: Dict[Tuple[int, int], float] = {start: 0.0}
    came: Dict[Tuple[int, int], Tuple[int, int]] = {}
    heap: List[Tuple[float, float, int, int]] = []
    h0 = math.hypot(goal[0] - start[0], goal[1] - start[1])
    heapq.heappush(heap, (h0, h0, start[0], start[1]))
    closed = set()
    neighbors = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
                 (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]
    expanded = 0
    while heap and expanded < max_iterations:
        _, _, r, c = heapq.heappop(heap)
        node = (r, c)
        if node in closed:
            continue
        closed.add(node)
        expanded += 1
        if node == goal:
            path = [node]
            while node in came:
                node = came[node]
                path.append(node)
            return path[::-1], expanded
        for dr, dc, step in neighbors:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            cell_cost = float(cost[nr, nc])
            if cell_cost >= blocked_threshold:
                continue
            if dr and dc:
                # Prevent corner cutting through two blocked cells.
                if cost[r, nc] >= blocked_threshold and cost[nr, c] >= blocked_threshold:
                    continue
            tentative = g_score[(r, c)] + step * (1.0 + 3.5 * cell_cost * cell_cost)
            nxt = (nr, nc)
            if tentative < g_score.get(nxt, float("inf")):
                g_score[nxt] = tentative
                came[nxt] = (r, c)
                h = math.hypot(goal[0] - nr, goal[1] - nc)
                heapq.heappush(heap, (tentative + h, h, nr, nc))
    return [], expanded


def smooth_world_path(points: Sequence[Tuple[float, float]], cost: np.ndarray,
                      grid, spacing: float = 1.1) -> List[Tuple[float, float]]:
    """Chaikin smoothing with a collision check; returns a safe resampled path."""
    if len(points) < 2:
        return list(points)
    smoothed = chaikin(points, iterations=2)
    resampled = resample_polyline(smoothed, spacing=spacing)
    safe = []
    for x, y in resampled:
        r, c = grid.world_to_cell(x, y)
        if 0 <= r < cost.shape[0] and 0 <= c < cost.shape[1] and cost[r, c] < 0.9:
            safe.append((x, y))
    if len(safe) >= 2:
        return safe
    # If smoothing crossed a narrow obstacle, retain the exact A* path.
    return resample_polyline(points, spacing=spacing)


def path_costs(points: Sequence[Tuple[float, float]], grid) -> List[float]:
    return [grid.cost_at(x, y) for x, y in points]


def path_clearance(points: Sequence[Tuple[float, float]], clearance: np.ndarray, grid) -> Tuple[float, float]:
    if not points:
        return 0.0, 0.0
    vals = []
    for x, y in points:
        r, c = grid.world_to_cell(x, y)
        vals.append(float(clearance[r, c]))
    return float(min(vals)), float(np.mean(vals))
