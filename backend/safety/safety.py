"""Collision-risk estimation, TTC, safe-speed selection and safety override.

For simulation, distances/velocities are metric and TTC is computed from relative
velocity. For a real uncalibrated monocular camera, physical distance is NOT
claimed: proximity is an image-plane proxy and TTC is estimated from optical
expansion (scale rate). The UI always displays the measurement basis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.planning.types import Obstacle
from backend.tracking.tracker import Track
from backend.utils import clamp


@dataclass
class SafetyAssessment:
    level: str = "SAFE"
    risk_score: float = 0.0
    time_to_collision_s: Optional[float] = None
    ttc_basis: str = "not_available"
    safe_speed: float = 0.0
    speed_units: str = "m/s"
    emergency_stop: bool = False
    override: bool = False
    warnings: List[str] = field(default_factory=list)
    risk_zones: List[Dict[str, Any]] = field(default_factory=list)
    nearest_obstacle: Optional[Dict[str, Any]] = None
    distance_basis: str = "simulation_metric_m"
    calibration_note: str = "Metric simulation coordinates."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "risk_score": round(self.risk_score, 3),
            "time_to_collision_s": None if self.time_to_collision_s is None else round(self.time_to_collision_s, 2),
            "ttc_basis": self.ttc_basis,
            "safe_speed": round(self.safe_speed, 3),
            "speed_units": self.speed_units,
            "emergency_stop": self.emergency_stop,
            "override": self.override,
            "warnings": self.warnings,
            "risk_zones": self.risk_zones,
            "nearest_obstacle": self.nearest_obstacle,
            "distance_basis": self.distance_basis,
            "calibration_note": self.calibration_note,
        }


class SafetyMonitor:
    def __init__(self, caution_ttc_s: float = 5.0, high_risk_ttc_s: float = 2.8,
                 emergency_ttc_s: float = 1.35, metric_range_m: float = 15.0):
        self.caution_ttc_s = float(caution_ttc_s)
        self.high_risk_ttc_s = float(high_risk_ttc_s)
        self.emergency_ttc_s = float(emergency_ttc_s)
        self.metric_range_m = float(metric_range_m)

    def assess(self,
               obstacles: Sequence[Obstacle],
               ego: Tuple[float, float] = (0.0, 0.0),
               heading: float = 0.0,
               speed: float = 0.0,
               max_speed: float = 8.0,
               path: Sequence[Tuple[float, float]] = (),
               units: str = "simulation_metric_m",
               tracks: Sequence[Track] = (),
               free_space_ratio: float = 1.0,
               planner_blocked: bool = False) -> SafetyAssessment:
        metric = units.startswith("simulation")
        basis = "simulation_metric_m" if metric else "uncalibrated_monocular_image_plane_proxy"
        note = ("Metric coordinates from the simulation world." if metric else
                "Physical distance is NOT claimed: camera is uncalibrated; values are image-plane/optical proxies.")
        speed_units = "m/s" if metric else "relative"
        ego_v = np.array([speed * math.sin(heading), speed * math.cos(heading)], dtype=float)
        track_by_id = {f"track-{t.id}": t for t in tracks}
        risk = 0.0
        min_ttc: Optional[float] = None
        nearest: Optional[Dict[str, Any]] = None
        nearest_dist = float("inf")
        zones: List[Dict[str, Any]] = []
        warnings: List[str] = []
        close_moving_conflict = False
        path_arr = np.asarray(path, dtype=float) if path else np.empty((0, 2))

        for obs in obstacles:
            rx, ry = obs.x - ego[0], obs.y - ego[1]
            dist = max(0.0, math.hypot(rx, ry) - obs.radius)
            if metric:
                proximity = clamp(1.0 - dist / self.metric_range_m)
                if dist > 1e-5:
                    r_hat = np.array([rx, ry]) / math.hypot(rx, ry)
                    obs_v = np.array([obs.vx, obs.vy], dtype=float)
                    closing = float(np.dot(ego_v - obs_v, r_hat))
                    ttc = dist / closing if closing > 0.08 else None
                    ttc_basis = "metric_relative_velocity"
                else:
                    ttc, ttc_basis = 0.0, "metric_relative_velocity"
            else:
                proximity = clamp(1.0 - dist)
                tr = track_by_id.get(obs.id)
                rate = tr.scale_rate_per_s if tr else 0.0
                ttc = 1.0 / rate if rate > 0.08 else None
                ttc_basis = "optical_scale_expansion_uncalibrated"
            ttc_risk = clamp((self.caution_ttc_s - ttc) / self.caution_ttc_s) if ttc is not None else 0.0
            path_risk = 0.0
            if len(path_arr):
                near_path = path_arr[np.linalg.norm(path_arr - np.asarray(ego), axis=1) < (12.0 if metric else 0.7)]
                if len(near_path):
                    d = np.linalg.norm(near_path - np.array([obs.x, obs.y]), axis=1)
                    min_path = float(d.min())
                    clearance = max(0.0, min_path - obs.radius)
                    path_risk = clamp(1.0 - clearance / (2.2 if metric else 0.35))
            obstacle_risk = clamp(max(proximity * 0.9, ttc_risk, path_risk))
            risk = max(risk, obstacle_risk)
            if (metric and abs(obs.vx) + abs(obs.vy) > 0.25 and dist < 2.6
                    and abs(obs.x - ego[0]) < 2.2 and -0.5 <= obs.y - ego[1] < 3.5):
                close_moving_conflict = True
            if ttc is not None and (min_ttc is None or ttc < min_ttc):
                min_ttc = ttc
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = {
                    "id": obs.id, "kind": obs.kind,
                    "distance": round(dist, 3),
                    "distance_basis": basis,
                    "radius": round(obs.radius, 3),
                }
            level = ("EMERGENCY STOP" if obstacle_risk >= 0.88 or (ttc is not None and ttc < self.emergency_ttc_s)
                     else "HIGH RISK" if obstacle_risk >= 0.62
                     else "CAUTION" if obstacle_risk >= 0.32 else "SAFE")
            zones.append({
                "x": round(obs.x, 3), "y": round(obs.y, 3),
                "radius": round(obs.radius + (1.2 if metric else 0.18), 3),
                "level": level, "risk": round(obstacle_risk, 3),
                "id": obs.id, "kind": obs.kind,
            })
            if level in {"HIGH RISK", "EMERGENCY STOP"}:
                warnings.append(f"{level}: {obs.kind} {obs.id} near planned corridor")

        if not metric and free_space_ratio < 0.03:
            risk = max(risk, 0.72)
            warnings.append("Very little drivable area in segmentation; reducing speed")
        if planner_blocked:
            risk = max(risk, 0.95)
            warnings.append("No collision-free path; safety override requests stop")

        if min_ttc is not None and min_ttc < self.emergency_ttc_s:
            level = "EMERGENCY STOP"
        elif risk >= 0.88:
            level = "EMERGENCY STOP"
        elif risk >= 0.62 or (min_ttc is not None and min_ttc < self.high_risk_ttc_s):
            level = "HIGH RISK"
        elif risk >= 0.32 or (min_ttc is not None and min_ttc < self.caution_ttc_s):
            level = "CAUTION"
        else:
            level = "SAFE"
        # A close *moving* obstacle directly intersecting the planned corridor
        # commands a stop before TTC reaches the emergency threshold. Static
        # objects are handled by the planner's inflated occupancy grid instead,
        # avoiding a permanent stop next to a parked obstacle.
        if close_moving_conflict and risk >= 0.55:
            level = "EMERGENCY STOP"
            warnings.append("Close moving obstacle inside planned corridor")
        emergency = level == "EMERGENCY STOP"
        if emergency:
            warnings.insert(0, "Emergency stop engaged")
        safe_speed = 0.0 if emergency else max(0.0, max_speed * (1.0 - 0.78 * risk) ** 2)
        # TTC-aware longitudinal limit: decelerate before a predicted conflict,
        # rather than relying only on a late emergency stop.
        if not emergency and min_ttc is not None and min_ttc < self.caution_ttc_s:
            safe_speed = min(safe_speed, max(0.0, (min_ttc - 0.9) * 1.7))
        return SafetyAssessment(
            level=level, risk_score=risk, time_to_collision_s=min_ttc,
            ttc_basis=("not_available" if min_ttc is None else
                       ("metric_relative_velocity" if metric else "optical_scale_expansion_uncalibrated")),
            safe_speed=safe_speed, speed_units=speed_units,
            emergency_stop=emergency, override=emergency or planner_blocked,
            warnings=warnings, risk_zones=zones, nearest_obstacle=nearest,
            distance_basis=basis, calibration_note=note,
        )
