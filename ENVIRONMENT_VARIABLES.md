# SIH-26037 Environment Variables and External Credentials

This is the complete inventory for the existing project. No value below is a real secret. The project has **no database**, no OAuth provider, no paid API key and no cloud-storage credential. Pairing tokens are generated at runtime by the backend. The TLS private key is generated locally and is deliberately excluded from all delivery ZIPs.

Legend: **B** = build time, **R** = runtime, **Secret?** = must never be committed or shipped.

## 1. Frontend / Netlify

| Variable | B/R | Required? | Where to obtain value | Dashboard / file | Secret? | Purpose |
|---|---|---|---|---|---|---|
| `VITE_BACKEND_URL` | B (also read at runtime as fallback) | **Yes for Netlify** | Public HTTPS origin of the separately deployed FastAPI backend, e.g. `https://sih26037-backend.onrender.com` | Netlify → Site configuration → Environment variables; or `netlify/site/runtime-config.js` for drag-and-drop | No | Absolute REST/QR/MJPEG/WebSocket backend origin. No trailing slash. |
| `VITE_FRONTEND_ORIGIN` | B (also read at runtime as fallback) | **Yes for Netlify** | Netlify site origin, e.g. `https://your-site.netlify.app`; use the deploy-preview URL before publishing | Netlify → Environment variables; or `runtime-config.js` | No | QR/pairing links and phone-facing frontend origin. No trailing slash. |
| `URL` | B | Optional | Automatically provided by Netlify during builds | Netlify build environment | No | Fallback for `VITE_FRONTEND_ORIGIN` in `frontend/scripts/build-netlify.mjs`. |
| `NODE_VERSION` | B | Optional | Set to `20` in `netlify.toml` | `netlify.toml` | No | Pins Node for reproducible Netlify builds. |
| `NPM_FLAGS` | B | Optional | Set to `--no-audit --no-fund` in `netlify.toml` | `netlify.toml` | No | Speeds up `npm ci`. |
| `SIH_USE_HTTPS` | B | Optional, local Vite only | `1`/`true` enables Vite HTTPS when cert/key exist | local `.env`, `frontend/.env` | No | Local LAN phone-camera secure context. |
| `SIH_USE_HTTP` | B | Optional, local Vite only | Any non-empty value forces Vite HTTP even if `SIH_USE_HTTPS=1` | local `.env`, `frontend/.env` | No | Emergency local override. |
| `SIH_BACKEND_PORT` | B | Optional, local Vite only | Default `8000` | local `.env`, `frontend/.env` | No | Vite dev/preview proxy target port. |
| `SIH_FRONTEND_PORT` | B | Optional, local Vite only | Default `5173` | local `.env`, `frontend/.env` | No | Vite dev/preview listen port. |

For **Netlify drag-and-drop**, the build-time variables are not read after upload. Edit `netlify/site/runtime-config.js` instead:

```js
window.__SIH_RUNTIME_CONFIG__ = {
  backendUrl: "https://YOUR_PUBLIC_BACKEND_ORIGIN",
  frontendOrigin: "https://YOUR_NETLIFY_SITE_ORIGIN",
  configured: true,
};
```

Never use `http://localhost:8000` from a deployed Netlify HTTPS site; browsers block mixed content and the phone cannot reach the developer's PC.

## 2. Backend / Python host

| Variable | B/R | Required? | Where to obtain value | Dashboard / file | Secret? | Purpose |
|---|---|---|---|---|---|---|
| `PORT` | R | Often required by PaaS | Automatically injected by Render/Railway/Fly/Heroku-style hosts | Backend host dashboard | No | `backend/config.py` uses it when `SIH_BACKEND_PORT` is absent. |
| `SIH_BACKEND_PORT` | R | Optional, default `8000` | Choose an open port; use `8000` for Docker | `.env`, Docker Compose, `deploy/backend/start.sh` | No | Uvicorn listen port; overrides `PORT`. |
| `SIH_HOST` | R | Optional, default `0.0.0.0` | Use `0.0.0.0` on containers/hosts | `.env`, Docker Compose, Render | No | Bind address. |
| `SIH_FRONTEND_PORT` | R | Optional, default `5173` | Local Windows launcher only | `.env`, `start_project.bat` | No | Local Vite port; not needed on Netlify. |
| `SIH_USE_HTTPS` | R | Optional, default `0` | Set `1` only for local LAN HTTPS with a trusted/generated cert | `.env`, Windows launcher | No | Enables uvicorn/Vite TLS locally. Behind Render/Railway/Fly, the platform terminates TLS and this stays `0`. |
| `SIH_PUBLIC_PAIR_BASE_URL` | R | Optional | Public HTTPS URL that phones should open for `/pair`, e.g. `https://your-site.netlify.app` | Backend host env vars | No | Adds an explicit reachable QR candidate. The frontend already sends `frontend_origin`, so this is usually unnecessary. |
| `SIH_AI_FPS` | R | Optional, default `8` | Tune to CPU capacity | Backend env | No | AI worker target rate. |
| `SIH_CAMERA_FPS` | R | Optional, default `20` | Tune to source | Backend env | No | Capture target rate. |
| `SIH_SIM_FPS` | R | Optional, default `20` | Tune to CPU capacity | Backend env | No | Simulation tick rate. |
| `SIH_BROADCAST_FPS` | R | Optional, default `8` | Tune to bandwidth/CPU | Backend env | No | Telemetry broadcast rate. |
| `SIH_PAIRING_TTL` | R | Optional, default `900` | Seconds before a pairing token expires | Backend env | No | Single-peer token lifetime. |
| `SIH_MAX_UPLOAD_MB` | R | Optional, default `200` | Choose according to host disk/memory | Backend env | No | Video upload limit. |
| `SIH_YOLO_MODEL` | R | Optional, default `yolov8n.onnx` | Bundled file name under `models/` | Backend env | No | Detector model filename. |
| `SIH_SEG_MODEL` | R | Optional, default `twinlitenet_da.onnx` | Bundled file name under `models/` | Backend env | No | Segmentation model filename. |
| `SIH_DETECTOR` | R | Optional, default `opencv_onnx` | `opencv_onnx`, `ultralytics`, etc.; only actually available backends are reported | Backend env | No | Selects detector implementation. |
| `SIH_CONF` | R | Optional, default `0.35` | Confidence threshold | Backend env | No | YOLO detection threshold. |
| `SIH_IOU` | R | Optional, default `0.45` | IoU threshold | Backend env | No | NMS/tracking threshold. |
| `SIH_USE_CUDA` | R | Optional, default `0` | Set `1` only on a host with working CUDA/OpenCV DNN | Backend env | No | Runtime-detected GPU preference; CPU fallback remains. |
| `PYTHON_VERSION` | B | Optional, recommended `3.11.9` on Render | Render Blueprint / host settings | `render.yaml`, Render dashboard | No | Pins Python for backend build. |

## 3. Test/tool-only variables

| Variable | B/R | Required? | Where to obtain value | Secret? | Purpose |
|---|---|---|---|---|---|
| `WINEPREFIX` | R | Optional | Only for `scripts/check_windows_bat.py --wine` | No | Temporary Wine prefix for Windows `.bat` parser probes. Not needed for deployment. |

## 4. External accounts, credentials and hardware

These are **not** secrets to place inside the ZIP, but you must provide them yourself:

1. **Netlify account** — needed for drag-and-drop publish.
2. **Backend host account** — Render, Railway, Fly.io, or a VPS/Docker host. The host must support a long-lived Python process and WebSockets. Netlify Functions/serverless cannot run this backend.
3. **Optional custom domain + DNS** — only if you do not use the default `*.netlify.app` / `*.onrender.com` origins.
4. **Android phone with camera + browser permission** — required to verify QR pairing, rear/front camera selection, `getUserMedia`, WebRTC/MJPEG fallback and certificate trust.
5. **HTTPS trust decision** — Netlify provides trusted HTTPS; a self-signed local backend certificate must be generated locally and trusted on the phone. The private key must never be shipped.
6. **USB/UVC camera, ADB, IP Webcam app, laptop webcam** — required only for physical hardware verification. None is needed to build or deploy the software.

## 5. Explicitly absent

- No database URL, username, password or connection string: the backend keeps authoritative state in memory and writes report files under `outputs/`.
- No JWT/session secret, OAuth client ID/secret or API key.
- No cloud storage credentials.
- No real production tokens in `.env`; only `.env.example` templates are shipped.
- No TLS private key. `certs/sih-26037.crt` is a public certificate only; `scripts/generate_cert.py` generates a local key.
- No machine-specific IP or localhost URL is hardcoded as a production backend. Placeholders are visible and trigger a UI warning.
