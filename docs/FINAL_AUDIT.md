# SIH-26037 Final Feature Audit

Date: 2026-11-03 (Asia/Calcutta). Workspace: `/home/user/sih-26037`. This audit reflects source inspection plus tests actually executed in this workspace. It does not assume that source existence equals working behavior.

Classes used: **1** implemented and verified; **2** implemented but not verified here; **3** partially implemented; **4** missing; **5** requires physical hardware or external credentials.

## A. Backend, API and state

| Feature | Class | Evidence / limitation |
|---|---|---|
| FastAPI application, lifespan startup/shutdown | 1 | `backend/main.py`, 45 REST routes, 2 WebSocket routes; TestClient and live uvicorn checks passed. |
| Health, config, system status endpoints | 1 | Covered by pytest and 18/18 live integration. |
| CORS middleware | 1 | `allow_origins=["*"]`, `allow_credentials=False`, methods/headers `*`; REST verified. |
| In-memory authoritative state | 1 | `backend/state.py`; no database integration exists. |
| REST simulation control/scenarios/state | 1 | pytest + live integration; scenario/control/state responses verified. |
| Evaluation report/export/download/comparison | 1 | pytest + live integration; Markdown/JSON downloads and comparison POST verified. |
| Calibration save/read/clear | 1 | pytest; explicitly labelled flat-ground estimate, never ground truth. |
| Model/detector status endpoints | 1 | pytest + live integration; bundled ONNX hashes verified. |
| Configuration reload via `/api/config` | 1 | historical live TestClient checks; no secret config required. |
| Authentication / user accounts | 4 | Not in original scope; no login system. Pairing tokens are the only access control. |
| Database integration | 4 | None required or implemented; state is in-memory plus report files. |

## B. Computer vision / AI

| Feature | Class | Evidence / limitation |
|---|---|---|
| YOLOv8n ONNX detection via OpenCV DNN CPU | 1 | Real sample-image inference: 5 detections; model SHA-256 verified. |
| TwinLiteNet ONNX drivable-area/lane segmentation | 1 | Real inference; logits softmax, cached masks labelled, SHA-256 verified. |
| IoU/centroid tracking with IDs, velocity, trails | 1 | pytest + pipeline runs; annotated-frame overlays. |
| Shared perception pipeline for camera and simulation | 1 | `backend/pipeline.py`, obstacles/plan/safety share types; pytest. |
| Optional CUDA / Ultralytics / ONNXRuntime | 2 | Guarded runtime detection; GPU hardware unavailable, CPU default verified. |
| Physical-distance accuracy from camera | 5 | Requires real calibration, known intrinsics, ground-plane assumptions and physical measurement. Uncalibrated values are image-plane proxies only. |

## C. Camera, pairing and media

| Feature | Class | Evidence / limitation |
|---|---|---|
| Camera source catalog and selection | 1 | pytest + live integration; `CameraControls.tsx` calls real select/disconnect endpoints. |
| Synthetic test pattern | 1 | pytest + live integration; explicitly labelled NOT a real camera. |
| Video upload and bundled demo clip | 1 | pytest + live integration; upload path, MJPG AVI, sample-derived demo clip. |
| MJPEG stream and JPEG snapshot | 1 | Live integration checked PNG/JPEG magic bytes and proxy paths. |
| QR pairing session, validation, regeneration, expiry | 1 | pytest + live integration; tokenized single-peer sessions. |
| Telemetry WebSocket | 1 | pytest + live integration, direct backend and frontend proxy. |
| Phone control WebSocket with frames/hello/ping/disconnect | 1 | pytest + live integration with synthetic JPEG frames. |
| WebRTC signalling / invalid-SDP handling | 2 | `aiortc` imports and invalid-offer rejection verified; no valid SDP/ICE media exchange. |
| Phone camera via QR/Wi-Fi | 5 | Requires Android phone, camera permission, trusted HTTPS, real network. |
| USB/UVC camera | 5 | Requires UVC hardware; OpenCV index path implemented. Windows PnP diagnostics skip on Linux. |
| ADB reverse + IP Webcam | 5 | Requires ADB, phone app and USB/network setup. |
| IP webcam / RTSP | 5 | Requires a reachable stream URL. |
| Laptop webcam | 5 | No webcam in sandbox. |
| HTTPS certificate trust on phone | 5 | Requires manual browser trust; generated private key excluded. |

## D. Planning, safety, simulation and 3D

| Feature | Class | Evidence / limitation |
|---|---|---|
| A* occupancy-grid planner, smoothing, alternative route | 1 | pytest, measured latency/smoothness/clearance, headless runs. |
| SafetyMonitor, TTC, risk zones, emergency stop | 1 | pytest; distinguishes metric simulation TTC from optical scale-rate camera TTC. |
| 13 scenarios / 10 demo scenarios / difficulty actuator | 1 | pytest and live integration; difficulty scaling verified. |
| Headless collision-avoidance runs | 1 | 10×3000 and 13×3600 steps at 1/30 s with zero collisions in measured runs; simulation only. |
| Measured metrics/history/evaluation | 1 | Event-derived only; null means no sample. |
| R3F 3D simulation from authoritative backend state | 2 | TypeScript build/typecheck pass and state shape is wired; no browser DOM/WebGL screenshot executed here. |
| Procedural vehicles/road/props, camera modes, quality | 2 | Source and production build verified; visual rendering not browser-inspected. |
| Real-road autonomous driving | 4 | Explicitly out of scope; research prototype only. |

## E. Frontend, routing and deployment

| Feature | Class | Evidence / limitation |
|---|---|---|
| React/Vite/TypeScript/Tailwind command-center shell | 2 | `npm ci`, typecheck and production build pass; no browser console/DOM inspection available. |
| Nine dashboard views / responsive layout | 2 | Source, imports and build verified; visual responsiveness not browser-inspected. |
| `/pair` mobile route | 1 | `App.tsx` routing plus live `/pair` HTTP check; SPA `_redirects` added for Netlify. |
| Reconnecting telemetry hook | 1 | Live WebSocket integration; explicit disconnected/error states. |
| Runtime backend URL/WS configuration | 1 | `runtime.ts`, `api.ts`, `socket.ts`, `PairingPanel.tsx`; typecheck, build and deployment tests pass. |
| Netlify production static build | 1 | `build:netlify` produced `netlify/site` with 2,977 modules, assets, `_redirects`, `_headers`, `runtime-config.js`. |
| Netlify SPA fallback on nested-route refresh | 2 | `_redirects` and `netlify.toml` verified as files; live Netlify behavior requires an actual account/deploy. |
| Production preview with API/WS proxy | 1 | `vite.config.ts` preview proxy added; preview integration checks executed. |
| CameraControls.tsx | 1 | Real source selection, upload, status from telemetry, no fake connection claims; TypeScript build passes. |
| CalibrationPanel.tsx | 1 | Real GET/POST/DELETE calibration calls, explicit estimate caveats; TypeScript build passes. |
| Offline/error handling | 1 | `ApiError` network wrapper, WebSocket reconnect state, warning banner for unconfigured backend. |
| Actual Netlify deployment / public DNS | 5 | Requires a Netlify account and user-side publish; not executed in this sandbox. |
| External always-on backend host | 5 | Requires Render/Railway/Fly/VPS credentials; Netlify cannot host Python/WebSockets. |
| Browser console / visual screenshot verification | 5 | No browser automation or physical display available here; explicitly not claimed. |

## F. Security and packaging

| Feature | Class | Evidence / limitation |
|---|---|---|
| Pairing token expiry and single-peer binding | 1 | Backend logic + pytest. |
| Token validation on phone WS and WebRTC offers | 1 | pytest rejects unauthorized token and invalid SDP. |
| No credentials/secrets/private keys in delivery ZIPs | 1 | Packaging scripts exclude `.env`, `*.key`, caches, `node_modules`; integrity verification rechecks. |
| Public certificate included, private key excluded | 1 | `certs/sih-26037.crt` present; `.key` absent. |
| Offline Python wheel cache | 3 | 47 resolved Linux wheels measured 184 MB; lockfile and downloader included, full wheel bundle omitted for delivery-size practicality. |
| npm lockfile | 1 | `frontend/package-lock.json` included; `npm ci` executed. |
| Windows local launchers | 2 | Static/Wine checks and user Windows 10 static check pass; full setup/start/stop not rerun here. |
| Model download/setup instructions | 1 | `scripts/download_models.py`, `models/README.md`, notices and hashes included. |
| Complete deployment documentation | 1 | `ENVIRONMENT_VARIABLES.md`, `DEPLOYMENT.md`, `docs/NETLIFY_DEPLOYMENT.md`, backend/host guides included. |

## G. Overall conclusion

The software is complete and verified at the level possible in this Linux sandbox: backend compilation/imports, 32 formal tests, real ONNX inference, REST/WebSocket integration, TypeScript typecheck, two production builds, 18/18 live integration and 20/20 production preview checks, plus three ZIP integrity/extraction/secret scans. Hardware-dependent features, a live Netlify account, an external backend host, valid WebRTC media, phone certificate trust and browser visual/console inspection require user-side hardware/credentials and are explicitly classified **5**, not falsely reported as verified.
