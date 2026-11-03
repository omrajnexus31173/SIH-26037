FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIH_HOST=0.0.0.0 \
    SIH_BACKEND_PORT=8000 \
    SIH_USE_HTTPS=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-webrtc.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt -r requirements-webrtc.txt

COPY . .

RUN python -m compileall -q backend \
    && python scripts/download_models.py

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host ${SIH_HOST} --port ${SIH_BACKEND_PORT:-${PORT:-8000}}"]
