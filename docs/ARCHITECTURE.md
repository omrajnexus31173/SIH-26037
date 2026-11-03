# Architecture

## System overview

SIH-26037 is split into a Python backend that owns all authoritative state and a React frontend that visualizes/controls that state. The browser never invents detections, camera status, planning results or evaluation metrics.

```text
Camera/Video/Simulation ground truth
        ↓
Frame normalization (640×360)
        ↓
YOLOv8n ONNX detection → TwinLiteNet ONNX segmentation → CentroidTracker
        ↓
Obstacle conversion (explicit measurement basis)
        ↓
Shared AdaptivePlanner (A*) + shared SafetyMonitor
        ↓
Annotated frame / simulation state / MetricsRecorder
        ↓
REST + WebSocket telemetry → React dashboard + R3F scene
```

## Backend modules

| Path | Responsibility |
|---|---|
| `backend/main.py` | FastAPI app, lifespan, REST endpoints, MJPEG stream, QR PNG, WebRTC offer, telemetry/phone WebSockets, report downloads |
| `backend/state.py` | `AppState`, simulation/broadcast/system loops, config application, telemetry snapshot, phone message handling |
| `backend/config.py` | Environment-driven settings, paths, LAN IP helpers, ports, FPS/model/threshold defaults |
| `backend/pipeline.py` | Real frame → detection → segmentation → tracking → obstacles → planner → safety → annotated frame → result |
| `backend/perception/` | YOLOv8n ONNX detector, optional Ultralytics adapter, COCO labels, optional flat-ground calibration |
| `backend/segmentation/road.py` | TwinLiteNet ONNX drivable-area/lane segmentation and labelled heuristic fallback |
| `backend/tracking/tracker.py` | IoU/centroid Hungarian assignment, velocity, direction, scale-rate and trails |
| `backend/planning/` | `Obstacle`/`PlanResult`, occupancy/cost grid, A*, adaptive planner, smoothing and alternative route |
| `backend/safety/safety.py` | TTC, risk score, risk zones, safe speed, emergency stop and planner override |
| `backend/simulation/` | Scenario specs, deterministic world/actors, authoritative engine, pure-pursuit ego motion |
| `backend/evaluation/` | Event-derived metrics and measured headless scenario comparison/report writers |
| `backend/camera/` | Pairing tokens, camera sources, upload/USB/IP/video/synthetic ingestion, Windows PnP diagnostics, aiortc receiver |
| `backend/tests/` | Formal pytest suite |

## Frontend modules

| Path | Responsibility |
|---|---|
| `frontend/src/App.tsx`, `main.tsx` | Route `/pair` to the mobile page; otherwise mount dashboard |
| `frontend/src/components/Layout.tsx` | Responsive sidebar/topbar and section metadata |
| `frontend/src/pages/dashboard/` | Nine dashboard views wired to real REST/WebSocket state |
| `frontend/src/pages/PairPage.tsx` | Android camera permission, rear/front selector, WebRTC offer/ICE, authenticated MJPEG fallback, RTT/status |
| `frontend/src/simulation/` | R3F canvas, procedural road/props/vehicles, path/risk visuals, camera rig |
| `frontend/src/components/` | Camera feed, A* grid, safety, analytics, evaluation, calibration and reusable UI/charts |
| `frontend/src/camera/` | QR pairing panel, source controls, USB diagnostics |
| `frontend/src/services/` | Typed REST wrappers and WebSocket URL helpers using relative URLs |
| `frontend/src/hooks/useTelemetry.ts` | Reconnecting telemetry WebSocket with backoff and measured sample history |

## Shared planner and safety

Both the real camera pipeline and simulation engine instantiate the same `AdaptivePlanner` and `SafetyMonitor` classes. The camera path uses explicitly labelled `uncalibrated_monocular_image_plane_proxy` coordinates; the simulation path uses `simulation_metric_m` coordinates. The frontend never conflates the two.

## Control and telemetry

- REST: `/api/config`, `/api/simulation/{scenarios,state,control,scenario}`, `/api/camera/*`, `/api/pairing/*`, `/api/webrtc/*`, `/api/models/*`, `/api/calibration`, `/api/evaluation/*`.
- WebSocket: `/ws/telemetry` broadcasts authoritative snapshots; `/ws/phone/{token}` accepts token-authenticated hello/ping/status/frame/latency/disconnect messages.
- Vite proxies `/api` and `/ws` to uvicorn; browser code uses relative URLs, never `localhost` calls to another host.

## Camera security model

- Pairing tokens expire, are rotatable and bind to one peer.
- Every phone WebSocket and WebRTC offer validates the token.
- QR URLs are generated from reachable origins; localhost is labelled "laptop only".
- Android camera APIs require HTTPS on a LAN IP (or localhost on the same machine).
- MTP/PTP file transfer is never treated as a video source.

## Measurement basis

- Simulation: metric metres, ground-truth actors and measured engine events.
- Real camera: pretrained detections are real; distances/TTC are image-plane/optical proxies unless calibration is supplied.
- Calibration: flat-ground inverse perspective, explicitly labelled `estimate_only_not_ground_truth`.
- Evaluation: null values mean no measured sample; no benchmark numbers are invented.

## Deployment runtime configuration

For local development, `runtime-config.js` leaves `backendUrl` empty and the Vite proxy handles same-origin `/api` and `/ws` paths. For Netlify, `frontend/scripts/build-netlify.mjs` writes absolute origins into `runtime-config.js` from `VITE_BACKEND_URL` and `VITE_FRONTEND_ORIGIN` before building `netlify/site`.

`apiUrl()` and `wsUrl()` in `frontend/src/config/runtime.ts` rewrite all REST, QR, MJPEG, snapshot, download and WebSocket URLs. `frontendOrigin()` is used for QR/pairing links. A remote HTTPS site with an empty or placeholder backend URL shows a visible configuration warning rather than silently pretending the backend is connected.

Netlify serves only the static site; the authoritative backend state remains on a separate always-on host.
