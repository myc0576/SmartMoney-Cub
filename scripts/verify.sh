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
# Scan the diff for secret *values*, local absolute paths, and live order keywords.
# It deliberately does not match bare field names: the plugin contract requires a
# manifest to declare credential names, and the packaged settings form contains an
# api_key field, so a keyword search reported both as leaks while never testing the
# thing that matters. scripts/leak-scan.py matches value shapes instead;
# tests/test_leak_scan.py holds it to that with positive and negative controls.
if ! "$PYTHON_BIN" scripts/leak-scan.py; then
  echo "FAIL: suspicious secret, local path, or live order keyword in git diff" >&2
  exit 1
fi
echo "✓ Safety sanity check passed."

echo ""
echo "========================================="
echo "  Verification Loop: ALL GATES PASSED    "
echo "========================================="
