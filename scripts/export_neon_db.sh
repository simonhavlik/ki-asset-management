#!/usr/bin/env bash
#
# Export the production Neon database to a local custom-format dump.
#
# WHY THIS EXISTS
#   Neon hard-suspends a project's computes when it exceeds a consumption quota
#   (compute / written data / data transfer). A suspended project refuses ALL
#   connections - including pg_dump - until the next billing period or until the
#   quota is lifted (plan upgrade or a support override). So: run this ONLY once
#   Neon accepts connections again.
#
# NOTES
#   * pg_dump must NOT go through the connection pooler. This script rewrites the
#     "...-pooler....neon.tech" host to the direct (unpooled) endpoint.
#   * Neon does not support pg_dumpall or pg_dump -C/--create.
#   * Use a pg_dump client whose major version is >= the server's.
#
# USAGE
#   ./scripts/export_neon_db.sh            # writes neon_kiam_<timestamp>.dump
#
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v pg_dump >/dev/null 2>&1; then
    cat <<'EOF'
pg_dump not found. Install the Postgres client tools:

    brew install libpq
    export PATH="/opt/homebrew/opt/libpq/bin:$PATH"     # keg-only
    # or: brew link --force libpq

Then re-run this script.
EOF
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "ERROR: .env not found (run from the repo, or create it from .env.example)." >&2
    exit 1
fi

# Read DATABASE_URL without echoing it (it contains credentials).
URL="$(grep -E '^[[:space:]]*DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')"
if [[ -z "${URL}" ]]; then
    echo "ERROR: DATABASE_URL is empty in .env (production is Neon; it must be set)." >&2
    exit 1
fi

DIRECT="${URL/-pooler./.}"
HOST="${DIRECT##*@}"; HOST="${HOST%%/*}"
OUT="neon_kiam_$(date +%Y%m%d_%H%M%S).dump"

echo "pg_dump : $(pg_dump --version)"
echo "target  : ${HOST}  (direct/unpooled)"
echo "output  : ${OUT}"
echo

# quick reachability check so a suspended project fails fast and clearly
if ! pg_isready -d "${DIRECT}" >/dev/null 2>&1; then
    echo "WARNING: pg_isready could not confirm the server. If the dump below fails with" >&2
    echo "         'exceeded the quota', Neon is still suspended - lift the quota first." >&2
fi

set +e
pg_dump -Fc -v --no-owner --no-privileges -d "${DIRECT}" -f "${OUT}"
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
    echo >&2
    echo "pg_dump FAILED (exit ${rc})." >&2
    echo "If the error mentions 'exceeded the quota', Neon still has the project suspended." >&2
    echo "Lift it (upgrade is prorated per day, or ask Neon support for a temporary override)," >&2
    echo "then re-run this script. The free-tier quota also resets at consumption_period_end." >&2
    exit $rc
fi

echo
echo "Dump written: $(ls -lh "${OUT}" | awk '{print $5, $9}')"
echo "Contents (first tables):"
pg_restore -l "${OUT}" | grep -E "TABLE DATA|TABLE " | head -20 || true
echo
echo "Next: restore into your own Postgres, or convert to SQLite."
