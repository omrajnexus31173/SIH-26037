from __future__ import annotations

import time
from pathlib import Path

from backend.config import ROOT


def wait_for_frames(client, minimum: int = 1, timeout_s: float = 10.0):
    """Wait for a *new* source to be genuinely connected, not stale counters."""
    deadline = time.monotonic() + timeout_s
    status = {}
    while time.monotonic() < deadline:
        status = client.get("/api/camera/status").json()
        resolution = status.get("resolution") or [0, 0]
        if (
            int(status.get("frames_received", 0)) >= minimum
            and status.get("connected") is True
            and int(resolution[0]) > 0
            and int(resolution[1]) > 0
        ):
            return status
        time.sleep(0.15)
    return status


def test_camera_catalog_sources_usb_guide_and_device_probe(client):
    catalog = client.get("/api/camera/sources")
    assert catalog.status_code == 200
    ids = {item["id"] for item in catalog.json()["sources"]}
    assert {"phone", "usb", "ip", "webcam", "video", "synthetic", "none"}.issubset(ids)
    assert "important" in catalog.json()["usb_guide"]

    devices = client.get("/api/camera/devices")
    assert devices.status_code == 200
    body = devices.json()
    for key in ("opencv_devices", "windows_devices", "windows_platform", "windows_note", "note", "audit_note"):
        assert key in body
    assert isinstance(body["opencv_devices"], list)
    assert "No physical camera devices were assumed" in body["audit_note"]


def test_synthetic_and_video_sources_produce_real_processed_frames(client):
    try:
        synthetic = client.post("/api/camera/select", json={"source_type": "synthetic", "config": {}})
        assert synthetic.status_code == 200
        status = wait_for_frames(client, 1)
        assert status["source_type"] == "synthetic"
        assert int(status["frames_received"]) >= 1
        assert status["connected"] is True
        assert status["resolution"][0] > 0 and status["resolution"][1] > 0
        snapshot = client.get("/api/camera/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.content[:2] == b"\xff\xd8"

        video = client.post("/api/camera/select", json={
            "source_type": "video", "config": {"path": "assets/demo_drive.avi"},
        })
        assert video.status_code == 200
        status = wait_for_frames(client, 1)
        assert status["source_type"] == "video"
        assert int(status["frames_received"]) >= 1
        assert status["error"] == ""
        assert status["models"]["detector"]["available"] is True
    finally:
        client.post("/api/camera/disconnect", json={})


def test_video_upload_uses_real_file_and_disconnect_clears_source(client):
    source = ROOT / "assets" / "demo_drive.avi"
    upload_path: Path | None = None
    try:
        with source.open("rb") as fh:
            response = client.post(
                "/api/camera/upload",
                files={"file": ("pytest_demo.avi", fh.read(), "video/avi")},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["filename"].endswith(".avi")
        upload_path = Path(body["path"])
        assert upload_path.exists()
        assert body["camera"]["source_type"] == "video"
        status = wait_for_frames(client, 1)
        assert int(status["frames_received"]) >= 1
    finally:
        disconnected = client.post("/api/camera/disconnect", json={})
        assert disconnected.status_code == 200
        assert disconnected.json()["source_type"] == "none"
        if upload_path and upload_path.exists():
            upload_path.unlink()
