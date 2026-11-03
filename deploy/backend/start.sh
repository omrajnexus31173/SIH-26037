#!/usr/bin/env bash
set -euo pipefail

export SIH_HOST="${SIH_HOST:-0.0.0.0}"
export SIH_BACKEND_PORT="${SIH_BACKEND_PORT:-${PORT:-8000}}"

exec python -m uvicorn backend.main:app \
  --host "$SIH_HOST" \
  --port "$SIH_BACKEND_PORT"
