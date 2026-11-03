"""Shared planning types used by simulation and real-camera perception."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.utils import json_safe


@dataclass
class Obstacle:
    id: str
    x: float
    y: float
    radius: float
    vx: float = 0.0
    vy: float = 0.0
    kind: str = "unknown"
    confidence: float = 1.0
    source: str = "simulation"
    distance_basis: str = "simulation_metric_m"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "x": round(self.x, 3), "y": round(self.y, 3),
            "radius": round(self.radius, 3), "vx": round(self.vx, 3),
            "vy": round(self.vy, 3), "kind": self.kind,
            "confidence": round(self.confidence, 3), "source": self.source,
            "distance_basis": self.distance_basis,
        }


@dataclass
class PlanResult:
    status: str = "blocked"
    path: List[Tuple[float, float]] = field(default_factory=list)
    alternative_path: List[Tuple[float, float]] = field(default_factory=list)
    waypoint: Optional[Tuple[float, float]] = None
    goal: Tuple[float, float] = (0.0, 60.0)
    path_costs: List[float] = field(default_factory=list)
    length: float = 0.0
    smoothness_rad: float = 0.0
    min_clearance: float = 0.0
    mean_clearance: float = 0.0
    latency_ms: float = 0.0
    expanded_nodes: int = 0
    replan_reason: str = "initial"
    units: str = "simulation_metric_m"
    message: str = ""
    grid_shape: List[int] = field(default_factory=list)
    grid_cost_downsample: List[List[float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "path": [[round(x, 3), round(y, 3)] for x, y in self.path],
            "alternative_path": [[round(x, 3), round(y, 3)] for x, y in self.alternative_path],
            "waypoint": list(self.waypoint) if self.waypoint else None,
            "goal": list(self.goal),
            "path_costs": [round(float(c), 3) for c in self.path_costs],
            "length": round(self.length, 3),
            "smoothness_rad": round(self.smoothness_rad, 4),
            "min_clearance": round(self.min_clearance, 3),
            "mean_clearance": round(self.mean_clearance, 3),
            "latency_ms": round(self.latency_ms, 2),
            "expanded_nodes": self.expanded_nodes,
            "replan_reason": self.replan_reason,
            "units": self.units,
            "message": self.message,
            "grid_shape": self.grid_shape,
            "grid_cost_downsample": self.grid_cost_downsample,
        }
