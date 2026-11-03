"""Ten reproducible autonomous-driving scenarios.

Each scenario is declarative and seeded; no random values are generated at
runtime. The engine uses these specs to build the world, while the frontend uses
the same geometry to draw the 3D environment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActorSpec:
    id: str
    kind: str  # car | truck | bus | motorcycle | pedestrian | animal | obstacle
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    radius: float = 1.0
    color: str = "#64748b"
    behavior: str = "constant"  # constant | crossing | oncoming | sudden | weave
    trigger_s: float = 0.0
    speed: float = 0.0
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "x": self.x, "y": self.y,
            "vx": self.vx, "vy": self.vy, "radius": self.radius,
            "color": self.color, "behavior": self.behavior,
            "trigger_s": self.trigger_s, "speed": self.speed,
            "label": self.label or self.kind,
        }


@dataclass
class ScenarioSpec:
    id: str
    name: str
    description: str
    environment: str
    length_m: float
    seed: int
    centerline_amplitude: float = 0.0
    centerline_wavelength: float = 80.0
    road_width_m: float = 9.0
    narrow_sections: List[Dict[str, float]] = field(default_factory=list)
    wide_sections: List[Dict[str, float]] = field(default_factory=list)
    lane_markings: bool = True
    unstructured_segments: List[Dict[str, float]] = field(default_factory=list)
    intersection_y: Optional[float] = None
    goal_x: float = 0.0
    actors: List[ActorSpec] = field(default_factory=list)
    props: List[Dict[str, Any]] = field(default_factory=list)
    traffic_light_y: Optional[float] = None
    target_speed_mps: float = 8.0
    difficulty: str = "medium"
    requested_name: str = ""
    demo_set: bool = False
    category: str = "extended_research"

    def road_width_at(self, y: float) -> float:
        width = self.road_width_m
        for section in self.wide_sections:
            start, end, w = section.get("start", 0), section.get("end", 0), section.get("width", width)
            if start <= y <= end:
                edge = min(y - start, end - y, 4.0)
                blend = min(1.0, max(0.0, edge / 4.0))
                width = width * (1 - blend) + w * blend
        for section in self.narrow_sections:
            start, end, w = section.get("start", 0), section.get("end", 0), section.get("width", width)
            if start <= y <= end:
                # Smooth narrowing and widening at section ends.
                edge = min(y - start, end - y, 4.0)
                blend = min(1.0, max(0.0, edge / 4.0))
                return width * (1 - blend) + w * blend
        return width

    def center_at(self, y: float) -> float:
        if self.centerline_amplitude == 0:
            return 0.0
        return self.centerline_amplitude * math.sin(2 * math.pi * y / max(1.0, self.centerline_wavelength))

    def boundaries(self, step: float = 2.0) -> List[Dict[str, float]]:
        out = []
        y = 0.0
        while y <= self.length_m + step:
            c = self.center_at(y)
            w = self.road_width_at(y)
            out.append({"y": round(y, 2), "center": round(c, 3),
                        "left": round(c - w / 2, 3), "right": round(c + w / 2, 3),
                        "width": round(w, 3),
                        "unstructured": any(s["start"] <= y <= s["end"] for s in self.unstructured_segments)})
            y += step
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "environment": self.environment, "length_m": self.length_m,
            "seed": self.seed, "centerline_amplitude": self.centerline_amplitude,
            "centerline_wavelength": self.centerline_wavelength,
            "road_width_m": self.road_width_m, "lane_markings": self.lane_markings,
            "narrow_sections": self.narrow_sections,
            "wide_sections": self.wide_sections,
            "unstructured_segments": self.unstructured_segments,
            "intersection_y": self.intersection_y,
            "traffic_light_y": self.traffic_light_y,
            "goal": [self.goal_x, self.length_m],
            "target_speed_mps": self.target_speed_mps,
            "difficulty": self.difficulty,
            "requested_name": self.requested_name or self.name,
            "demo_set": self.demo_set,
            "category": self.category,
            "actors": [a.to_dict() for a in self.actors],
            "props": self.props,
            "boundaries": self.boundaries(),
        }


def _street_props(environment: str, seed: int, length: float) -> List[Dict[str, Any]]:
    """Deterministic procedural scenery: buildings, trees, signs and lights."""
    props: List[Dict[str, Any]] = []
    for side in (-1, 1):
        for i in range(int(length / 12) + 1):
            y = 8 + i * 12 + (seed % 5)
            x = side * (8.8 + (i % 3) * 1.4)
            if environment == "market":
                kind = "stall" if i % 2 == 0 else "building"
            elif environment == "village":
                kind = "tree" if i % 3 == 0 else "house"
            elif environment == "intersection":
                kind = "building" if i % 2 == 0 else "tree"
            else:
                kind = "building" if i % 3 else "tree"
            props.append({
                "id": f"prop-{side}-{i}", "kind": kind, "x": x, "y": y,
                "height": 3.0 + ((seed + i * 7) % 9) * 0.55,
                "width": 2.2 + ((seed + i * 3) % 5) * 0.4,
                "color": "#334155" if kind == "building" else "#3f6212",
                "rotation": 0.0 if side > 0 else math.pi,
            })
    for i, y in enumerate([24, 56, 88]):
        if y < length - 5:
            props.append({"id": f"sign-{i}", "kind": "sign", "x": 6.2, "y": y,
                          "height": 2.8, "width": 1.1, "color": "#0ea5e9", "label": "SIH"})
    return props


def _scenario(**kwargs) -> ScenarioSpec:
    props = kwargs.pop("props", None)
    spec = ScenarioSpec(**kwargs)
    if props is None:
        spec.props = _street_props(spec.environment, spec.seed, spec.length_m)
    else:
        spec.props = props
    if spec.traffic_light_y:
        spec.props.append({"id": "traffic-light", "kind": "traffic_light",
                           "x": 5.6, "y": spec.traffic_light_y,
                           "height": 4.2, "width": 0.6, "color": "#111827"})
    return spec


SCENARIOS: List[ScenarioSpec] = [
    _scenario(
        id="unmarked_village", name="Unmarked Village Road",
        description="Unpainted rural road with gentle curvature, loose edges, trees, houses and an oncoming motorcycle.",
        environment="village", length_m=110, seed=101,
        centerline_amplitude=1.3, centerline_wavelength=70, road_width_m=8.0,
        lane_markings=False, unstructured_segments=[{"start": 0, "end": 110}],
        goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("village-bike", "motorcycle", 1.6, 42, vy=-4.0, radius=0.8,
                      color="#f97316", behavior="oncoming", speed=4.0),
            ActorSpec("village-cow", "animal", -2.2, 68, radius=0.9, color="#d6c09b",
                      behavior="crossing", speed=0.35),
            ActorSpec("village-static", "obstacle", 2.4, 86, radius=0.75,
                      color="#a16207", behavior="constant", label="stone pile"),
        ]),
    _scenario(
        id="narrow_market", name="Narrow Market Street",
        description="Constrained market corridor with stalls, pedestrians, a parked cart and a tight 5.2 m passage.",
        environment="market", length_m=100, seed=202,
        road_width_m=8.5, narrow_sections=[{"start": 28, "end": 55, "width": 5.2}],
        lane_markings=False, goal_x=1.0, target_speed_mps=5.5,
        actors=[
            ActorSpec("market-cart", "obstacle", -1.4, 38, radius=1.05, color="#b45309", label="cart"),
            ActorSpec("market-stall-edge", "obstacle", 2.0, 48, radius=0.8, color="#92400e", label="crates"),
            ActorSpec("market-ped-1", "pedestrian", -2.8, 32, vx=0.8, radius=0.42,
                      color="#38bdf8", behavior="crossing", speed=0.8),
            ActorSpec("market-ped-2", "pedestrian", 2.7, 61, vx=-0.7, radius=0.42,
                      color="#fb7185", behavior="crossing", speed=0.7),
        ]),
    _scenario(
        id="moving_vehicle", name="Moving Vehicle Obstacle",
        description="A slower lead vehicle changes lateral position; the ego must generate and follow a safe overtake corridor.",
        environment="urban", length_m=110, seed=303,
        centerline_amplitude=0.7, centerline_wavelength=90, road_width_m=9.5,
        goal_x=0.0, target_speed_mps=8.0,
        actors=[
            ActorSpec("lead-car", "car", 0.2, 30, vy=3.0, radius=1.25,
                      color="#2563eb", behavior="weave", speed=3.0),
            ActorSpec("oncoming-car", "car", -3.0, 75, vy=-5.0, radius=1.2,
                      color="#ef4444", behavior="oncoming", speed=5.0),
        ]),
    _scenario(
        id="pedestrian_crossing", name="Pedestrian Crossing",
        description="A pedestrian enters the route near a marked crossing; the planner and safety monitor must slow or stop.",
        environment="urban", length_m=100, seed=404, road_width_m=9.0,
        goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("crossing-ped", "pedestrian", -5.0, 43, vx=1.35, radius=0.45,
                      color="#facc15", behavior="crossing", trigger_s=1.0, speed=1.35),
            ActorSpec("crossing-bike", "bicycle", 3.6, 62, vx=-1.1, radius=0.65,
                      color="#22c55e", behavior="crossing", trigger_s=3.0, speed=1.1),
            ActorSpec("parked-car", "car", 3.1, 25, radius=1.2, color="#475569"),
        ]),
    _scenario(
        id="sudden_obstacle", name="Sudden Obstacle Appears",
        description="A fallen load appears at t = 3 s. The route must replan around it with a measured latency.",
        environment="village", length_m=100, seed=505,
        centerline_amplitude=0.8, centerline_wavelength=85, road_width_m=8.6,
        lane_markings=False, unstructured_segments=[{"start": 0, "end": 100}],
        goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("sudden-load", "obstacle", 0.4, 35, radius=1.25,
                      color="#dc2626", behavior="sudden", trigger_s=3.0, label="fallen load"),
            ActorSpec("sudden-bike", "motorcycle", -2.8, 72, vy=-3.5, radius=0.75,
                      color="#a855f7", behavior="oncoming", speed=3.5),
        ]),
    _scenario(
        id="dense_traffic", name="Dense Traffic",
        description="Multiple vehicles and two-wheelers at different speeds require repeated replanning and safe speed selection.",
        environment="urban", length_m=120, seed=606, road_width_m=10.5,
        goal_x=0.0, target_speed_mps=7.5, traffic_light_y=58,
        actors=[
            ActorSpec("dense-1", "car", -2.4, 22, vy=2.6, radius=1.2, color="#3b82f6", behavior="constant", speed=2.6),
            ActorSpec("dense-2", "car", 2.3, 34, vy=3.2, radius=1.2, color="#f97316", behavior="weave", speed=3.2),
            ActorSpec("dense-3", "bus", -2.7, 52, vy=2.0, radius=1.7, color="#eab308", behavior="constant", speed=2.0),
            ActorSpec("dense-4", "motorcycle", 1.4, 64, vy=4.0, radius=0.7, color="#ec4899", behavior="weave", speed=4.0),
            ActorSpec("dense-5", "car", 3.2, 82, vy=-4.5, radius=1.2, color="#ef4444", behavior="oncoming", speed=4.5),
            ActorSpec("dense-6", "truck", -3.1, 96, vy=2.4, radius=1.6, color="#64748b", behavior="constant", speed=2.4),
        ]),
    _scenario(
        id="road_blockage", name="Road Blockage",
        description="Maintenance barriers block the centre of the road. A widened, narrow shoulder creates a measurable detour; if the shoulder is occupied the safety controller stops.",
        environment="urban", length_m=100, seed=707, road_width_m=8.5,
        wide_sections=[{"start": 35, "end": 60, "width": 12.5}],
        goal_x=0.0, target_speed_mps=6.5,
        actors=[
            ActorSpec("block-1", "obstacle", -2.0, 46, radius=1.55, color="#f59e0b", label="barrier"),
            ActorSpec("block-2", "obstacle", 1.2, 46, radius=1.55, color="#f59e0b", label="barrier"),
            ActorSpec("block-worker", "pedestrian", -4.9, 43, radius=0.45, color="#fde047"),
            ActorSpec("block-truck", "truck", -3.0, 74, vy=-2.5, radius=1.55,
                      color="#94a3b8", behavior="oncoming", speed=2.5),
        ]),
    _scenario(
        id="unstructured_road", name="No Lane Markings",
        description="Wide unstructured dirt road with no lane paint. Drivable boundaries come from road geometry and segmentation cues.",
        environment="village", length_m=115, seed=808,
        centerline_amplitude=2.0, centerline_wavelength=65, road_width_m=10.5,
        lane_markings=False, unstructured_segments=[{"start": 0, "end": 115}],
        goal_x=1.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("dirt-tractor", "truck", -2.5, 40, vy=2.2, radius=1.6,
                      color="#65a30d", behavior="constant", speed=2.2),
            ActorSpec("dirt-ped", "pedestrian", 3.3, 72, vx=-0.6, radius=0.45,
                      color="#fb923c", behavior="crossing", speed=0.6),
            ActorSpec("dirt-rock", "obstacle", 0.7, 88, radius=0.8, color="#78716c", label="rocks"),
        ]),
    _scenario(
        id="multiple_moving", name="Multiple Moving Obstacles",
        description="Crossing pedestrians, weaving two-wheelers and oncoming traffic move independently while the ego replans.",
        environment="market", length_m=115, seed=909,
        centerline_amplitude=0.9, centerline_wavelength=78, road_width_m=9.5,
        lane_markings=False, goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("multi-ped-1", "pedestrian", -4.5, 28, vx=1.2, radius=0.42,
                      color="#38bdf8", behavior="crossing", trigger_s=0.5, speed=1.2),
            ActorSpec("multi-ped-2", "pedestrian", 4.5, 52, vx=-1.0, radius=0.42,
                      color="#fb7185", behavior="crossing", trigger_s=2.0, speed=1.0),
            ActorSpec("multi-bike", "motorcycle", 1.5, 62, vy=2.2, radius=0.7,
                      color="#a855f7", behavior="weave", speed=2.2),
            ActorSpec("multi-car", "car", -2.5, 82, vy=2.5, radius=1.2,
                      color="#2563eb", behavior="constant", speed=2.5),
            ActorSpec("multi-auto", "car", 2.6, 98, vy=2.0, radius=1.1,
                      color="#ef4444", behavior="weave", speed=2.0),
        ]),
    _scenario(
        id="emergency_stop", name="Emergency Stop",
        description="A child-sized pedestrian enters directly ahead at close range. The safety override must command a full stop, then resume.",
        environment="urban", length_m=95, seed=1010, road_width_m=9.0,
        goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("emergency-ped", "pedestrian", -3.8, 30, vx=2.1, radius=0.4,
                      color="#f43f5e", behavior="crossing", trigger_s=1.8, speed=2.1),
            ActorSpec("emergency-car", "car", 2.7, 58, vy=2.0, radius=1.2,
                      color="#334155", behavior="constant", speed=2.0),
        ]),
    _scenario(
        id="highway_cruising", name="Highway Cruising",
        description="Marked multi-lane highway with light same-direction traffic, higher target speed and gentle curvature.",
        environment="urban", length_m=120, seed=1111,
        centerline_amplitude=0.45, centerline_wavelength=110, road_width_m=11.0,
        lane_markings=True, goal_x=0.0, target_speed_mps=10.0,
        actors=[
            ActorSpec("highway-car", "car", -3.2, 38, vy=5.0, radius=1.2,
                      color="#3b82f6", behavior="constant", speed=5.0),
            ActorSpec("highway-truck", "truck", 3.3, 78, vy=3.5, radius=1.55,
                      color="#94a3b8", behavior="constant", speed=3.5),
        ]),
    _scenario(
        id="vehicle_cut_in", name="Vehicle Cut-In",
        description="A vehicle in the adjacent lane moves into the ego lane at t = 2 s. The planner must replan and reduce speed.",
        environment="urban", length_m=110, seed=1212, road_width_m=10.0,
        lane_markings=True, goal_x=0.0, target_speed_mps=8.5,
        actors=[
            ActorSpec("cut-in-car", "car", 3.2, 32, vy=3.0, radius=1.2,
                      color="#f97316", behavior="cut_in", trigger_s=2.0, speed=3.0),
            ActorSpec("cut-in-lead", "car", -2.9, 68, vy=2.5, radius=1.2,
                      color="#2563eb", behavior="constant", speed=2.5),
        ]),
    _scenario(
        id="complex_mixed_traffic", name="Complex Mixed Traffic",
        description="Market intersection with pedestrians, two-wheelers, a bus, cars, static crates and a traffic light. All actors move independently.",
        environment="market", length_m=120, seed=1313, road_width_m=10.5,
        lane_markings=False, intersection_y=60, traffic_light_y=60,
        goal_x=0.0, target_speed_mps=7.0,
        actors=[
            ActorSpec("mixed-ped", "pedestrian", -4.6, 30, vx=1.0, radius=0.42,
                      color="#38bdf8", behavior="crossing", trigger_s=0.5, speed=1.0),
            ActorSpec("mixed-bike", "motorcycle", 2.5, 45, vy=2.2, radius=0.7,
                      color="#a855f7", behavior="weave", speed=2.2),
            ActorSpec("mixed-bus", "bus", -3.1, 62, vy=2.0, radius=1.65,
                      color="#eab308", behavior="constant", speed=2.0),
            ActorSpec("mixed-car", "car", 3.1, 80, vy=2.8, radius=1.2,
                      color="#22c55e", behavior="weave", speed=2.8),
            ActorSpec("mixed-scooter", "motorcycle", -1.8, 98, vy=3.0, radius=0.7,
                      color="#ec4899", behavior="constant", speed=3.0),
            ActorSpec("mixed-crates", "obstacle", 3.9, 54, radius=0.8,
                      color="#92400e", label="crates"),
        ]),
]


# The ten scenarios named in the SIH demonstration brief, mapped to reproducible
# specs. The three additional village/unstructured-road scenarios are retained
# as an extended research set rather than deleting working functionality.
DEMO_META = {
    "highway_cruising": ("Highway Cruising", "easy"),
    "pedestrian_crossing": ("Pedestrian Crossing", "medium"),
    "sudden_obstacle": ("Sudden Obstacle", "medium"),
    "vehicle_cut_in": ("Vehicle Cut-In", "medium"),
    "dense_traffic": ("Traffic Congestion", "hard"),
    "multiple_moving": ("Multiple Moving Obstacles", "hard"),
    "emergency_stop": ("Emergency Braking", "medium"),
    "narrow_market": ("Narrow Road", "hard"),
    "road_blockage": ("Lane Blockage", "hard"),
    "complex_mixed_traffic": ("Complex Mixed Traffic", "hard"),
}
for _spec in SCENARIOS:
    if _spec.id in DEMO_META:
        _spec.requested_name, _spec.difficulty = DEMO_META[_spec.id]
        _spec.demo_set = True
        _spec.category = "required_sih_demo"
    else:
        _spec.requested_name = _spec.name
        _spec.category = "extended_unstructured_road"


def get_scenario(scenario_id: str) -> ScenarioSpec:
    for s in SCENARIOS:
        if s.id == scenario_id:
            return s
    return SCENARIOS[0]


def scenario_library() -> List[Dict[str, Any]]:
    return [s.to_dict() for s in SCENARIOS]


def demo_scenario_ids() -> List[str]:
    return [s.id for s in SCENARIOS if s.demo_set]


def demo_scenarios() -> List[Dict[str, Any]]:
    return [s.to_dict() for s in SCENARIOS if s.demo_set]
