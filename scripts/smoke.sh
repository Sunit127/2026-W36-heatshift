#!/usr/bin/env bash
set -euo pipefail
PORT="${HEATSHIFT_SMOKE_PORT:-4173}"
python3 -m http.server "$PORT" --directory dist >/tmp/heatshift-smoke.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for _ in {1..20}; do curl -fsS "http://127.0.0.1:$PORT/" >/tmp/heatshift-index.html && break; sleep 0.1; done
grep -q 'Plan a shift' /tmp/heatshift-index.html
curl -fsS "http://127.0.0.1:$PORT/logic.js" | grep -q 'buildPlan'
echo "Smoke test passed on http://127.0.0.1:$PORT/"
