"""Deterministic simulation world state and independent actor motion."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from backend.planning.types import Obstacle
from backend.utils import clamp

from .scenarios import ActorSpec, ScenarioSpec


@dataclass
class ActorState:
    spec: ActorSpec
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    heading: float = 0.0
    active: bool = True
    spawn_x: float = 0.0
    spawn_y: float = 0.0
    phase: float = 0.0
    last_x: float = 0.0
    last_y: float = 0.0

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def kind(self) -> str:
        return self.spec.kind

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id, "kind": self.kind, "label": self.spec.label or self.kind,
            "x": round(self.x, 3), "y": round(self.y, 3),
            "vx": round(self.vx, 3), "vy": round(self.vy, 3),
            "heading": round(self.heading, 3), "radius": self.spec.radius,
            "color": self.spec.color, "active": self.active,
            "behavior": self.spec.behavior,
        }


class SimulationWorld:
    def __init__(self, scenario: ScenarioSpec):
        self.scenario = scenario
        self.actors: List[ActorState] = []
        # Scales real actor motion; exposed through the engine difficulty control.
        self.difficulty_scale = 1.0
        self.reset()

    def reset(self) -> None:
        self.actors = []
        for i, spec in enumerate(self.scenario.actors):
            self.actors.append(ActorState(
                spec=spec, x=spec.x, y=spec.y, vx=spec.vx, vy=spec.vy,
                heading=0.0 if spec.vy >= 0 else math.pi,
                active=spec.behavior != "sudden" and spec.trigger_s <= 0,
                spawn_x=spec.x, spawn_y=spec.y,
                phase=(self.scenario.seed + i * 37) % 100 / 15.0,
                last_x=spec.x, last_y=spec.y,
            ))

    def update(self, t: float, dt: float, ego=None) -> List[str]:
        """Advance actors independently. Returns IDs of newly activated actors.

        Oncoming traffic has a simple defensive-driving rule: it brakes when a
        stopped/slow ego vehicle is close in the same lateral corridor. This is
        independent traffic behaviour, not the ego's planner.
        """
        newly_active: List[str] = []
        length = self.scenario.length_m
        for actor in self.actors:
            actor.last_x, actor.last_y = actor.x, actor.y
            spec = actor.spec
            yield_factor = 1.0
            lane_shift = 0.0
            if ego is not None and spec.vy < 0 and actor.active:
                gap = actor.y - ego.y
                lateral = abs(actor.x - ego.x)
                if 0.0 < gap < 12.0 and lateral < 3.2:
                    # Brake to a slow yield rather than stopping nose-to-nose,
                    # and move away laterally so a valid corridor can reopen.
                    yield_factor = clamp((gap - 3.5) / 8.5, 0.22, 1.0)
                    lane_shift = 2.0 if actor.x >= ego.x else -2.0
            if spec.behavior == "sudden":
                if t >= spec.trigger_s and not actor.active:
                    actor.active = True
                    newly_active.append(actor.id)
                actor.vx = actor.vy = 0.0
                continue
            if spec.behavior == "crossing":
                if spec.trigger_s > 0 and t < spec.trigger_s:
                    actor.active = False
                    actor.vx = actor.vy = 0.0
                    continue
                if not actor.active:
                    actor.active = True
                    newly_active.append(actor.id)
                elapsed = max(0.0, t - spec.trigger_s)
                span = max(1.0, 9.0)
                # Triangle wave gives deterministic back-and-forth crossing.
                p = (elapsed * max(0.1, spec.speed) * self.difficulty_scale / span) % 2.0
                wave = p if p <= 1.0 else 2.0 - p
                base = spec.x
                actor.x = base + (2.0 * wave - 1.0) * 4.6
                if dt > 0:
                    actor.vx = (actor.x - actor.last_x) / dt
                actor.vy = 0.0
                actor.heading = math.pi / 2 if actor.vx >= 0 else -math.pi / 2
                continue
            actor.active = True
            move_vy = spec.vy * yield_factor * self.difficulty_scale
            actor.y += move_vy * dt
            actor.vy = move_vy
            if spec.behavior == "cut_in":
                elapsed = max(0.0, t - spec.trigger_s)
                u = clamp(elapsed * self.difficulty_scale / 2.5, 0.0, 1.0)
                smooth = u * u * (3.0 - 2.0 * u)
                target_x = actor.spawn_x * (1.0 - smooth)
                blend = min(1.0, dt * 2.2)
                actor.x = actor.x + (target_x - actor.x) * blend
            elif spec.behavior == "weave":
                weave_x = actor.spawn_x + 0.85 * math.sin(0.55 * t * self.difficulty_scale + actor.phase)
                target_x = weave_x + lane_shift
                actor.x = actor.x + (target_x - actor.x) * min(1.0, dt * 1.8)
            elif spec.behavior in {"constant", "oncoming"}:
                target_x = actor.spawn_x + lane_shift + spec.vx * self.difficulty_scale * (t % max(1.0, length))
            else:
                target_x = actor.spawn_x + lane_shift + spec.vx * self.difficulty_scale * t
            # Smooth lateral motion; return toward the original lane when clear.
            blend = min(1.0, dt * 1.8)
            actor.x = actor.x + (target_x - actor.x) * blend
            if dt > 0:
                actor.vx = (actor.x - actor.last_x) / dt
            actor.heading = math.atan2(actor.vx, actor.vy)
            # Recirculate off-screen vehicles so traffic remains alive.
            if actor.y < -12 and spec.vy < 0:
                actor.y = length + 12
            elif actor.y > length + 12 and spec.vy > 0:
                actor.y = -12
                if spec.behavior == "cut_in":
                    actor.x = actor.spawn_x
        return newly_active

    def obstacles(self) -> List[Obstacle]:
        out: List[Obstacle] = []
        for a in self.actors:
            if not a.active:
                continue
            out.append(Obstacle(
                id=a.id, x=a.x, y=a.y, radius=a.spec.radius,
                vx=a.vx, vy=a.vy, kind=a.kind, confidence=1.0,
                source="simulation_ground_truth",
                distance_basis="simulation_metric_m"))
        return out

    def actor_dicts(self) -> List[Dict[str, object]]:
        return [a.to_dict() for a in self.actors]
