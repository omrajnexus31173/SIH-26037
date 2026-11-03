# Troubleshooting

## First checks

```bat
cd /d "%USERPROFILE%\Downloads\sih-26037"
.venv\Scripts\python.exe -m compileall -q backend
.venv\Scripts\python.exe scripts\check_windows_bat.py --static
.venv\Scripts\python.exe scripts\download_models.py
.venv\Scripts\python.exe scripts\run_tests.py
cd frontend
npm run typecheck
npm run build
cd ..
```

With the servers running:

```bat
curl.exe -k http://127.0.0.1:8000/api/health
.venv\Scripts\python.exe scripts\live_integration_check.py
```

## Symptoms and fixes

| Symptom | Cause / fix |
|---|---|
| `setup_windows.bat` says Python or Node missing | Install Python 3.10–3.13 with “Add python.exe to PATH” and Node.js 18+ LTS; reopen Command Prompt |
| `. was unexpected at this time.` immediately after `[OK] Python ...` | Older `setup_windows.bat` contained an unescaped `)` inside `echo ... (LTS recommended).` in an `if (...)` block. Fixed in the current ZIP: replace the archive and rerun `setup_windows.bat`. The failed parse aborted before `.venv` was created. |
| `npm install` fails | Check internet/proxy, delete `frontend\node_modules`, rerun `npm install`; Node 20 is verified in this workspace |
| `ModuleNotFoundError: qrcode` or `aiortc` | Install `requirements.txt` and `requirements-webrtc.txt` into `.venv` |
| ONNX model missing / hash mismatch | Run `.venv\Scripts\python.exe scripts\download_models.py`; it verifies bundled SHA-256 and downloads only if needed |
| Backend health does not return 200 | Wait for ONNX load; inspect the backend command window; ensure port 8000 is free |
| Dashboard is blank | Confirm Vite is on 5173, then run `npm run typecheck` and `npm run build`; open browser console for exact error |
| Dashboard says telemetry offline | Backend may still be starting; WebSocket hook retries with backoff. Confirm `/api/health`; click **Retry** in topbar |
| `http://192.168.x.x` phone page cannot open camera | Android requires HTTPS on LAN IPs. Set `SIH_USE_HTTPS=1`, trust `certs\sih-26037.crt`, reopen QR link over HTTPS |
| QR URL contains `localhost` | Do not scan on a separate phone. Open dashboard from the laptop LAN IP and choose the LAN-IP candidate in Camera Connection |
| Token invalid/expired | Click **Regenerate QR**; tokens are intentionally short-lived and single-peer |
| WebRTC fails | The `/pair` page automatically falls back to authenticated MJPEG/WebSocket. Check transport/FPS/RTT in Camera Connection |
| No phone frames after scanning | Confirm same Wi-Fi/LAN, firewall allows ports 5173/8000, certificate is trusted, and camera permission was granted |
| USB phone visible only in File Explorer | That is MTP, not a camera stream. Use ADB reverse + IP Webcam, UVC-capable device, or Wi-Fi QR |
| OpenCV index finds no frames | Try indices 0–4, close other camera apps, check Windows camera privacy settings, run device probe |
| IP Webcam URL fails | Verify the exact `/video` or RTSP URL from the phone app; test it in a browser/VLC; backend validates scheme/host before opening |
| Upload rejected | Use `.mp4/.avi/.mov/.mkv/.m4v/.webm`, keep under `SIH_MAX_UPLOAD_MB` (default 200 MB) |
| Synthetic source shows a warning | Expected: synthetic frames are labelled NOT a real camera and are for software verification only |
| Very low FPS / high latency | CPU-only TwinLiteNet is heavier; lower AI/Camera FPS in System Controls, use Low quality, or enable optional CUDA only if actually available |
| Segmentation says cached | Real TwinLiteNet masks are computed every third processed frame and reused in between; `cached` is reported explicitly, not hidden |
| Physical distance seems wrong | Without calibration there is no physical distance claim. Supply real checkerboard intrinsics/height/pitch; estimates still assume a flat road |
| Report values are null | `null`/`—` means no measured event sample; the system does not invent a value |
| Port already in use | Change `SIH_BACKEND_PORT` / `SIH_FRONTEND_PORT` in `.env`, or close the conflicting process |
| `stop_project.bat` leaves a port listener | It intentionally avoids killing arbitrary PIDs; use Task Manager or `netstat -ano` to identify the owner |

## Log locations / outputs

- Backend and Vite logs appear in their spawned command windows.
- `outputs/live_integration_latest.json` records the last live process integration run.
- `outputs/evaluation_*.json/.md` are generated real reports.
- `outputs/scenario_comparison_latest.json/.md` are generated measured comparisons.
- `docs/TEST_RESULTS.md` records executed validation from this workspace.

## Windows script validation

`setup_windows.bat`, `start_project.bat` and `stop_project.bat` are written for Windows 10 `cmd.exe`. Full Windows execution was not performed here. Their syntax is checked by `scripts/check_windows_bat.py --static`; the user ran that check on Windows 10 and reported `STATIC_CHECK_OK 3 files`, and stubbed copies were also parsed successfully by Wine `cmd.exe` via `--wine`. Their commands are mirrored in `README.md` and were individually validated here using Python/npm/uvicorn/Vite equivalents.

## Netlify deployment

| Symptom | Fix |
|---|---|
| Yellow `Deployment configuration required` banner | Deploy the backend first, then edit `netlify/site/runtime-config.js` (set `configured: true`) or set `VITE_BACKEND_URL` / `VITE_FRONTEND_ORIGIN` and redeploy |
| No backend URL yet | Follow `deploy/netlify/BACKEND_FIRST.md`; do not use `http://localhost:8000` or publish with placeholders |
| REST returns 404 on the Netlify origin | Configure an absolute external backend origin; Netlify does not host `/api` |
| WebSocket fails or is pending | Use direct `wss://your-backend.example.com/ws/...`; Netlify redirects cannot proxy WebSockets |
| Mixed-content / insecure WebSocket error | Put the backend behind HTTPS/WSS; do not use plain HTTP from an HTTPS Netlify site |
| `/pair` 404 on refresh | Deploy `_redirects` or keep the `[[redirects]]` rule in `netlify.toml` |
| QR URL shows localhost or a placeholder | Set `VITE_FRONTEND_ORIGIN`/runtime `frontendOrigin` to the public Netlify HTTPS origin |
| Backend `PORT` ignored on PaaS | `backend/config.py` accepts `SIH_BACKEND_PORT`, then `PORT`, then 8000; use `deploy/backend/start.sh` if needed |

See `docs/NETLIFY_DEPLOYMENT.md` and `deploy/backend/README.md` for exact commands.
