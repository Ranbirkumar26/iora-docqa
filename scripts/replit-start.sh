#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv/bin/python" ] || [ ! -d "web/out" ]; then
  bash scripts/replit-build.sh
fi

source .venv/bin/activate
exec python -m uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
