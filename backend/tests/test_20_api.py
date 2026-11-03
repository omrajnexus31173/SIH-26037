from __future__ import annotations

from pathlib import Path

from backend.config import ROOT


def test_health_system_config_models_and_calibration_contract(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] in {"ok", "healthy", "running"}

    system = client.get("/api/system/status")
    assert system.status_code == 200
    body = system.json()
    for key in ("cpu_percent", "ram_percent", "gpu", "https_enabled", "models", "websocket_clients"):
        assert key in body

    config = client.get("/api/config")
    assert config.status_code == 200
    cfg = config.json()
    assert "detector_backend" in cfg and "simulation_difficulty" in cfg and "overlays" in cfg

    updated = client.post("/api/config", json={
        "confidence_threshold": 0.4,
        "simulation_quality": "balanced",
        "simulation_difficulty": "medium",
        "overlays": {"detections": True, "segmentation": True, "path": True,
                     "risk": True, "alternative": True, "trails": True},
    })
    assert updated.status_code == 200
    assert updated.json()["confidence_threshold"] == 0.4
    assert updated.json()["simulation_difficulty"] == "medium"

    models = client.get("/api/models")
    assert models.status_code == 200
    assert "status" in models.json() and "files" in models.json()
    selected = client.post("/api/models/detector", json={"backend": "opencv_onnx"})
    assert selected.status_code == 200
    assert selected.json()["config"]["detector_backend"] == "opencv_onnx"


def test_calibration_endpoints_save_then_clear_without_claiming_ground_truth(client):
    payload = {
        "image_width": 1280, "image_height": 720, "fx": 1000.0, "fy": 1000.0,
        "cx": 640.0, "cy": 360.0, "camera_height_m": 1.25, "pitch_deg": 8.0,
        "notes": "pytest API calibration",
    }
    try:
        before = client.get("/api/calibration")
        assert before.status_code == 200 and "calibrated" in before.json()
        saved = client.post("/api/calibration", json=payload)
        assert saved.status_code == 200
        assert saved.json()["calibrated"] is True
        assert saved.json()["basis"].startswith("calibrated_flat_ground")
        assert "estimate" in saved.json()["note"].lower()
        assert (ROOT / "config" / "camera_calibration.json").exists()
    finally:
        cleared = client.delete("/api/calibration")
        assert cleared.status_code == 200
        assert cleared.json()["calibrated"] is False
        assert not (ROOT / "config" / "camera_calibration.json").exists()


def test_scenario_library_and_simulation_controls_are_real(client):
    scenarios = client.get("/api/simulation/scenarios")
    assert scenarios.status_code == 200
    payload = scenarios.json()
    assert len(payload["scenarios"]) >= 13
    assert len(payload["demo_scenarios"]) == 10
    assert len(payload["demo_scenario_ids"]) == 10

    selected = client.post("/api/simulation/scenario", json={"scenario_id": "highway_cruising"})
    assert selected.status_code == 200
    assert selected.json()["state"]["scenario_id"] == "highway_cruising"

    for action in ("start", "pause", "resume", "stop", "start"):
        response = client.post("/api/simulation/control", json={"action": action})
        assert response.status_code == 200
        assert response.json()["scenario_id"] == "highway_cruising"

    controlled = client.post("/api/simulation/control", json={
        "speed": 1.4, "quality": "low", "difficulty": "hard",
    })
    assert controlled.status_code == 200
    state = controlled.json()
    assert state["speed_multiplier"] == 1.4
    assert state["quality"] == "low"
    assert state["difficulty"] == "hard"
    assert state["difficulty_scale"] == 1.2

    state_endpoint = client.get("/api/simulation/state")
    assert state_endpoint.status_code == 200
    full_state = state_endpoint.json()
    assert full_state["plan"]["grid_cost_downsample"]
    assert "metrics" in full_state and "safety" in full_state
    client.post("/api/config", json={"simulation_quality": "balanced", "simulation_difficulty": "medium"})
    client.post("/api/simulation/control", json={"action": "start", "speed": 1.0})


def test_pairing_session_qr_regeneration_validate_and_redirect(client):
    session = client.post("/api/pairing/session", json={"frontend_origin": "http://192.168.1.10:5173"})
    assert session.status_code == 200
    data = session.json()
    token = data["token"]
    pair_url = data["recommended_pair_url"]
    assert pair_url and "192.168.1.10:5173" in pair_url and token in pair_url
    assert "localhost" not in pair_url
    assert data["candidate_urls"]

    validation = client.get("/api/pairing/validate", params={"token": token})
    assert validation.status_code == 200 and validation.json()["valid"] is True

    qr = client.get("/api/pairing/qr.png", params={"url": pair_url, "token": token})
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/png")
    assert len(qr.content) > 1000

    bad_qr = client.get("/api/pairing/qr.png", params={"url": "http://192.168.1.10/pair", "token": token})
    assert bad_qr.status_code == 400

    regenerated = client.post("/api/pairing/regenerate", json={"frontend_origin": "http://192.168.1.10:5173"})
    assert regenerated.status_code == 200
    new_token = regenerated.json()["token"]
    assert new_token != token
    assert client.get("/api/pairing/validate", params={"token": token}).json()["valid"] is False
    assert client.get("/api/pairing/validate", params={"token": new_token}).json()["valid"] is True

    redirect = client.get("/pair", params={"token": new_token}, follow_redirects=False)
    assert redirect.status_code == 307
    assert "/pair?token=" in redirect.headers["location"]

    disconnected = client.post("/api/pairing/disconnect", json={})
    assert disconnected.status_code == 200 and disconnected.json()["status"] == "disconnected"


def test_evaluation_report_export_downloads_and_comparison_post(client):
    report = client.get("/api/evaluation/report")
    assert report.status_code == 200
    body = report.json()
    for key in ("scenario", "collision_count", "replanning_count", "path_length_m", "events", "note"):
        assert key in body

    exported = client.post("/api/evaluation/export", json={})
    assert exported.status_code == 200
    result = exported.json()
    assert Path(result["json_file"]).exists()
    assert Path(result["markdown_file"]).exists()

    json_download = client.get("/api/evaluation/download", params={"format": "json"})
    assert json_download.status_code == 200
    assert "attachment" in json_download.headers.get("content-disposition", "")
    markdown_download = client.get("/api/evaluation/download", params={"format": "md"})
    assert markdown_download.status_code == 200
    assert "SIH-26037 Evaluation Report" in markdown_download.text

    latest = client.get("/api/evaluation/comparison")
    assert latest.status_code == 200
    assert "available" in latest.json()

    comparison = client.post("/api/evaluation/comparison", json={
        "scenario_ids": ["highway_cruising", "vehicle_cut_in"], "max_steps": 300,
    })
    assert comparison.status_code == 200
    comparison_body = comparison.json()
    assert comparison_body["status"] == "ok"
    assert comparison_body["report"]["scenario_count"] == 2
    assert comparison_body["report"]["not_real_road_results"] is True
    assert Path(comparison_body["files"]["latest_json"]).exists()
    assert Path(comparison_body["files"]["latest_md"]).exists()
