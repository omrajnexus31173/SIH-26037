from __future__ import annotations

import base64
import time

import cv2
import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect


def test_telemetry_websocket_initial_snapshot_and_ping(client):
    with client.websocket_connect("/ws/telemetry") as ws:
        first = ws.receive_json()
        assert first["type"] == "telemetry"
        for key in ("simulation", "camera", "perception", "system", "pairing", "evaluation", "config"):
            assert key in first
        ws.send_text("ping")
        pong = None
        for _ in range(6):
            message = ws.receive_json()
            if message.get("type") == "pong":
                pong = message
                break
        assert pong is not None and "timestamp" in pong


def test_phone_websocket_authenticated_hello_ping_frame_and_disconnect(client):
    token = client.get("/api/pairing/session").json()["token"]
    with client.websocket_connect(f"/ws/phone/{token}?peer_id=pytest-phone&transport=control") as ws:
        paired = ws.receive_json()
        assert paired["type"] == "paired" and paired["token_valid"] is True

        ws.send_json({"type": "hello", "transport": "mjpeg_websocket", "facing": "environment", "width": 320, "height": 240})
        hello = ws.receive_json()
        assert hello["type"] == "hello_ack" and hello["token_valid"] is True

        ws.send_json({"type": "ping", "client_time": 123456})
        pong = ws.receive_json()
        assert pong["type"] == "pong" and pong["client_time"] == 123456

        image = np.full((64, 96, 3), (30, 120, 210), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        jpeg = base64.b64encode(encoded.tobytes()).decode("ascii")
        ws.send_json({"type": "frame", "jpeg": jpeg, "sent_at": time.time()})
        ack = ws.receive_json()
        assert ack["type"] == "frame_ack"
        assert ack["frames_received"] >= 1

        ws.send_json({"type": "latency", "rtt_ms": 42.5})
        ws.send_json({"type": "status", "fps": 10.0, "width": 320, "height": 240, "facing": "environment"})
        ws.send_json({"type": "disconnect"})
        disconnected = ws.receive_json()
        assert disconnected["type"] == "disconnected"


def test_phone_websocket_rejects_unauthorized_token(client):
    with client.websocket_connect("/ws/phone/not-a-valid-token?peer_id=intruder&transport=control") as ws:
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "Invalid" in error["message"] or "token" in error["message"].lower()
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_webrtc_status_and_invalid_offer_returns_fallback_error(client):
    status = client.get("/api/webrtc/status")
    assert status.status_code == 200
    assert "available" in status.json()
    token = client.get("/api/pairing/session").json()["token"]
    invalid = client.post("/api/webrtc/offer", json={"token": token, "type": "offer", "sdp": "not an SDP"})
    assert invalid.status_code == 200
    body = invalid.json()
    assert "A complete SDP offer is required" in body.get("error", "")
    assert body.get("available") is False
