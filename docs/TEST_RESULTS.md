# SIH-26037 Test Results

All results below were executed in this workspace on **2026-11-02**, with the Windows launcher regression fix, Netlify deployment packaging and revalidation on **2026-11-03** (Asia/Calcutta), except for the explicitly labelled user-reported Windows 10 static check. Hardware-dependent, Windows-only and external-host items are explicitly listed as not executed; no result is fabricated.

## Environment actually used

| Component | Measured value |
|---|---|
| Python | `3.13.16` |
| Node.js | `v20.20.2` |
| npm | `10.8.2` |
| OpenCV | `4.11.0.86` |
| NumPy | `2.3.5` |
| SciPy | `1.17.1` |
| FastAPI | `0.162.0` |
| pytest | `9.0.3` |
| httpx | `0.28.1` |
| aiortc | `1.15.0` |
| OpenSSL | `3.5.7` |
| Wine cmd.exe parser | `10.0~repack-6` (Linux parser check only; not Windows 10) |
| User-reported Windows 10 cmd.exe | `10.0.19045.7417` (static launcher check only; not full setup/start/stop) |
| FastAPI routes | `45` |

`ffmpeg` is not installed in the sandbox; the demo clip was generated with OpenCV `VideoWriter`.

---

## 1. Backend compile and imports

Command:

```bash
python3 -m compileall -q backend
python3 -c "from backend.main import app; print(len(app.routes))"
```

Result: **PASS**, `COMPILEALL_OK`, `45` routes. Import included pairing validation, calibration GET/POST/DELETE, comparison GET/POST, `/ws/telemetry` and `/ws/phone/{token}`.

## 2. Bundled models and assets

Command:

```bash
python3 scripts/download_models.py
```

Result: **PASS**

- `models/yolov8n.onnx`: SHA-256 `65158dad735be799c2466fa15e260c09558080bd530b42a8d0c3d1b419afd8b5` verified.
- `models/twinlitenet_da.onnx`: SHA-256 `f505b56bd7c9e4e38b2928373aa4daa191a9a398e07e1fb340024b9ce84d4285` verified.
- `assets/sample_road.jpg` exists.
- `assets/demo_drive.avi` exists, generated with OpenCV, 90 frames at 15 fps.

Real model smoke test in pytest loaded both ONNX models via OpenCV DNN, ran YOLO on `sample_road.jpg`, produced ≥1 real detection, and confirmed TwinLiteNet source `twinlitenet-onnx`.

## 3. HTTPS certificate

Command:

```bash
python3 scripts/generate_cert.py
openssl x509 -in certs/sih-26037.crt -noout -text | grep -A1 'Subject Alternative Name'
```

Result: **PASS**. Sandbox certificate SAN:

```text
DNS:localhost, DNS:e2b.local, IP Address:127.0.0.1, IP Address:169.254.0.21
```

The Windows setup regenerates the certificate for the actual laptop LAN IP. The `.key` is excluded from the ZIP.

## 4. Formal pytest suite

Command:

```bash
python3 scripts/run_tests.py
```

First run: 21 passed, 2 failed (23 total); the two failures were overly strict assertions, not product defects. They were fixed to match real backend contracts:

- `PerceptionPipeline.process_frame()` normalizes frames to `640×360`, so annotated output is `(360,640)` and `resolution=[640,360]`.
- Calibration basis is `calibrated_flat_ground_inverse_perspective`; the estimate caveat is in `note`.

Second run: **23/23 PASS**, `PYTEST_EXIT 0`. After adding the Windows launcher regression tests and fixing a real per-source camera counter reset issue, the suite returned **25/25 PASS**. After adding four Netlify deployment artifact tests, the final run returned **32/32 PASS**, `PYTEST_EXIT 0`. Final collection breakdown:

- `test_10_core.py`: 11 tests
- `test_20_api.py`: 5 tests
- `test_30_websockets.py`: 4 tests
- `test_40_camera.py`: 3 tests
- `test_50_windows_launchers.py`: 2 tests
- `test_60_deployment.py`: 4 tests
- `test_70_delivery.py`: 3 tests

Coverage executed: module imports, model hashes/assets, A* planner, SafetyMonitor, centroid tracker, optional calibration, MetricsRecorder, 10 required scenario names, engine difficulty scaling, headless comparison, real YOLO/TwinLiteNet/Pipeline inference, health/system/config/models, calibration save/clear, scenario/control/difficulty/quality/speed REST endpoints, pairing session/QR/regeneration/validation/redirect, evaluation report/export/downloads/comparison POST, telemetry WebSocket, authenticated phone WebSocket with hello/ping/frame/disconnect, unauthorized phone token rejection, WebRTC invalid-offer fallback error, camera catalog/device probe, synthetic and video frame ingestion, JPEG snapshot, video upload and disconnect, plus Windows launcher static syntax and known-bad-echo regression detection, Netlify static-site artifacts, runtime config/SPA redirect headers, backend `PORT` fallback, resolved requirements lockfile, environment-variable documentation, final audit and production-preview proxy configuration. The Wine `cmd.exe` parser probe is recorded separately in section 11.

Known nonfatal warning: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` This comes from FastAPI/TestClient, not project code.

## 5. Frontend typecheck

Command:

```bash
cd frontend && npm run typecheck
```

First run after dependency restoration found two real TypeScript issues:

1. `USBGuide.tsx`: `unknown` used directly as a JSX conditional.
2. `CalibrationPanel.tsx`: `CalibrationForm` interface not assignable to `Record<string, unknown>`.

Both were fixed. Also fixed: hidden video upload label not wired to input, and pairing panel POST-regenerating a token on every mount. Final result: **PASS**, no TypeScript errors.

## 6. Frontend production build

Command:

```bash
cd frontend && npm run build
```

First build: **PASS**, 2,975 modules, one 1,559.29 kB JS chunk, gzip 429.94 kB; Vite emitted a nonfatal chunk-size advisory. `vite.config.ts` was updated with `manualChunks` splitting.

Final build: **PASS**, 2,975 modules transformed, no chunk-size warning:

```text
dist/index.html                   1.02 kB │ gzip:   0.48 kB
dist/assets/index-DkV2TVgA.css   26.83 kB │ gzip:   5.83 kB
dist/assets/icons-BIXlE-gB.js    28.18 kB │ gzip:   5.85 kB
dist/assets/react-C822Eag7.js   146.11 kB │ gzip:  47.17 kB
dist/assets/index-CWcexs33.js   147.75 kB │ gzip:  40.53 kB
dist/assets/charts-Rd1rkV6h.js  383.96 kB │ gzip: 105.53 kB
dist/assets/three-BkeU--1U.js   849.11 kB │ gzip: 228.79 kB
```

`npm install` emitted nonfatal deprecation notices for `three-mesh-bvh@0.7.8` and `recharts@2.15.4`; the build still succeeded.

## 7. Real backend difficulty actuator

Command executed directly:

```python
eng = SimulationEngine('highway_cruising')
eng.set_difficulty('hard')
eng.reset('highway_cruising')
```

Measured result:

```text
DEFAULT medium 1.0
HARD hard 1.2 1.2
EASY_RESET_PRESERVED easy 0.8
```

This confirms difficulty changes actor motion scale and is preserved through reset. REST `/api/simulation/control` and `/api/config` tests also verified `hard → difficulty_scale 1.2`.

## 8. Live uvicorn + Vite integration

Started with:

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

Both processes reported listening on `0.0.0.0` ports `8000` and `5173`. Vite correctly restarted after `vite.config.ts` changed.

Command:

```bash
python3 scripts/live_integration_check.py
```

Result, executed three times (before and after Vite config restart, and again after the camera counter reset fix): **18/18 PASS, 0 failed each time**. Full measured JSON: `outputs/live_integration_latest.json`.

Live checks included:

- backend `/api/health`;
- dashboard HTML through Vite;
- `/api/health` through Vite proxy;
- LAN-reachable pairing URL and token validation;
- `/pair` SPA route;
- QR PNG through Vite proxy;
- simulation scenario/start/state through REST;
- full A* grid in `/api/simulation/state`;
- synthetic camera frames and JPEG snapshot through Vite proxy;
- telemetry WebSocket directly to backend and through Vite proxy with ping/pong;
- authenticated phone WebSocket through Vite proxy with paired/hello/frame/disconnect;
- WebRTC invalid-offer error through Vite proxy;
- evaluation Markdown download through Vite proxy;
- measured comparison POST;
- restoration of bundled demo video source for live preview.

Backend logs showed all proxied REST/WebSocket requests returning `200`/accepted. No preview-breaking host/origin warnings were reported.

## 9. Existing measured outputs

- `outputs/evaluation_20261102_142449.json/.md`: earlier TestClient-generated real report.
- `outputs/scenario_comparison_latest.json/.md`: generated measured comparison.
- Additional timestamped comparison files were created by pytest/live integration.
- `outputs/live_integration_latest.json`: live process check result.
- `outputs/windows_launcher_check_latest.json`: final static/Wine `cmd.exe` launcher parser check.
- `config/camera_calibration.json`: calibration was saved then cleared by the pytest suite; final state is uncalibrated.

## 10. ZIP packaging

Legacy packaging helpers remain available (`scripts/make_zip.py`, `scripts/make_deploy_zip.py`), but the final delivery uses:

```bash
python3 scripts/make_delivery_zips.py
```

It creates exactly three user-facing packages in `/home/user/`:

- `SIH-26037-NETLIFY-FRONTEND.zip` — production static site only, with a top-level `SIH-26037-NETLIFY-FRONTEND/` folder for Netlify drag-and-drop.
- `SIH-26037-COMPLETE-SOURCE.zip` — full source, production builds, models, assets, docs, tests, scripts, deployment recipes, environment templates and manifest.
- `SIH-26037-BACKEND-DEPLOY.zip` — backend-only Docker/Render/Railway/Fly/VPS package.

The packager excludes private keys, real `.env` files, Python caches, `node_modules`, wheel binaries, virtual environments and non-`.gitkeep` uploads. It writes `SHA256SUMS.txt`, `delivery/VERIFICATION.json`, `delivery/README.md` and `deploy/MANIFEST.json`. Every ZIP is tested with `zipfile.testzip()`, extracted to a clean temporary directory, structurally checked, scanned for secret-like filenames/content and hashed. Exact sizes and checksums are recorded in those generated artifacts rather than hard-coded here.

---

## 11. Windows launcher regression fix (2026-11-03)

Reported Windows 10 failure:

```text
[OK] Python 3.13.17
. was unexpected at this time.
```

Root cause: `setup_windows.bat` contained

```bat
echo [ERROR] Node.js was not found. Install Node.js 18 or newer (LTS recommended).
```

inside an `if errorlevel 1 ( ... )` block. In `cmd.exe`, the unescaped `)` in `(LTS recommended)` closes the block early, leaving the trailing `.` to be parsed as a command. The script aborts during parsing, before `[1/8] Creating Python virtual environment`, which is why `start_project.bat` subsequently reported that `.venv\Scripts\python.exe` was missing.

Fixes applied:

- Rephrased that `echo` as `LTS preferred` and removed all remaining unescaped parentheses from `echo` lines in the launchers.
- Replaced inline `python -c ... >= ...` and `node -e ... >= ...` version checks with batch-native `for /f` parsing plus `set /a` / `if LSS`, avoiding shell metacharacters inside quoted JavaScript/Python snippets.
- Added `scripts/check_windows_bat.py`, which statically scans `.bat` files for unescaped parentheses in `echo` lines inside parenthesized blocks, and can generate stubbed launcher copies for a Wine `cmd.exe` parser probe.
- Added `backend/tests/test_50_windows_launchers.py` with two pytest tests: workspace launchers pass static check, and a deliberately bad `echo ... (LTS recommended).` block is detected.
- A full-suite rerun then exposed a real product defect: `CameraHub.select()` did not reset `frame_count` / `processed_count`, so a newly selected source could inherit stale frame totals. Counters are now reset, and `wait_for_frames()` waits for `connected` plus nonzero resolution instead of stale counts.

Commands executed:

```bash
python3 scripts/check_windows_bat.py --static
python3 scripts/check_windows_bat.py --wine
python3 -m compileall -q backend
python3 scripts/run_tests.py
python3 scripts/live_integration_check.py
```

Measured results:

- `STATIC_CHECK_OK 3 files: setup_windows.bat, start_project.bat, stop_project.bat`.
- A minimal bad block reproduced the parser failure under Wine as `Syntax error: unexpected (`; Windows 10 reported the equivalent `. was unexpected at this time.`.
- `WINE_PROBE_OK`: stubbed `setup_windows_probe.bat`, `start_project_probe.bat` and `stop_project_probe.bat` all reached their completion markers with no parse errors or fail markers. Full result: `outputs/windows_launcher_check_latest.json`.
- `COMPILEALL_OK`; final `python3 scripts/run_tests.py` returned 32 dots and `PYTEST_EXIT 0` after the deployment tests were added.
- Restarted uvicorn/Vite live integration returned `18 passed, 0 failed`, rewriting `outputs/live_integration_latest.json`.

Wine `cmd.exe` is a parser-validation aid, not Windows 10.

### User-reported Windows 10 validation

The user then ran the corrected command on Windows 10 `10.0.19045.7417`:

```bat
.venv\Scripts\python.exe scripts\check_windows_bat.py --static
```

Reported output:

```text
STATIC_CHECK_OK 3 files: setup_windows.bat, start_project.bat, stop_project.bat
```

This confirms the three fixed launchers pass the static parenthesis check on the user's real Windows 10 system. It does **not** yet confirm that `setup_windows.bat`, `start_project.bat` and `stop_project.bat` were executed end-to-end there. Full Windows setup/start/stop remains the final acceptance step.

---

## 12. Netlify deployment packaging (2026-11-03)

Executed here:

- `npm ci --no-audit --no-fund` from `frontend/package-lock.json`: 245 packages, exit 0.
- `npm run typecheck`: PASS after adding runtime configuration types and the deployment warning component.
- `VITE_BACKEND_URL=https://REPLACE_WITH_BACKEND_ORIGIN VITE_FRONTEND_ORIGIN=https://REPLACE_WITH_NETLIFY_ORIGIN npm run build:netlify`: PASS, 2,977 modules transformed; produced `netlify/site/index.html`, `runtime-config.js`, `_redirects`, `_headers`, `DEPLOY_NOTICE.txt` and asset chunks. Largest chunk remained the `three` bundle at 849.11 kB / 228.79 kB gzip; no chunk-size advisory.
- A second `npm run build` restored the same-origin local `frontend/dist` build; PASS, 2,977 modules.
- `python3 -m pip download -r requirements.txt -r requirements-dev.txt -r requirements-webrtc.txt`: resolved 47 Linux wheels, 184 MB total. The wheel set is not bundled because it exceeds the practical workspace delivery cap; `deploy/requirements.lock.txt` and `scripts/download_wheels.py` reproduce it.
- `python3 scripts/check_windows_bat.py --static`: `STATIC_CHECK_OK 3 files`.
- `python3 scripts/run_tests.py`: 32 dots, `PYTEST_EXIT 0` after stopping the live servers to avoid the known constrained-memory OOM condition.
- `python3 scripts/live_integration_check.py` against the production Vite preview: `18 passed, 0 failed`; rewrote `outputs/live_integration_latest.json`.
- `python3 scripts/production_preview_check.py`: `20 passed, 0 failed`; rewrote `outputs/production_preview_latest.json`. It verified index HTML, runtime-config script, hashed assets, compiled warning/error handling, no hardcoded localhost backend, `/pair` refresh, static assets, REST/WS proxy, synthetic camera fallback and JPEG snapshot.
- `python3 scripts/make_delivery_zips.py`: created and verified the three final ZIPs; exact sizes and checksums are in `SHA256SUMS.txt` and `delivery/VERIFICATION.json`.

Netlify runtime configuration was added in `frontend/public/runtime-config.js`, `frontend/src/config/runtime.ts`, `frontend/src/services/api.ts`, `frontend/src/services/socket.ts`, `frontend/src/camera/PairingPanel.tsx` and `frontend/src/components/RuntimeConfigNotice.tsx`. `backend/config.py` now accepts the platform-provided `PORT` variable as a fallback.

---

## 13. Final delivery verification (2026-11-03)

Final mission checks executed after all fixes:

- Python dependency install, `compileall -q backend`, `py_compile` on new scripts/tests, model hash verification and Windows `.bat` static check: PASS.
- `npm ci`, `npm run typecheck`, local `npm run build`, Netlify `npm run build:netlify` with placeholder origins, and a final local `npm run build`: PASS. Both builds transformed 2,977 modules; largest `three` chunk 849.11 kB / 228.79 kB gzip, no advisory.
- `python3 -m pytest`: **32 passed, 1 nonfatal Starlette warning** in 8.42 s. Collection: 11 core, 5 API, 4 WebSocket, 3 camera, 2 Windows launcher, 4 deployment, 3 final delivery.
- Production Vite preview on `0.0.0.0:4173` with real uvicorn backend on `0.0.0.0:8000`: live integration **18/18**, production preview **20/20**.
- `scripts/make_delivery_zips.py`: three ZIPs generated, `zipfile.testzip()` clean, clean extraction, required structures present, secret/private-key/cache/node_modules/wheel scan clean, SHA-256 checksums generated.

---

## Not executed in this Linux sandbox (honest exclusions)

- Physical Android phone camera pairing, rear/front permission UI, trusted self-signed certificate UI, and a valid end-to-end WebRTC SDP/ICE media flow.
- Physical USB/UVC camera, laptop webcam and Windows Device Manager hardware behavior.
- Full Windows 10 `cmd.exe` execution of `setup_windows.bat`, `start_project.bat` and `stop_project.bat`; the static launcher checker was run by the user on Windows 10, but full setup/start/stop execution remains unverified.
- An actual Netlify account/deployment, DNS/domain configuration, external always-on backend host, public HTTPS/WSS connection from a real browser, browser console/DOM automation, and phone certificate-trust interaction.
- Optional NVIDIA/CUDA acceleration; default CPU-only OpenCV DNN was used.
- Real-road driving, production vehicle safety validation or physical distance accuracy.

Software substitutes actually executed: TestClient phone WebSocket frames, synthetic frames, generated sample-derived video, QR/token/reachability APIs, WebRTC invalid-offer handling, aiortc import/status, OpenCV model inference, REST/WebSocket proxy integration, headless simulation events, stubbed Windows launcher parsing through Wine `cmd.exe`, and the user-reported Windows 10 static launcher check. Also executed: a Netlify-targeted production build with placeholder runtime configuration, SPA redirects, no-cache runtime headers, a Vite production preview with REST/WebSocket proxy, 20 production-preview checks, Docker/Render/Fly/Procfile deployment recipes, resolved offline wheel metadata, three deployment ZIPs, per-ZIP extraction/secret scans, a deployment manifest and SHA-256 checksums. These are reported as software integration and packaging, not as a live Netlify deployment or hardware verification.
