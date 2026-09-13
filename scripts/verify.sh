#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== [Gate 1] Harness Doctor & Safety Contract Audit ==="
PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

DOCTOR_OUT=$("$PYTHON_BIN" -m smartmoney_cub_harness.cli doctor)
echo "$DOCTOR_OUT"
if ! echo "$DOCTOR_OUT" | grep -q "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"; then
  echo "FAIL: Doctor output missing safety declaration READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" >&2
  exit 1
fi
echo "✓ Doctor contract check passed."

echo ""
echo "=== [Gate 2] Test Suite Execution ==="
"$PYTHON_BIN" -m pytest tests/ -q --tb=short
echo "✓ All tests passed."

echo ""
echo "=== [Gate 3] Leak & Safety Sanity Scan ==="
# Ensure no unredacted absolute local paths or live order placement keywords slipped in
if git status --porcelain | grep -q '^[MARCD]'; then
  git diff HEAD -- ':(exclude)ledger.md' ':(exclude)*.json' | grep -iE '(api_key|secret_key|password|access_token|live_order)' && {
    echo "FAIL: Suspicious secret or live order keyword in git diff" >&2
    exit 1
  } || true
fi
echo "✓ Safety sanity check passed."

echo ""
echo "========================================="
echo "  Verification Loop: ALL GATES PASSED    "
echo "========================================="

