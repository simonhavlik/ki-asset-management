#!/usr/bin/env bash
# Local development launcher for KI Asset Management
# Usage: ./run-local.sh          (port 5001)
#        PORT=8080 ./run-local.sh
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-5001}"   # 5000 is taken by macOS AirPlay Receiver
source venv/bin/activate
echo "Starting KI Asset Management on http://127.0.0.1:${PORT}"
exec python -m flask run --port "$PORT" --host 127.0.0.1
