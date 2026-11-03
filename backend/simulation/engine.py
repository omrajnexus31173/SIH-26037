"""Authoritative simulation engine.

The engine calls the SAME AdaptivePlanner and SafetyMonitor classes as the real
camera pipeline. Actor positions are simulation ground truth (not a fake camera
detector). Metrics come from measured state transitions and collisions.
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.evaluation.metrics import MetricsRecorder
from backend.planning.planner import AdaptivePlanner
from backend.planning.types import Obstacle, PlanResult
from backend.safety.safety import SafetyMonitor
from backend.utils import clamp, distance, now_iso

from .scenarios import ScenarioSpec, get_scenario
from .world import SimulationWorld


DIFFICULTY_SCALES = {"easy": 0.8, "medium": 1.0, "hard": 1.2}


@dataclass
class EgoState:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # 0 = +Y
    speed: float = 0.0
    steering: float = 0.0
    target_speed: float = 7.0

    def to_dict(self) -> Dict[str, Any]:
        return {"x": round(self.x, 3), "y": round(self.y, 3),
                "heading": round(self.heading, 4), "speed": round(self.speed, 3),
                "steering": round(self.steering, 4),
                "target_speed": round(self.target_speed, 3)}


class SimulationEngine:
    def __init__(self, scenario_id: str = "unmarked_village", sim_fps: float = 20.0):
        self.scenario: ScenarioSpec = get_scenario(scenario_id)
        self.difficulty = "medium"
        self.world = SimulationWorld(self.scenario)
        self.world.difficulty_scale = DIFFICULTY_SCALES[self.difficulty]
        self.planner = AdaptivePlanner(y_max=self.scenario.length_m + 8.0)
        self.safety_monitor = SafetyMonitor()
        self.metrics = MetricsRecorder()
        self.ego = EgoState()
        self.time_s = 0.0
        self.running = True
        self.paused = False
        self.completed = False
        self.speed_multiplier = 1.0
        self.quality = "balanced"
        self.sim_fps = float(sim_fps)
        self.measured_fps = 0.0
        self.plan: PlanResult = PlanResult(units="simulation_metric_m")
        self.safety = self.safety_monitor.assess([], units="simulation_metric_m")
        self.obstacles: List[Obstacle] = []
        self.last_replan_s = -10.0
        self.replan_interval_s = 0.35
        self.replan_reason = "initial"
        self.collision_ids: set = set()
        self.encounter_state: Dict[str, Dict[str, Any]] = {}
        self.stop_latch_s = 0.0
        self.safe_timer_s = 0.0
        self.emergency_active = False
        self.last_step_wall = time.monotonic()
        self.reset(scenario_id)

    def reset(self, scenario_id: Optional[str] = None) -> None:
        if scenario_id:
            self.scenario = get_scenario(scenario_id)
        self.world = SimulationWorld(self.scenario)
        self.world.difficulty_scale = DIFFICULTY_SCALES[self.difficulty]
        self.planner = AdaptivePlanner(y_max=self.scenario.length_m + 8.0)
        self.ego = EgoState(x=0.0, y=0.0, heading=0.0, speed=0.0,
                            target_speed=self.scenario.target_speed_mps)
        self.time_s = 0.0
        self.running = True
        self.paused = False
        self.completed = False
        self.metrics.reset(self.scenario.id)
        self.plan = PlanResult(units="simulation_metric_m")
        self.safety = self.safety_monitor.assess([], units="simulation_metric_m")
        self.obstacles = []
        self.last_replan_s = -10.0
        self.replan_reason = "initial"
        self.collision_ids = set()
        self.encounter_state = {}
        self.stop_latch_s = 0.0
        self.safe_timer_s = 0.0
        self.emergency_active = False
        self.last_step_wall = time.monotonic()
        self._replan("reset")

    def set_scenario(self, scenario_id: str) -> None:
        self.reset(scenario_id)

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self.last_step_wall = time.monotonic()

    def start(self) -> None:
        self.running = True
        self.paused = False
        self.last_step_wall = time.monotonic()

    def stop(self) -> None:
        self.running = False
        self.paused = True
        self.ego.speed = 0.0

    def set_speed_multiplier(self, value: float) -> None:
        self.speed_multiplier = float(clamp(float(value), 0.25, 3.0))

    def set_quality(self, value: str) -> None:
        if value in {"low", "balanced", "high"}:
            self.quality = value

    def set_difficulty(self, value: str) -> None:
        key = str(value).lower()
        if key in DIFFICULTY_SCALES:
            self.difficulty = key
            self.world.difficulty_scale = DIFFICULTY_SCALES[key]

    def _ego_relative_bounds(self, lookahead: float = 65.0) -> List[Tuple[float, float, float]]:
        y0 = max(0.0, self.ego.y - 2.0)
        y1 = min(self.scenario.length_m + 8.0, self.ego.y + lookahead)
        samples = []
        for y in np.linspace(y0, y1, 40):
            c = self.scenario.center_at(float(y))
            w = self.scenario.road_width_at(float(y))
            samples.append((float(y - self.ego.y), c - w / 2 - self.ego.x, c + w / 2 - self.ego.x))
        return samples

    def _relative_obstacles(self) -> List[Obstacle]:
        ego_vx = self.ego.speed * math.sin(self.ego.heading)
        ego_vy = self.ego.speed * math.cos(self.ego.heading)
        out = []
        for o in self.obstacles:
            # Only include obstacles in the forward planning window and a small rear buffer.
            if not (-8.0 <= o.y - self.ego.y <= 68.0):
                continue
            out.append(Obstacle(
                id=o.id, x=o.x - self.ego.x, y=o.y - self.ego.y,
                radius=o.radius, vx=o.vx - ego_vx, vy=o.vy - ego_vy,
                kind=o.kind, confidence=o.confidence, source=o.source,
                distance_basis="simulation_metric_m"))
        return out

    def _globalize_plan(self, rel: PlanResult) -> PlanResult:
        p = copy.copy(rel)
        ex, ey = self.ego.x, self.ego.y
        p.path = [(x + ex, y + ey) for x, y in rel.path]
        p.alternative_path = [(x + ex, y + ey) for x, y in rel.alternative_path]
        p.waypoint = ((rel.waypoint[0] + ex, rel.waypoint[1] + ey)
                      if rel.waypoint else (ex, ey))
        p.goal = (self.scenario.goal_x, self.scenario.length_m)
        return p

    def _replan(self, reason: str) -> None:
        self.replan_reason = reason
        rel_obstacles = self._relative_obstacles()
        goal_rel = (self.scenario.goal_x - self.ego.x,
                    max(2.0, self.scenario.length_m - self.ego.y))
        rel = self.planner.plan(
            obstacles=rel_obstacles,
            goal=goal_rel,
            start=(0.0, 0.0),
            road_bounds=self._ego_relative_bounds(),
            units="simulation_metric_m",
            replan_reason=reason,
            include_alternative=True,
        )
        self.plan = self._globalize_plan(rel)
        self.last_replan_s = self.time_s
        self.metrics.record_replan(rel.latency_ms, rel.smoothness_rad, reason)

    def _choose_waypoint(self) -> Tuple[float, float]:
        path = self.plan.path
        if not path:
            return (self.ego.x, self.ego.y + 4.0)
        lookahead = clamp(3.0 + self.ego.speed * 0.45, 3.0, 10.0)
        for p in path:
            if distance(p, (self.ego.x, self.ego.y)) >= lookahead:
                return p
        return path[-1]

    def _control(self, dt: float, emergency_active: bool = False) -> Tuple[float, float]:
        """Pure-pursuit steering + longitudinal speed controller. Returns (steer, desired_speed)."""
        emergency = emergency_active or self.completed
        desired_speed = 0.0 if emergency else min(self.safety.safe_speed, self.scenario.target_speed_mps)
        ttc = self.safety.time_to_collision_s
        # If a dynamic obstacle keeps the stop latch active, a very slow creep is
        # permitted after 1.8 s so the vehicle can clear a narrow corridor
        # instead of deadlocking. No creep is allowed at a real imminent TTC.
        if (emergency and not self.completed and self.plan.status == "ok"
                and self.stop_latch_s > 1.8 and (ttc is None or ttc > 1.1)):
            desired_speed = 0.85
        # Additional conservative braking for a close predicted conflict.
        if not emergency and ttc is not None and ttc < 4.5:
            desired_speed = min(desired_speed, max(0.0, (ttc - 0.75) * 1.5))
        waypoint = self._choose_waypoint()
        dx, dy = waypoint[0] - self.ego.x, waypoint[1] - self.ego.y
        target_heading = math.atan2(dx, dy)
        alpha = math.atan2(math.sin(target_heading - self.ego.heading),
                           math.cos(target_heading - self.ego.heading))
        wheelbase = 2.7
        ld = max(2.0, math.hypot(dx, dy))
        steer = math.atan2(2.0 * wheelbase * math.sin(alpha), ld)
        steer = float(clamp(steer, -0.62, 0.62))
        # Keep the vehicle inside the physical road envelope.
        c = self.scenario.center_at(self.ego.y)
        w = self.scenario.road_width_at(self.ego.y)
        if self.ego.x < c - w / 2 + 0.8 or self.ego.x > c + w / 2 - 0.8:
            steer += 0.12 * (c - self.ego.x)
            desired_speed *= 0.55
        return steer, max(0.0, desired_speed)

    def _evaluate_encounters(self) -> None:
        active_collisions = set()
        for obs in self.obstacles:
            d = math.hypot(obs.x - self.ego.x, obs.y - self.ego.y)
            collision_radius = obs.radius + 1.05
            if d < collision_radius:
                active_collisions.add(obs.id)
            state = self.encounter_state.setdefault(obs.id, {"near": False, "counted": False, "collided": False})
            if d < collision_radius + 3.2 and abs(obs.x - self.ego.x) < 4.0 and obs.y > self.ego.y - 1.0:
                state["near"] = True
            if obs.id in active_collisions:
                state["collided"] = True
            if state["near"] and not state["counted"] and obs.y < self.ego.y - 2.0:
                state["counted"] = True
                self.metrics.record_encounter(obs.id, not state["collided"])
        self.metrics.record_collisions(active_collisions)
        self.collision_ids = active_collisions

    def step(self, real_dt: Optional[float] = None) -> Dict[str, Any]:
        wall = time.monotonic()
        if real_dt is None:
            real_dt = max(1e-4, wall - self.last_step_wall)
        self.last_step_wall = wall
        real_dt = max(1e-4, min(0.25, float(real_dt)))
        self.measured_fps = 1.0 / real_dt
        if not self.running or self.paused or self.completed:
            return self.state()
        dt = min(0.12, real_dt * self.speed_multiplier)
        self.time_s += dt
        newly_active = self.world.update(self.time_s, dt, ego=self.ego)
        self.obstacles = self.world.obstacles()

        need_replan = (
            self.time_s - self.last_replan_s >= self.replan_interval_s or
            bool(newly_active) or self.plan.status == "blocked" or
            not self.plan.path or
            (self.plan.waypoint and distance(self.plan.waypoint, (self.ego.x, self.ego.y)) < 2.0)
        )
        if need_replan:
            reason = "dynamic_obstacle_appeared" if newly_active else (
                "blocked_route_retry" if self.plan.status == "blocked" else
                "periodic_replan" if self.time_s - self.last_replan_s >= self.replan_interval_s else
                "waypoint_reached")
            self._replan(reason)

        self.safety = self.safety_monitor.assess(
            obstacles=self.obstacles,
            ego=(self.ego.x, self.ego.y),
            heading=self.ego.heading,
            speed=self.ego.speed,
            max_speed=self.scenario.target_speed_mps,
            path=self.plan.path,
            units="simulation_metric_m",
            planner_blocked=self.plan.status == "blocked",
        )
        # Hysteresis: a stop is held until the corridor has been SAFE for 0.8 s.
        # This prevents start/stop chatter around a threshold and lets a crossing
        # pedestrian or moving vehicle clear the route before the ego proceeds.
        if self.safety.emergency_stop or self.plan.status == "blocked":
            self.stop_latch_s = max(self.stop_latch_s, 1.2)
            self.safe_timer_s = 0.0
        elif self.safety.level == "SAFE":
            self.safe_timer_s += dt
            if self.safe_timer_s > 0.8:
                self.stop_latch_s = max(0.0, self.stop_latch_s - dt)
        else:
            self.safe_timer_s = 0.0
            self.stop_latch_s = max(0.0, self.stop_latch_s - dt * 0.25)
        self.emergency_active = (self.safety.emergency_stop or self.plan.status == "blocked"
                                 or self.stop_latch_s > 0.0)
        self.metrics.record_emergency_stop(self.emergency_active)
        steer, desired_speed = self._control(dt, self.emergency_active)
        accel_limit, brake_limit = 2.5, 8.0
        delta = desired_speed - self.ego.speed
        self.ego.speed += clamp(delta, -brake_limit * dt, accel_limit * dt)
        self.ego.speed = max(0.0, self.ego.speed)
        self.ego.steering = steer
        if self.ego.speed > 1e-4:
            self.ego.heading += (self.ego.speed / 2.7) * math.tan(steer) * dt
            self.ego.heading = math.atan2(math.sin(self.ego.heading), math.cos(self.ego.heading))
        prev = (self.ego.x, self.ego.y)
        self.ego.x += self.ego.speed * math.sin(self.ego.heading) * dt
        self.ego.y += self.ego.speed * math.cos(self.ego.heading) * dt
        c = self.scenario.center_at(self.ego.y)
        w = self.scenario.road_width_at(self.ego.y)
        self.ego.x = clamp(self.ego.x, c - w / 2 + 0.55, c + w / 2 - 0.55)
        travel = distance(prev, (self.ego.x, self.ego.y))
        self.metrics.record_step(dt, self.ego.speed, travel,
                                 self.safety.risk_score, self.measured_fps)
        self._evaluate_encounters()
        if self.ego.y >= self.scenario.length_m - 1.0 and abs(self.ego.x - self.scenario.goal_x) < 3.0:
            self.metrics.record_completion()
            self.completed = True
            self.ego.speed = 0.0
            self.metrics.event("run_completed", scenario=self.scenario.id)
        return self.state()

    def state(self) -> Dict[str, Any]:
        return {
            "timestamp": now_iso(),
            "scenario_id": self.scenario.id,
            "scenario_name": self.scenario.name,
            "environment": self.scenario.environment,
            "time_s": round(self.time_s, 3),
            "status": "completed" if self.completed else "paused" if self.paused else "running" if self.running else "stopped",
            "ego": self.ego.to_dict(),
            "actors": self.world.actor_dicts(),
            "obstacles": [o.to_dict() for o in self.obstacles],
            "goal": [self.scenario.goal_x, self.scenario.length_m],
            "plan": self.plan.to_dict(),
            "safety": self.safety.to_dict(),
            "metrics": self.metrics.report(),
            "speed_multiplier": self.speed_multiplier,
            "quality": self.quality,
            "difficulty": self.difficulty,
            "difficulty_scale": self.world.difficulty_scale,
            "fps": round(self.measured_fps, 2),
            "emergency_active": self.emergency_active,
            "replan_reason": self.replan_reason,
            "road_length_m": self.scenario.length_m,
        }

    def evaluation_report(self) -> Dict[str, Any]:
        return self.metrics.report()
