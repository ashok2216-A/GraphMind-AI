#!/usr/bin/env bash
set -e

PUBLIC_PORT=${PORT:-10000}
INTERNAL_API_PORT=8000

echo "=== Starting GraphMind on Render ==="
echo "1. Launching FastAPI backend on 0.0.0.0:${INTERNAL_API_PORT}..."
uvicorn api:app --host 0.0.0.0 --port ${INTERNAL_API_PORT} &

echo "2. Waiting for FastAPI backend to be ready..."
for i in $(seq 1 30); do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${INTERNAL_API_PORT}/')" >/dev/null 2>&1; then
    echo "FastAPI backend is ready!"
    break
  fi
  sleep 1
done

export API_BASE_URL="http://127.0.0.1:${INTERNAL_API_PORT}"

echo "3. Launching Streamlit frontend on port ${PUBLIC_PORT}..."
streamlit run streamlit_app.py \
  --server.port ${PUBLIC_PORT} \
  --server.address 0.0.0.0 \
  --server.headless true
