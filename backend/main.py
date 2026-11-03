"""SIH-26037 FastAPI backend: REST controls, MJPEG stream, WebRTC signaling,
phone WebSocket, telemetry WebSocket and evaluation reports.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse

import qrcode
from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from backend.camera.manager import USB_GUIDE
from backend.config import OUTPUTS_DIR, primary_lan_ip, settings
from backend.evaluation.comparison import latest_comparison, run_comparison, write_comparison
from backend.simulation.scenarios import demo_scenarios, demo_scenario_ids, scenario_library
from backend.state import app_state
from backend.utils import now_iso


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_state.start()
    try:
        yield
    finally:
        await app_state.stop()


app = FastAPI(
    title="SIH-26037 Adaptive Path Planning and Collision Avoidance",
    version="1.0.0",
    description="Integrated autonomous-driving research prototype: real camera perception, shared A*/safety stack, 3D simulation, WebRTC phone pairing and measured evaluation.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- helpers
def pairing_payload(session, request: Request, frontend_origin: str = "") -> Dict[str, Any]:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    urls = app_state.pairing.pairing_urls(session.token, host, scheme, frontend_origin)
    return {
        "token": session.token,
        "created_at": session.created_iso,
        "expires_at": datetime.fromtimestamp(session.expires_at, timezone.utc).isoformat(),
        "expires_in_s": max(0, int(session.expires_at - time.time())),
        "candidate_urls": urls,
        "recommended_pair_url": urls[0]["pair_url"] if urls else None,
        "secure_context_note": ("Camera access requires HTTPS on a LAN IP (or localhost). "
                                "Trust the generated self-signed certificate on the phone, or use the QR/Wi-Fi page over an HTTPS tunnel."),
        "https_enabled": settings.use_https,
    }


def model_files() -> Dict[str, Any]:
    out = {}
    for name in ["yolov8n.onnx", "twinlitenet_da.onnx"]:
        path = settings.model_dir / name
        if not path.exists():
            out[name] = {"exists": False, "size_bytes": 0, "sha256": None}
            continue
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        out[name] = {"exists": True, "size_bytes": path.stat().st_size, "sha256": h.hexdigest()}
    return out


def markdown_report(report: Dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        return "No sample recorded" if value is None else str(value)

    rows = [
        ("Scenario", report.get("scenario")),
        ("Run started", report.get("run_started_at")),
        ("Elapsed (s)", fmt(report.get("elapsed_s"))),
        ("Completed", fmt(report.get("completed"))),
        ("Completion rate", fmt(report.get("completion_rate"))),
        ("Collision count", fmt(report.get("collision_count"))),
        ("Collision avoidance success rate", fmt(report.get("collision_avoidance_success_rate"))),
        ("Obstacle encounters", fmt(report.get("obstacle_encounters"))),
        ("Obstacle avoidance success", fmt(report.get("obstacle_avoidance_success"))),
        ("Path length (m)", fmt(report.get("path_length_m"))),
        ("Path smoothness (rad)", fmt(report.get("path_smoothness_rad"))),
        ("Replanning count", fmt(report.get("replanning_count"))),
        ("Replanning latency mean (ms)", fmt(report.get("replanning_latency_ms_mean"))),
        ("Replanning latency max (ms)", fmt(report.get("replanning_latency_ms_max"))),
        ("Emergency stops", fmt(report.get("emergency_stops"))),
        ("Average speed (m/s)", fmt(report.get("average_speed_mps"))),
        ("FPS mean", fmt(report.get("fps_mean"))),
    ]
    lines = ["# SIH-26037 Evaluation Report", "", f"Generated: {report.get('generated_at')}", "",
             "| Metric | Measured value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += ["", "## Events", "", "| Time (s) | Type | Details |", "|---:|---|---|"]
    for event in report.get("events", [])[-40:]:
        details = ", ".join(f"{k}={v}" for k, v in event.items() if k not in {"t", "type"})
        lines.append(f"| {event.get('t', '')} | {event.get('type', '')} | {details} |")
    lines += ["", "All values are derived from actual simulation state transitions and events. "
                  "`No sample recorded` means the event did not occur; no numbers are fabricated.", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- root / health
@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(f"""
    <html><head><title>SIH-26037 Backend</title></head>
    <body style="font-family:system-ui;background:#0b1220;color:#dbeafe;padding:32px">
      <h1>SIH-26037 backend is running</h1>
      <p>Open the dashboard at <a style="color:#38bdf8" href="http{'s' if settings.use_https else ''}://localhost:{settings.frontend_port}">
      {'https' if settings.use_https else 'http'}://localhost:{settings.frontend_port}</a>.</p>
      <p><a style="color:#38bdf8" href="/docs">Interactive API documentation</a></p>
      <p>LAN IP: {primary_lan_ip()} | HTTPS: {settings.use_https}</p>
    </body></html>""")


@app.get("/api/health")
def health():
    return {
        "status": "ok", "project": "SIH-26037", "timestamp": now_iso(),
        "backend": "FastAPI", "models_loaded": app_state.pipeline.status(),
        "simulation_status": app_state.engine.state()["status"],
        "https_enabled": settings.use_https,
        "webrtc": app_state.webrtc.status(),
    }


@app.get("/api/system/status")
def system_status():
    return app_state.system_status()


@app.get("/api/config")
def get_config():
    return app_state.config()


@app.post("/api/config")
def post_config(payload: dict = Body(...)):
    updated = app_state.apply_config(payload)
    updated["restart_note"] = ("Changing CUDA or TLS mode requires restarting the backend. "
                              "Other settings take effect immediately.")
    return updated


@app.get("/pair")
def pair_redirect(request: Request, token: str = ""):
    """Direct backend /pair links are forwarded to the actual React pairing page."""
    scheme = "https" if settings.use_https else "http"
    base = settings.public_pair_base_url or f"{scheme}://{primary_lan_ip()}:{settings.frontend_port}"
    return RedirectResponse(f"{base.rstrip('/')}/pair?token={quote(token)}", status_code=307)


# --------------------------------------------------------------------------- pairing + QR
@app.get("/api/pairing/session")
def current_pairing_session(request: Request, frontend_origin: str = ""):
    return pairing_payload(app_state.pairing.current, request, frontend_origin)


@app.post("/api/pairing/session")
async def create_pairing_session(request: Request, payload: dict = Body(default={})):
    await app_state.close_phone_connections(revoke=False)
    session = app_state.pairing.create()
    return pairing_payload(session, request, str(payload.get("frontend_origin", "")))


@app.post("/api/pairing/regenerate")
async def regenerate_pairing(request: Request, payload: dict = Body(default={})):
    await app_state.close_phone_connections(revoke=False)
    session = app_state.pairing.create()
    return pairing_payload(session, request, str(payload.get("frontend_origin", "")))


@app.get("/api/pairing/status")
def pairing_status():
    return app_state.pairing.status()


@app.get("/api/pairing/validate")
def pairing_validate(token: str = ""):
    """Lightweight token/link validation used by the mobile pairing page."""
    session = app_state.pairing.validate(token) if token else None
    result = {
        "valid": session is not None,
        "expires_in_s": max(0, int(session.expires_at - time.time())) if session else 0,
        "reason": "" if session else "Token missing, expired, revoked or regenerated",
        "secure_context": bool(settings.use_https),
        "https_note": ("Browser camera access requires HTTPS on a LAN IP (or localhost). "
                       "Trust the self-signed certificate or open the dashboard over an HTTPS tunnel."),
    }
    return result


@app.post("/api/pairing/disconnect")
async def pairing_disconnect():
    await app_state.close_phone_connections(revoke=False)
    app_state.hub.disconnect()
    return {"status": "disconnected", "pairing": app_state.pairing.status(),
            "camera": app_state.hub.status()}


@app.get("/api/pairing/qr.png")
def pairing_qr(url: str = Query(...), token: str = Query(...)):
    """Generate a real QR code containing the supplied accessible pairing URL."""
    if token not in url or len(url) > 1000:
        raise HTTPException(status_code=400, detail="QR URL must include the active token")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="QR URL must be an absolute http(s) URL")
    if not app_state.pairing.validate(token):
        raise HTTPException(status_code=403, detail="Pairing token is expired or revoked")
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#07101c", back_color="#e0f2fe").convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store, max-age=0"})


# --------------------------------------------------------------------------- WebRTC
@app.get("/api/webrtc/status")
def webrtc_status():
    return {**app_state.webrtc.status(), "active_connections": sum(len(v) for v in app_state.webrtc.connections.values())}


@app.post("/api/webrtc/offer")
async def webrtc_offer(offer: dict = Body(...)):
    answer = await app_state.webrtc.create_answer(offer)
    return JSONResponse(content=answer)


# --------------------------------------------------------------------------- camera
@app.get("/api/camera/sources")
def camera_sources():
    return {"sources": app_state.hub.catalog(), "usb_guide": USB_GUIDE}


@app.get("/api/camera/devices")
async def camera_devices():
    devices = await asyncio.to_thread(app_state.hub.devices)
    return {**devices,
            "audit_note": "No physical camera devices were assumed; this is a live OpenCV/PnP probe."}


@app.get("/api/camera/usb-guide")
def usb_guide():
    return USB_GUIDE


@app.get("/api/camera/status")
def camera_status():
    return app_state.hub.status()


@app.post("/api/camera/select")
def camera_select(payload: dict = Body(...)):
    try:
        source_type = str(payload.get("source_type", "none"))
        config = payload.get("config") or {}
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
        return app_state.hub.select(source_type, config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/camera/upload")
async def camera_upload(file: UploadFile = File(...)):
    try:
        content = await file.read()
        path = app_state.hub.save_upload(file.filename or "upload.avi", content)
        status = app_state.hub.select("video", {"path": str(path)})
        return {"status": "ok", "path": str(path), "filename": path.name, "camera": status}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/camera/disconnect")
async def camera_disconnect():
    await app_state.close_phone_connections(revoke=False)
    return app_state.hub.disconnect()


@app.get("/api/camera/snapshot")
def camera_snapshot():
    return Response(content=app_state.hub.jpeg_snapshot(), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/camera/stream")
async def camera_stream():
    return StreamingResponse(
        app_state.hub.stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=sihframe",
        headers={"Cache-Control": "no-cache, no-store, max-age=0", "Pragma": "no-cache"},
    )


# --------------------------------------------------------------------------- models
@app.get("/api/models")
def models_status():
    return {"status": app_state.pipeline.status(), "files": model_files()}


@app.post("/api/models/detector")
def select_detector(payload: dict = Body(...)):
    backend = str(payload.get("backend", "opencv_onnx"))
    return {"status": app_state.pipeline.set_detector_backend(backend),
            "config": app_state.config()}


@app.get("/api/models/instructions")
def model_instructions():
    return {
        "bundled": model_files(),
        "yolov8n_onnx": {
            "source": "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx",
            "license": "Ultralytics YOLOv8 / AGPL-3.0",
            "size_mb_approx": 13,
        },
        "twinlitenet_onnx": {
            "source": "https://raw.githubusercontent.com/harrylal/TwinLiteNet-onnx-opencv-dnn/main/models/best.onnx",
            "license": "MIT (harrylal wrapper); original TwinLiteNet MIT, Copyright (c) 2023 Chế Quang Huy",
            "size_mb_approx": 1.8,
        },
        "download_command": "python scripts/download_models.py",
        "optional_ultralytics": "pip install ultralytics  # requires PyTorch; CPU works. Then select 'ultralytics' in Model settings.",
        "cpu_default": "OpenCV DNN CPU is the default; no GPU is required.",
    }


@app.get("/api/calibration")
def calibration_status():
    return app_state.pipeline.calibration.status()


@app.post("/api/calibration")
def calibration_save(payload: dict = Body(...)):
    try:
        return app_state.pipeline.set_calibration(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/calibration")
def calibration_clear():
    return app_state.pipeline.clear_calibration()


# --------------------------------------------------------------------------- simulation
@app.get("/api/simulation/scenarios")
def simulation_scenarios():
    return {"scenarios": scenario_library(), "demo_scenarios": demo_scenarios(),
            "demo_scenario_ids": demo_scenario_ids(), "current": app_state.engine.scenario.id}


@app.get("/api/simulation/state")
def simulation_state():
    return app_state.engine.state()


@app.post("/api/simulation/control")
def simulation_control(payload: dict = Body(...)):
    action = str(payload.get("action", ""))
    scenario_id = payload.get("scenario_id")
    engine = app_state.engine
    if action == "start":
        engine.start()
    elif action == "stop":
        engine.stop()
    elif action == "pause":
        engine.pause()
    elif action == "resume":
        engine.resume()
    elif action == "reset":
        engine.reset(scenario_id)
    elif action == "scenario":
        if not scenario_id:
            raise HTTPException(status_code=400, detail="scenario_id is required")
        engine.set_scenario(str(scenario_id))
    elif action:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    if "speed" in payload:
        engine.set_speed_multiplier(float(payload["speed"]))
    if "quality" in payload:
        engine.set_quality(str(payload["quality"]))
    if "difficulty" in payload:
        engine.set_difficulty(str(payload["difficulty"]))
    return engine.state()


@app.post("/api/simulation/scenario")
def simulation_scenario(payload: dict = Body(...)):
    scenario_id = str(payload.get("scenario_id", ""))
    app_state.engine.set_scenario(scenario_id)
    return {"status": "ok", "scenario_id": app_state.engine.scenario.id,
            "state": app_state.engine.state()}


# --------------------------------------------------------------------------- evaluation
@app.get("/api/evaluation/report")
def evaluation_report():
    return app_state.engine.evaluation_report()


@app.post("/api/evaluation/export")
def evaluation_export():
    report = app_state.engine.evaluation_report()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUTS_DIR / f"evaluation_{stamp}.json"
    md_path = OUTPUTS_DIR / f"evaluation_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    return {"status": "ok", "json_file": str(json_path), "markdown_file": str(md_path),
            "download_json": "/api/evaluation/download?format=json",
            "download_markdown": "/api/evaluation/download?format=md",
            "report": report}


@app.get("/api/evaluation/comparison")
def evaluation_comparison_latest():
    report = latest_comparison()
    if report is None:
        return {"available": False,
                "message": "No comparison run recorded yet. Use POST /api/evaluation/comparison to run all demo scenarios."}
    return {"available": True, "report": report}


@app.post("/api/evaluation/comparison")
async def evaluation_comparison_run(payload: dict = Body(default={})):
    ids = payload.get("scenario_ids")
    max_steps = int(payload.get("max_steps", 3600))
    try:
        report = await asyncio.to_thread(run_comparison, ids, max_steps, 1.0 / 30.0)
        files = await asyncio.to_thread(write_comparison, report)
        return {"status": "ok", "files": files, "report": report}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/evaluation/download")
def evaluation_download(format: str = "json"):
    report = app_state.engine.evaluation_report()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if format == "md" or format == "markdown":
        return Response(content=markdown_report(report), media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="sih26037_evaluation_{stamp}.md"'})
    return Response(content=json.dumps(report, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="sih26037_evaluation_{stamp}.json"'})


# --------------------------------------------------------------------------- websockets
@app.websocket("/ws/telemetry")
async def telemetry_websocket(ws: WebSocket):
    await app_state.add_telemetry_client(ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong", "timestamp": now_iso()})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        app_state.remove_telemetry_client(ws)


@app.websocket("/ws/phone/{token}")
async def phone_websocket(ws: WebSocket, token: str):
    peer_id = ws.query_params.get("peer_id")
    transport = ws.query_params.get("transport", "mjpeg_websocket")
    session = app_state.pairing.validate(token, peer_id=peer_id, bind=True)
    await ws.accept()
    if not session:
        await ws.send_json({"type": "error", "message": "Invalid, expired, revoked or already-bound pairing token"})
        await ws.close(code=4401)
        return
    old = app_state.register_phone_socket(token, ws, peer_id, transport)
    if old is not None and old is not ws:
        try:
            await old.close(code=4400)
        except Exception:
            pass
    await ws.send_json({"type": "paired", "token_valid": True,
                        "server_time": time.time(), "message": "Authenticated control channel"})
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Expected JSON message"})
                continue
            await app_state.handle_phone_message(token, ws, data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        app_state.pairing.set_error(token, f"WebSocket error: {exc}")
    finally:
        app_state.unregister_phone_socket(token, ws)
