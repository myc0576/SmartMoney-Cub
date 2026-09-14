#!/usr/bin/env bash
# Trader contract oracle: prove the product's API can back a real, shipping
# trading-journal UI without that UI changing its own contract.
#
# It starts the product's own server, seeds it with two fills, serves the
# archived third-party bundle with an adapter injected, drives five routes in
# Chromium, and writes work/trader-oracle/report.json.
#
# The archived bundle lives under work/ and is git-ignored on purpose: it is
# third-party build output, kept local for verification only, never published.
#
# Usage: bash scripts/trader-oracle.sh [api-port] [bundle-port]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${1:-8791}"
BUNDLE_PORT="${2:-8799}"
ORACLE_DIR="$ROOT/work/trader-oracle"
BUNDLE_DIR="$ROOT/work/tradezella-ui"
STATE_DIR="$ORACLE_DIR/tmp-state"
PYTHON_BIN="${PYTHON_BIN:-python}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python3

if [ ! -d "$BUNDLE_DIR/assets" ]; then
  echo "the archived bundle is missing at work/tradezella-ui/assets." >&2
  echo "It is git-ignored local material; re-run the earlier recon scripts to restore it." >&2
  exit 3
fi
if [ ! -f "$ORACLE_DIR/serve.cjs" ] || [ ! -f "$ORACLE_DIR/adapter.cjs" ]; then
  echo "the oracle adapter is missing under work/trader-oracle/." >&2
  echo "It is git-ignored local material; restore it before running the oracle." >&2
  exit 3
fi

mkdir -p "$STATE_DIR" "$ORACLE_DIR/shots"
API_PID=""; BUNDLE_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  [ -n "$BUNDLE_PID" ] && kill "$BUNDLE_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT

# A stale server on either port would answer the browser instead of the process
# this script starts, and the run would report the OLD backend's numbers as if
# they were ours. Refuse to start rather than produce a misleading report.
for port in "$API_PORT" "$BUNDLE_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port $port is already in use; stop that process first." >&2
    echo "A stale server would answer the browser and make this report meaningless." >&2
    exit 3
  fi
done

echo "=== start the product server (this is the backend under test) ==="
"$PYTHON_BIN" -m smartmoney_cub_harness.cli trader serve \
  --port "$API_PORT" --no-browser --state-dir "$STATE_DIR" > "$ORACLE_DIR/api.log" 2>&1 &
API_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/trader/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$API_PORT/api/trader/health" >/dev/null 2>&1; then
  echo "the product server did not come up; see work/trader-oracle/api.log" >&2
  cat "$ORACLE_DIR/api.log" >&2
  exit 3
fi
echo "  up on 127.0.0.1:$API_PORT"

echo "=== seed it with two fills (toy data, local only) ==="
curl -fsS -X POST "http://127.0.0.1:$API_PORT/api/trader/accounts" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Oracle Account","broker":"Local","account_type":"live","initial_balance":100000,"currency":"USD"}' \
  | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print("  account:", d.get("account",{}).get("account_id"), "| safety:", d.get("safety"))'
curl -fsS -X POST "http://127.0.0.1:$API_PORT/api/trader/trades/import" \
  -H 'Content-Type: application/json' \
  -d '{"rows":[{"trade_id":"oracle-b1","symbol":"600111","side":"BUY","price":10.0,"quantity":1000,"trade_date":"2026-09-01"},{"trade_id":"oracle-s1","symbol":"600111","side":"SELL","price":11.0,"quantity":1000,"trade_date":"2026-09-03"},{"trade_id":"oracle-b2","symbol":"600519","side":"BUY","price":100.0,"quantity":100,"trade_date":"2026-09-02"},{"trade_id":"oracle-s2","symbol":"600519","side":"SELL","price":98.0,"quantity":100,"trade_date":"2026-09-04"}]}' \
  | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print("  inserted:", d.get("inserted_count"), "| safety:", d.get("safety"))'

echo "=== serve the archived bundle with the adapter injected ==="
# Our own server, not offline-app/serve.cjs: that one injects the old fixture
# mock, which runs after any init script and would shadow the adapter, making
# every route render from stubs. Serving our own shell keeps the mock out of the
# page so the bundle talks to the real backend alone.
( cd "$ORACLE_DIR" && node serve.cjs "$BUNDLE_PORT" > "$ORACLE_DIR/bundle.log" 2>&1 ) &
BUNDLE_PID=$!
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$BUNDLE_PORT/tracking" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
echo "  up on 127.0.0.1:$BUNDLE_PORT"

echo "=== drive the routes ==="
node "$ORACLE_DIR/run.cjs" "http://127.0.0.1:$BUNDLE_PORT" "http://127.0.0.1:$API_PORT" "$ORACLE_DIR/report.json"
STATUS=$?

echo ""
echo "=== report ==="
"$PYTHON_BIN" - "$ORACLE_DIR/report.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for r in d["routes"]:
    print(f'{r["route"]:<24} ok={str(r.get("ok")):<5} dom={r.get("dom",0):<8} rows={r.get("rows",0):<4} '
          f'REAL={r.get("real_calls",0):<3} FALLBACK={r.get("fallback_calls",0):<3} errs={len(r.get("console_errors",[]))}')
s = d["summary"]
print()
print("routes checked            :", s["routes_checked"])
print("routes clean              :", s["routes_clean"])
print("clean AND backed by real  :", s["routes_clean_with_real_backend"])
print("real backend calls        :", s["total_real_calls"])
print("fallback (stub) calls     :", s["total_fallback_calls"])
PY

exit $STATUS
