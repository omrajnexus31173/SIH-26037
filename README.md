# SIH-26037 backend deployment README

This package contains the long-lived Python backend only. Deploy it to a host that supports a persistent process and WebSockets, then point the Netlify frontend at its public HTTPS origin.

## Included

- `backend/` FastAPI application, perception, planning, safety, simulation, evaluation, camera/pairing and WebSockets.
- `models/` bundled YOLOv8n and TwinLiteNet ONNX files with verified hashes.
- `assets/` sample image and generated demo clip.
- `Dockerfile`, `docker-compose.yml`, `render.yaml`, `Procfile`, `fly.toml`.
- `deploy/backend/start.sh`, `deploy/requirements.lock.txt`, `vendor/wheels/README.md`.
- `requirements.txt`, `requirements-webrtc.txt`, `requirements-dev.txt`.
- `.env.example`, `backend/.env.example`, `ENVIRONMENT_VARIABLES.md`.
- Certificate generator and public certificate; **private key excluded**.

## Render (recommended for beginners)

1. Open <https://dashboard.render.com> and sign in.
2. Click **New +** → **Web Service**.
3. Connect a GitHub/GitLab repository containing this backend package.
4. If `render.yaml` is detected, accept the Blueprint. Otherwise enter:
   - Runtime: `Python 3`
   - Python version: `3.11.9`
   - Build command: `pip install -r requirements.txt -r requirements-webrtc.txt`
   - Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/health`
5. Add environment variables from `backend/.env.example`. At minimum keep `SIH_HOST=0.0.0.0` and `SIH_USE_HTTPS=0`; Render supplies `PORT`.
6. Choose an always-on plan for stable WebSockets. Free tiers can sleep.
7. Click **Create Web Service** and wait for **Live**.
8. Copy the public URL, e.g. `https://sih26037-backend.onrender.com`.
9. Open `https://sih26037-backend.onrender.com/api/health`; success is JSON containing `"status": "ok"` and `"project": "SIH-26037"`.

## Docker / VPS

```bash
docker build -t sih26037-backend .
docker run --rm -p 8000:8000 sih26037-backend
curl http://127.0.0.1:8000/api/health
```

For a public Netlify site, put the container behind managed HTTPS (Caddy, Nginx, Cloudflare Tunnel, Fly.io, Railway). Plain HTTP from an HTTPS frontend is blocked as mixed content.

## Offline Python wheels

The resolved versions are in `deploy/requirements.lock.txt`. Generate a local wheel directory:

```bash
python3 scripts/download_wheels.py --platform native
python3 -m venv .venv-deploy
.venv-deploy/bin/pip install --no-index --find-links vendor/wheels/native -r requirements.txt -r requirements-webrtc.txt
```

A full Linux wheel set measured 184 MB and is not bundled. No database credentials or API keys are required.

## After deployment

Edit `runtime-config.js` in the Netlify frontend ZIP as described in `NETLIFY_DEPLOY_README.md`, or set `VITE_BACKEND_URL` / `VITE_FRONTEND_ORIGIN` for a Git-based Netlify build. The backend already allows permissive REST CORS; WebSockets must connect directly to this host's `wss://` origin, not through Netlify redirects.
