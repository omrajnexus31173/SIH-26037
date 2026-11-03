"""Measured scenario comparison.

Each scenario is executed headlessly with the real SimulationEngine, the shared
A* planner and the real SafetyMonitor. Values come from MetricsRecorder events.
No benchmark numbers are invented.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import OUTPUTS_DIR
from backend.simulation.engine import SimulationEngine
from backend.simulation.scenarios import demo_scenario_ids, get_scenario, scenario_library
from backend.utils import now_iso


def _fmt(value: Any) -> str:
    return "—" if value is None else str(value)


def run_comparison(scenario_ids: Optional[List[str]] = None,
                   max_steps: int = 3600, dt: float = 1.0 / 30.0) -> Dict[str, Any]:
    ids = scenario_ids or demo_scenario_ids()
    valid = {s["id"] for s in scenario_library()}
    ids = [str(s) for s in ids if str(s) in valid]
    if not ids:
        raise ValueError("No valid scenario IDs supplied")
    rows: List[Dict[str, Any]] = []
    for sid in ids:
        spec = get_scenario(sid)
        engine = SimulationEngine(sid, sim_fps=1.0 / dt)
        steps = 0
        for _ in range(int(max_steps)):
            engine.step(dt)
            steps += 1
            if engine.completed:
                break
        report = engine.metrics.report()
        rows.append({
            "id": sid,
            "name": spec.requested_name or spec.name,
            "difficulty": spec.difficulty,
            "category": spec.category,
            "environment": spec.environment,
            "steps_executed": steps,
            "completed": report["completed"],
            "elapsed_s": report["elapsed_s"],
            "collision_count": report["collision_count"],
            "collision_avoidance_success_rate": report["collision_avoidance_success_rate"],
            "obstacle_encounters": report["obstacle_encounters"],
            "path_length_m": report["path_length_m"],
            "path_smoothness_rad": report["path_smoothness_rad"],
            "replanning_count": report["replanning_count"],
            "replanning_latency_ms_mean": report["replanning_latency_ms_mean"],
            "replanning_latency_ms_max": report["replanning_latency_ms_max"],
            "emergency_stops": report["emergency_stops"],
            "average_speed_mps": report["average_speed_mps"],
            "fps_mean": report["fps_mean"],
            "safety_level_at_end": engine.safety.level,
            "plan_status_at_end": engine.plan.status,
        })
    completed = sum(1 for r in rows if r["completed"])
    collisions = sum(int(r["collision_count"]) for r in rows)
    return {
        "generated_at": now_iso(),
        "kind": "headless_simulation_measurement",
        "not_real_road_results": True,
        "scenario_count": len(rows),
        "completion_rate": round(completed / len(rows), 4) if rows else None,
        "total_collisions": collisions,
        "dt_s": dt,
        "max_steps_per_scenario": max_steps,
        "scenarios": rows,
        "note": ("Each row is measured from an actual engine run with fixed timestep. "
                 "A null/— value means the event had no sample. These are simulation results, not real-world driving claims."),
    }


def comparison_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# SIH-26037 Scenario Comparison", "",
        f"Generated: {report['generated_at']}  ",
        f"Runs: {report['scenario_count']} | Completion rate: {_fmt(report['completion_rate'])} | Total collisions: {report['total_collisions']}",
        "",
        "All values below are measured from headless simulation engine runs. They are **not** real-road or hardware benchmark results.",
        "",
        "| Scenario | Difficulty | Completed | Collisions | Avoid rate | Path (m) | Smoothness (rad) | Replans | Mean plan ms | Max plan ms | Stops | Avg speed (m/s) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in report["scenarios"]:
        lines.append(
            f"| {r['name']} | {r['difficulty']} | {r['completed']} | {r['collision_count']} | "
            f"{_fmt(r['collision_avoidance_success_rate'])} | {_fmt(r['path_length_m'])} | "
            f"{_fmt(r['path_smoothness_rad'])} | {r['replanning_count']} | "
            f"{_fmt(r['replanning_latency_ms_mean'])} | {_fmt(r['replanning_latency_ms_max'])} | "
            f"{r['emergency_stops']} | {_fmt(r['average_speed_mps'])} |")
    lines += ["", report["note"], ""]
    return "\n".join(lines)


def write_comparison(report: Dict[str, Any]) -> Dict[str, str]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUTS_DIR / f"scenario_comparison_{stamp}.json"
    md_path = OUTPUTS_DIR / f"scenario_comparison_{stamp}.md"
    latest_json = OUTPUTS_DIR / "scenario_comparison_latest.json"
    latest_md = OUTPUTS_DIR / "scenario_comparison_latest.md"
    payload = json.dumps(report, indent=2)
    markdown = comparison_markdown(report)
    for p in (json_path, latest_json):
        p.write_text(payload, encoding="utf-8")
    for p in (md_path, latest_md):
        p.write_text(markdown, encoding="utf-8")
    return {"json_file": str(json_path), "markdown_file": str(md_path),
            "latest_json": str(latest_json), "latest_md": str(latest_md)}


def latest_comparison() -> Optional[Dict[str, Any]]:
    path = OUTPUTS_DIR / "scenario_comparison_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
