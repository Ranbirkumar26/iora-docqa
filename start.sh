#!/usr/bin/env bash
# Launch FastAPI (internal) + Streamlit (public). Streamlit is the foreground
# process so the container stays alive on it; the API runs in the background.
set -e

uvicorn app.api.main:app --host 0.0.0.0 --port 8000 &

# give the API a moment to bind before the UI can call /status
sleep 2

exec streamlit run frontend/app.py \
  --server.port "${PORT:-8501}" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
