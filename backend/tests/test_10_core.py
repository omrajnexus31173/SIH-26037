from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import pytest

from backend.config import ROOT, settings
from backend.evaluation.comparison import run_comparison
from backend.evaluation.metrics import MetricsRecorder
from backend.perception.calibration import CalibrationManager, CameraCalibration
from backend.perception.detector import YoloOnnxDetector
from backend.perception.types import Detection
from backend.pipeline import PerceptionPipeline
from backend.planning.planner import AdaptivePlanner
from backend.planning.types import Obstacle
from backend.safety.safety import SafetyMonitor
from backend.segmentation.road import TwinLiteNetSegmenter
from backend.simulation.engine import SimulationEngine
from backend.simulation.scenarios import demo_scenario_ids, demo_scenarios, scenario_library
from backend.tracking.tracker import CentroidTracker

EXPECTED_HASHES = {
    "yolov8n.onnx": "65158dad735be799c2466fa15e260c09558080bd530b42a8d0c3d1b419afd8b5",
    "twinlitenet_da.onnx": "f505b56bd7c9e4e38b2928373aa4daa191a9a398e07e1fb340024b9ce84d4285",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_bundled_models_and_assets_exist_with_verified_hashes():
    for name, expected in EXPECTED_HASHES.items():
        path = settings.model_dir / name
        assert path.exists(), f"missing bundled model {name}"
        assert sha256(path) == expected
    assert (ROOT / "assets" / "sample_road.jpg").exists()
    assert (ROOT / "assets" / "demo_drive.avi").stat().st_size > 100_000


def test_all_backend_modules_import():
    import backend.camera.manager  # noqa: F401
    import backend.camera.pairing  # noqa: F401
    import backend.camera.webrtc  # noqa: F401
    import backend.camera.windows_devices  # noqa: F401
    import backend.evaluation.comparison  # noqa: F401
    import backend.main  # noqa: F401
    import backend.perception.calibration  # noqa: F401
    import backend.segmentation.road  # noqa: F401
    import backend.simulation.engine  # noqa: F401
    import backend.state  # noqa: F401


def test_astar_planner_measured_result():
    planner = AdaptivePlanner()
    obstacle = Obstacle(id="test-car", x=0.0, y=12.0, radius=1.0, vx=0.0, vy=-1.0,
                        source="test", distance_basis="simulation_metric_m")
    result = planner.plan([obstacle], goal=(0.0, 45.0),
                          road_bounds=[(0, -8, 8), (45, -8, 8)],
                          units="simulation_metric_m", replan_reason="pytest")
    assert result.status == "ok"
    assert len(result.path) > 5
    assert result.length > 0
    assert result.latency_ms >= 0
    assert result.grid_shape and result.grid_cost_downsample
    assert result.units == "simulation_metric_m"


def test_safety_monitor_metric_risk_and_explicit_basis():
    monitor = SafetyMonitor()
    obstacle = Obstacle(id="oncoming", x=0.0, y=8.0, radius=1.0, vx=0.0, vy=-5.0,
                        source="test", distance_basis="simulation_metric_m")
    assessment = monitor.assess([obstacle], ego=(0.0, 0.0), speed=8.0, max_speed=8.0,
                                path=[(0.0, 0.0), (0.0, 8.0)], units="simulation_metric_m")
    data = assessment.to_dict()
    assert data["risk_score"] > 0
    assert data["risk_zones"]
    assert data["ttc_basis"]
    assert "simulation" in data["distance_basis"]
    assert data["level"] in {"SAFE", "CAUTION", "HIGH RISK", "EMERGENCY STOP"}


def test_centroid_tracker_preserves_id_and_measured_motion():
    tracker = CentroidTracker()
    first = [Detection(bbox=(100, 100, 160, 180), confidence=0.9, class_id=2, label="car")]
    second = [Detection(bbox=(108, 104, 168, 184), confidence=0.88, class_id=2, label="car")]
    tracks1 = tracker.update(first, timestamp=1.0)
    tracks2 = tracker.update(second, timestamp=1.2)
    assert len(tracks1) == len(tracks2) == 1
    assert tracks1[0].id == tracks2[0].id == 1
    assert tracks2[0].hits >= 2
    assert len(tracks2[0].history) >= 2
    assert tracks2[0].to_dict()["distance_basis"] == "uncalibrated_image_plane"


def test_calibration_is_explicit_estimate_and_clearable(tmp_path):
    manager = CalibrationManager(tmp_path / "camera_calibration.json")
    assert manager.status()["calibrated"] is False
    payload = {
        "image_width": 1280, "image_height": 720, "fx": 1000.0, "fy": 1000.0,
        "cx": 640.0, "cy": 360.0, "camera_height_m": 1.25, "pitch_deg": 8.0,
        "notes": "pytest synthetic intrinsics",
    }
    saved = manager.save(payload)
    assert manager.status()["calibrated"] is True
    estimate = saved.estimate_from_bbox((600, 500, 660, 600), 1280, 720)
    assert estimate is not None
    assert estimate["basis"] == "calibrated_flat_ground_inverse_perspective"
    assert estimate["confidence"] == "estimate_only_not_ground_truth"
    assert estimate["distance_m"] > 0
    manager.clear()
    assert manager.status()["calibrated"] is False
    with pytest.raises(ValueError):
        CameraCalibration.from_dict({**payload, "pitch_deg": 0})


def test_metrics_recorder_event_derived_values():
    metrics = MetricsRecorder()
    metrics.reset("pytest")
    metrics.record_step(0.1, 5.0, 0.5, 0.2, 30.0)
    metrics.record_replan(12.5, 0.05, "pytest")
    metrics.record_emergency_stop(True)
    metrics.record_collisions({"obstacle-a"})
    metrics.record_encounter("obstacle-a", False)
    metrics.record_completion()
    report = metrics.report()
    assert report["collision_count"] == 1
    assert report["emergency_stops"] == 1
    assert report["replanning_count"] == 1
    assert report["replanning_latency_ms_mean"] == 12.5
    assert report["completed"] is True
    assert report["path_length_m"] >= 0.5
    assert any(event["type"] == "completion" for event in report["events"])


def test_scenario_library_has_all_ten_required_demos():
    scenarios = scenario_library()
    demo = demo_scenarios()
    ids = set(demo_scenario_ids())
    assert len(scenarios) >= 13
    assert len(demo) == 10
    assert len(ids) == 10
    names = {item["requested_name"] for item in demo}
    required = {
        "Highway Cruising", "Pedestrian Crossing", "Sudden Obstacle", "Vehicle Cut-In",
        "Traffic Congestion", "Multiple Moving Obstacles", "Emergency Braking",
        "Narrow Road", "Lane Blockage", "Complex Mixed Traffic",
    }
    assert required.issubset(names)
    assert all(item["difficulty"] in {"easy", "medium", "hard"} for item in demo)


def test_engine_difficulty_is_real_and_state_contains_measured_fields():
    engine = SimulationEngine("highway_cruising", sim_fps=30)
    assert engine.difficulty == "medium"
    assert engine.world.difficulty_scale == 1.0
    engine.set_difficulty("hard")
    assert engine.world.difficulty_scale == 1.2
    engine.reset("highway_cruising")
    assert engine.state()["difficulty_scale"] == 1.2
    for _ in range(45):
        engine.step(1.0 / 30.0)
    state = engine.state()
    assert state["scenario_id"] == "highway_cruising"
    assert "plan" in state and state["plan"]["grid_shape"]
    assert "safety" in state and "metrics" in state
    assert state["metrics"]["elapsed_s"] > 0


def test_headless_comparison_produces_measured_rows():
    report = run_comparison(["highway_cruising", "vehicle_cut_in"], max_steps=450, dt=1.0 / 30.0)
    assert report["kind"] == "headless_simulation_measurement"
    assert report["scenario_count"] == 2
    assert report["not_real_road_results"] is True
    assert len(report["scenarios"]) == 2
    assert all("steps_executed" in row and "collision_count" in row for row in report["scenarios"])


def test_real_yolo_and_twinlitenet_pipeline_on_sample_image():
    frame = cv2.imread(str(ROOT / "assets" / "sample_road.jpg"))
    assert frame is not None
    detector = YoloOnnxDetector(settings.yolo_model, conf_threshold=0.35, use_cuda=False)
    assert detector.available, detector.error
    detection = detector.detect(frame)
    assert detection.available
    assert len(detection.detections) >= 1
    segmenter = TwinLiteNetSegmenter(settings.segmentation_model, use_cuda=False)
    assert segmenter.available, segmenter.error
    segmentation = segmenter.segment(frame)
    assert segmentation.available
    assert segmentation.source == "twinlitenet-onnx"
    assert 0 <= segmentation.free_space_ratio <= 1

    pipeline = PerceptionPipeline()
    result = pipeline.process_frame(frame, source_type="camera")
    data = result.data
    assert data["detection"]["available"] is True
    assert len(data["detection"]["detections"]) >= 1
    assert data["segmentation"]["available"] is True
    assert data["plan"]["status"] in {"ok", "blocked"}
    assert "uncalibrated" in data["distance_disclaimer"].lower()
    # The pipeline intentionally normalizes frames to 640x360 before inference;
    # the reported perception resolution must match the annotated frame.
    assert data["resolution"] == [640, 360]
    assert result.annotated.shape[:2] == (360, 640)
    assert pipeline.set_overlays({"detections": False})["detections"] is False
    assert pipeline.set_confidence(0.42) == 0.42
    assert pipeline.set_detector_backend("opencv_onnx")["available"] is True
