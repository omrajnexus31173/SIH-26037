# Backend deployment

The FastAPI backend must run as a long-lived process. Netlify cannot host it.

## Local / VPS Docker

```bash
docker build -t sih26037-backend .
docker run --rm -p 8000:8000 sih26037-backend
```

or:

```bash
docker compose up --build
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Render / Railway / Heroku-style

- `render.yaml` is included.
- `Procfile` works on platforms that support Procfiles.
- `deploy/backend/start.sh` can be used as a custom start command.
- `backend/config.py` accepts `PORT` when `SIH_BACKEND_PORT` is absent.

## Fly.io

1. Change `app` in `fly.toml` to a unique name.
2. Run `fly launch --no-deploy` or `fly apps create <name>`.
3. Run `fly deploy`.
4. Use `https://<app>.fly.dev` as `VITE_BACKEND_URL` on Netlify.

## HTTPS / WSS

For a Netlify HTTPS frontend, the backend must also be reachable over HTTPS/WSS. Use the platform's managed TLS or put the container behind a reverse proxy. Do not point a HTTPS frontend at a plain HTTP backend; browsers block mixed content.

## Persistent files

- `outputs/` receives generated reports/comparisons.
- `uploads/` receives uploaded videos.
- `config/` receives optional calibration JSON.

Mount these directories if the deployment platform has an ephemeral filesystem.

## Models

`models/yolov8n.onnx` and `models/twinlitenet_da.onnx` are bundled in the image. `Dockerfile` runs `scripts/download_models.py` to verify their SHA-256 hashes at build time. CPU-only OpenCV DNN is the default; no GPU is required.
