# Netlify Deployment Guide

## If you see `Deployment configuration required`

That banner is expected when the static site has no backend URL. Netlify cannot host the FastAPI/OpenCV/WebSocket backend, so a frontend-only edit cannot fix it while `backendUrl` is empty. Do not publish with the warning.

- No backend yet? Follow `deploy/netlify/BACKEND_FIRST.md` and obtain a public HTTPS backend URL.
- Drag-and-drop deploy? Edit `netlify/site/runtime-config.js` using `deploy/netlify/runtime-config.template.js`, set `configured: true`, and re-upload the folder.
- Git/Netlify build? Set `VITE_BACKEND_URL` and `VITE_FRONTEND_ORIGIN` in Netlify, then clear cache and redeploy. The build regenerates `runtime-config.js`.
- Never use `http://localhost:8000`; the browser is on Netlify's HTTPS origin and cannot reach your PC.

## Architecture

```text
Browser / phone
    │
    ├── https://your-site.netlify.app          (static React + /pair)
    │       runtime-config.js
    │
    └── https://your-backend.example.com      (FastAPI, ONNX, WebSockets, MJPEG)
            /api/*  /ws/*  /docs
```

Netlify does not host the backend. Do not rely on Netlify redirects for `/api` or `/ws`: REST can sometimes be proxied, but WebSockets cannot. The frontend therefore uses an absolute backend origin from runtime configuration.

---

## 1. Deploy the backend first

### Docker / VPS

```bash
docker build -t sih26037-backend .
docker run --rm -p 8000:8000 \
  -e SIH_HOST=0.0.0.0 \
  -e SIH_BACKEND_PORT=8000 \
  -e SIH_USE_HTTPS=0 \
  sih26037-backend
```

Or:

```bash
docker compose up --build
```

For a public HTTPS origin, put the container behind Caddy, Nginx, Traefik, Cloudflare Tunnel, Render, Railway, or Fly.io. The browser requires `https://` and `wss://` when the Netlify site is HTTPS; mixed content is blocked.

### Render

Use `render.yaml` or create a Web Service with:

```text
Build:  pip install -r requirements.txt -r requirements-webrtc.txt
Start:  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

`backend/config.py` accepts `PORT` as a fallback when `SIH_BACKEND_PORT` is not set.

### Offline Python install

The resolved versions are in `deploy/requirements.lock.txt`. To create a local wheel cache:

```bash
python3 scripts/download_wheels.py --platform native
python3 -m venv .venv-deploy
.venv-deploy/bin/pip install --no-index --find-links vendor/wheels/native -r requirements.txt -r requirements-dev.txt -r requirements-webrtc.txt
```

A full Linux wheel set was measured at 184 MB and is therefore not bundled in the ZIP; the reproducibly generated lockfile and downloader are included instead.

---

## 2. Configure Netlify

Set these environment variables in **Site configuration → Environment variables**:

```ini
VITE_BACKEND_URL=https://your-backend.example.com
VITE_FRONTEND_ORIGIN=https://your-site.netlify.app
```

No trailing slash. `VITE_BACKEND_URL` must be the HTTPS origin of the backend. `VITE_FRONTEND_ORIGIN` is used when generating QR/pairing links.

`netlify.toml` runs:

```text
cd frontend && npm ci && npm run build:netlify
```

and publishes `netlify/site`.

---

## 3. Deploy

### Git deploy

1. Push the extracted project to Git.
2. Import the repository in Netlify.
3. Confirm build command/publish directory from `netlify.toml`.
4. Add the two environment variables.
5. Deploy and open the site URL.
6. Open `/pair` to verify SPA routing and secure context.

### Manual drag-and-drop

1. Edit `netlify/site/runtime-config.js`.
2. Replace the two `REPLACE_WITH` placeholders.
3. Set `configured: true`.
4. Drag `netlify/site` into Netlify's manual deploy area.

`_redirects` maps all unknown paths to `/index.html`, so `/pair` works on refresh. `_headers` sets `Cache-Control: no-store` on the runtime config.

---

## 4. Phone pairing on Netlify

Netlify provides HTTPS for the static site, which satisfies the secure-context requirement for `getUserMedia` on the phone. However:

- the backend must also be HTTPS/WSS;
- the phone must be able to reach the backend origin;
- QR URLs are built from `VITE_FRONTEND_ORIGIN` / runtime `frontendOrigin`;
- WebRTC failure falls back to authenticated MJPEG-over-WebSocket;
- no physical phone, valid SDP/ICE media exchange, or certificate-trust UI was tested in this workspace.

---

## 5. Verification checklist

- `curl https://your-backend.example.com/api/health` returns HTTP 200.
- Browser devtools shows REST calls going to the backend origin, not Netlify.
- Telemetry WebSocket connects to `wss://your-backend.example.com/ws/telemetry`.
- `/pair` loads on refresh over HTTPS.
- No `Deployment configuration required` banner appears after runtime config is set.
- QR candidate URLs use the Netlify origin, not `localhost`.
- MJPEG/JPEG snapshot and simulation controls respond through the external backend.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Yellow configuration banner | Edit `runtime-config.js` or set `VITE_BACKEND_URL` / `VITE_FRONTEND_ORIGIN` and redeploy |
| REST 404 on Netlify | Backend URL is empty/placeholder; set an absolute external backend origin |
| WebSocket fails | Netlify cannot proxy WebSockets; use direct `wss://` backend origin |
| Mixed-content error | Backend must be HTTPS/WSS, not plain HTTP |
| `/pair` 404 on refresh | Ensure `_redirects` / `netlify.toml` SPA fallback is deployed |
| QR says localhost | Set `VITE_FRONTEND_ORIGIN` to the public Netlify HTTPS origin |
| CORS error | Confirm backend is running with the included CORS middleware; do not use Netlify redirects for `/api` |
| Camera permission blocked | Netlify HTTPS is required; avoid a custom HTTP domain |

## Final drag-and-drop package

Use `SIH-26037-NETLIFY-FRONTEND.zip`. Extract it, then drag the single `SIH-26037-NETLIFY-FRONTEND/` folder into Netlify's manual deploy area. It already includes `index.html`, hashed `assets/`, `_redirects`, `_headers`, `runtime-config.js`, `NETLIFY_DEPLOY_README.md`, `BACKEND_FIRST.md`, `runtime-config.template.js` and `ENVIRONMENT_VARIABLES.md`. The backend is in `SIH-26037-BACKEND-DEPLOY.zip`.
