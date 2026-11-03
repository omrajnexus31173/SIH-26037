"""Event-based evaluation metrics. All values are derived from actual simulation events."""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from backend.utils import now_iso


@dataclass
class MetricsRecorder:
    scenario_id: str = "unmarked_village"
    run_started_at: str = field(default_factory=now_iso)
    elapsed_s: float = 0.0
    distance_m: float = 0.0
    speed_sum: float = 0.0
    speed_samples: int = 0
    collision_count: int = 0
    emergency_stops: int = 0
    replans: int = 0
    replanning_latencies_ms: List[float] = field(default_factory=list)
    smoothness_samples: List[float] = field(default_factory=list)
    fps_samples: Deque[float] = field(default_factory=lambda: deque(maxlen=240))
    avoidance_successes: int = 0
    avoidance_failures: int = 0
    obstacle_encounters: int = 0
    completed: bool = False
    runs: int = 0
    completed_runs: int = 0
    last_emergency: bool = False
    last_collision_ids: set = field(default_factory=set)
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=120))
    history: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=300))

    def reset(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self.run_started_at = now_iso()
        self.elapsed_s = 0.0
        self.distance_m = 0.0
        self.speed_sum = 0.0
        self.speed_samples = 0
        self.collision_count = 0
        self.emergency_stops = 0
        self.replans = 0
        self.replanning_latencies_ms.clear()
        self.smoothness_samples.clear()
        self.fps_samples.clear()
        self.avoidance_successes = 0
        self.avoidance_failures = 0
        self.obstacle_encounters = 0
        self.completed = False
        self.runs += 1
        self.last_emergency = False
        self.last_collision_ids.clear()
        self.events.append({"t": 0.0, "type": "reset", "scenario": scenario_id})

    def event(self, kind: str, **data: Any) -> None:
        self.events.append({"t": round(self.elapsed_s, 3), "type": kind, **data})

    def record_step(self, dt: float, speed: float, distance_step: float,
                    risk_score: float, fps: float) -> None:
        self.elapsed_s += dt
        self.distance_m += max(0.0, distance_step)
        self.speed_sum += max(0.0, speed)
        self.speed_samples += 1
        self.fps_samples.append(float(fps))
        self.history.append({
            "t": round(self.elapsed_s, 2),
            "speed": round(float(speed), 3),
            "risk": round(float(risk_score), 3),
            "distance": round(self.distance_m, 2),
            "fps": round(float(fps), 1),
        })

    def record_replan(self, latency_ms: float, smoothness_rad: float, reason: str) -> None:
        self.replans += 1
        self.replanning_latencies_ms.append(float(latency_ms))
        self.smoothness_samples.append(float(smoothness_rad))
        self.event("replan", latency_ms=round(latency_ms, 2), reason=reason)

    def record_emergency_stop(self, active: bool) -> None:
        if active and not self.last_emergency:
            self.emergency_stops += 1
            self.event("emergency_stop")
        self.last_emergency = active

    def record_collisions(self, active_ids: set) -> None:
        new = active_ids - self.last_collision_ids
        for oid in new:
            self.collision_count += 1
            self.event("collision", obstacle=oid)
        self.last_collision_ids = set(active_ids)

    def record_encounter(self, obstacle_id: str, avoided: bool) -> None:
        self.obstacle_encounters += 1
        if avoided:
            self.avoidance_successes += 1
        self.event("obstacle_encounter", obstacle=obstacle_id, avoided=avoided)

    def record_completion(self) -> None:
        if not self.completed:
            self.completed = True
            self.completed_runs += 1
            self.event("completion", distance_m=round(self.distance_m, 2),
                       elapsed_s=round(self.elapsed_s, 2))

    def report(self) -> Dict[str, Any]:
        latencies = self.replanning_latencies_ms
        fps = list(self.fps_samples)
        encounters = self.avoidance_successes + self.avoidance_failures
        return {
            "generated_at": now_iso(),
            "scenario": self.scenario_id,
            "run_started_at": self.run_started_at,
            "elapsed_s": round(self.elapsed_s, 2),
            "collision_count": self.collision_count,
            "collision_avoidance_success_rate": (
                round(self.avoidance_successes / encounters, 4) if encounters else None),
            "obstacle_encounters": self.obstacle_encounters,
            "obstacle_avoidance_success": (
                round(self.avoidance_successes / self.obstacle_encounters, 4)
                if self.obstacle_encounters else None),
            "path_length_m": round(self.distance_m, 2),
            "path_smoothness_rad": (
                round(sum(self.smoothness_samples) / len(self.smoothness_samples), 5)
                if self.smoothness_samples else None),
            "replanning_count": self.replans,
            "replanning_latency_ms_mean": (
                round(sum(latencies) / len(latencies), 2) if latencies else None),
            "replanning_latency_ms_max": round(max(latencies), 2) if latencies else None,
            "completion_rate": round(self.completed_runs / self.runs, 4) if self.runs else None,
            "completed": self.completed,
            "emergency_stops": self.emergency_stops,
            "average_speed_mps": (
                round(self.speed_sum / self.speed_samples, 3) if self.speed_samples else None),
            "fps_mean": round(sum(fps) / len(fps), 2) if fps else None,
            "fps_current": round(fps[-1], 2) if fps else None,
            "runs_started": self.runs,
            "history": list(self.history),
            "events": list(self.events),
            "note": "Values are measured from actual simulation events. null means no sample was recorded.",
        }

    def write_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.report(), fh, indent=2)
