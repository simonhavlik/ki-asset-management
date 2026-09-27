#!/usr/bin/env bash
#
# Local development launcher for KI Asset Management.
#
# IMPORTANT: .env mirrors the deployment configuration, so it points DATABASE_URL
# at the LIVE Neon database. Running the app that way means every click in the UI
# (votes, imports, recalculation, purchases) writes to PRODUCTION.
#
# This script therefore forces a local SQLite database by default. Opt in to the
# mirrored production config only when you deliberately need it.
#
#   ./run-local.sh              # safe: local SQLite, auto-reload
#   PORT=8080 ./run-local.sh    # different port
#   KI_USE_PROD_ENV=1 ./run-local.sh   # uses .env as-is -> writes to production!
#
# Note: variables exported here win over .env because python-dotenv does not
# overwrite variables that are already present in the environment.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5001}"   # 5000 is taken by macOS AirPlay Receiver

if [[ "${KI_USE_PROD_ENV:-0}" == "1" ]]; then
    echo "############################################################"
    echo "#  WARNING: .env is used as-is. DATABASE_URL points at the  #"
    echo "#  LIVE production database. UI actions WRITE TO PRODUCTION.#"
    echo "############################################################"
    read -r -p "Type 'yes i am sure' to continue: " confirm
    if [[ "$confirm" != "yes i am sure" ]]; then
        echo "aborted"
        exit 1
    fi
    DB_LABEL="postgres (PRODUCTION)"
else
    export FLASK_CONFIG=development
    export USE_LOCAL_SQLITE=True
    export DATABASE_URL=
    export NEON_OPTIMIZE=false
    export FLASK_DEBUG=1
    export SESSION_COOKIE_SECURE=false
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
    DB_LABEL="sqlite (instance/analyst.db)"
fi

if [[ ! -x venv/bin/python ]]; then
    echo "venv/ not found. Create it first:"
    echo "  uv venv --python 3.12 venv && uv pip install --python venv/bin/python -r requirements.txt"
    exit 1
fi

source venv/bin/activate
echo "KI Asset Management -> http://127.0.0.1:${PORT}"
echo "  database: ${DB_LABEL}"
echo "  debug/reload: ${FLASK_DEBUG:-0}"
exec python -m flask run --port "$PORT" --host 127.0.0.1
