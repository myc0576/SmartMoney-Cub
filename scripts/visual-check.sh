#!/usr/bin/env bash
# Visual pass over the product's own interface.
#
# Starts the product, seeds it with toy data, drives every view in Chromium, and
# writes screenshots plus report.json to artifacts/visual/. Exits non-zero if any
# view fails to open, overflows horizontally, or logs a console error.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${1:-8800}"
PYTHON_BIN="${PYTHON_BIN:-python}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python3

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is already in use; stop that process first." >&2
  exit 3
fi

STATE_DIR="$ROOT/artifacts/visual/tmp-state"
mkdir -p "$STATE_DIR" "$ROOT/artifacts/visual"

"$PYTHON_BIN" -m smartmoney_cub_harness.cli trader serve \
  --port "$PORT" --no-browser --state-dir "$STATE_DIR" > "$ROOT/artifacts/visual/server.log" 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:$PORT/api/trader/health" >/dev/null 2>&1 && break
  sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$PORT/api/trader/health" >/dev/null 2>&1; then
  echo "the product did not start; see artifacts/visual/server.log" >&2
  exit 3
fi

# Toy fixture data so the views have something to render.
curl -fsS -X POST "http://127.0.0.1:$PORT/api/trader/accounts" -H 'Content-Type: application/json' \
  -d '{"name":"Main","broker":"Local","account_type":"live","initial_balance":100000,"currency":"USD"}' >/dev/null
curl -fsS -X POST "http://127.0.0.1:$PORT/api/trader/trades/import" -H 'Content-Type: application/json' \
  -d '{"rows":[{"trade_id":"v1","symbol":"600111","side":"BUY","price":10.0,"quantity":1000,"trade_date":"2026-09-01"},{"trade_id":"v2","symbol":"600111","side":"SELL","price":11.0,"quantity":1000,"trade_date":"2026-09-03"},{"trade_id":"v3","symbol":"600519","side":"BUY","price":100.0,"quantity":100,"trade_date":"2026-09-02"},{"trade_id":"v4","symbol":"600519","side":"SELL","price":98.0,"quantity":100,"trade_date":"2026-09-04"}]}' >/dev/null
# A playbook, so the playbook view renders its populated state rather than only
# its empty state. Without one that view is a single short notice, which the
# harness's size heuristic reads as a broken page.
curl -fsS -X POST "http://127.0.0.1:$PORT/api/trader/playbooks" -H 'Content-Type: application/json' \
  -d '{"name":"toy-breakout","description":"A toy plan used by the visual pass.","setup":"Breakout above the prior day high on rising volume.","entry_rules":"Wait for the close above the level.\nEnter on the next open.","exit_rules":"Exit below the breakout level.","risk_rules":"Risk no more than one percent per trade.","tags":["toy"]}' >/dev/null

node "$ROOT/scripts/visual-check.cjs" "http://127.0.0.1:$PORT" "$ROOT/artifacts/visual"
