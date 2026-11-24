"""Numerical analysis subprocess provider for smartmoney-cub-harness.

Reads one bounded strict JSON object from stdin, dispatches to offline numerical
modules (inverse_linear or markov_propagate), and emits one JSON result to stdout.

Errors exit non-zero with bounded structured stderr and safety declaration.
Never executes orders, communicates over network, or writes arbitrary files.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

MAX_INPUT_BYTES = 2_097_152  # 2 MiB finite byte budget
ALLOWED_OPERATIONS = frozenset({"inverse_linear", "markov_propagate"})


def _emit_error(code: str, message: str, exit_code: int = 1) -> int:
    """Write bounded structured error to stderr and return non-zero exit code.

    Truncates and redacts the message before serialization so the envelope is
    always well-formed JSON and never drops the safety declaration.
    """
    bounded_message = str(redact(message))[:500]
    payload = {
        "status": "error",
        "error_code": str(code)[:64],
        "message": bounded_message,
        "safety": SAFETY_DECLARATION,
    }
    raw = json.dumps(payload, ensure_ascii=True, allow_nan=False)
    sys.stderr.write(raw + "\n")
    sys.stderr.flush()
    return exit_code


def _reject_constant(constant_val: str) -> Any:
    raise ValueError(f"disallowed JSON constant: {constant_val}")


def _strict_object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError(f"duplicate key in JSON object: {key!r}")
        obj[key] = val
    return obj


def parse_strict_json(raw_text: str) -> Any:
    """Parse JSON rejecting duplicate keys, NaN/Infinity constants, and deep recursion."""
    try:
        return json.loads(
            raw_text,
            parse_constant=_reject_constant,
            object_pairs_hook=_strict_object_pairs_hook,
        )
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"Strict JSON parsing failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """Read one JSON request from stdin, dispatch numerical operation, write result."""
    args = sys.argv[1:] if argv is None else argv
    if args:
        if len(args) == 1 and args[0] in ("-h", "--help"):
            sys.stdout.write(
                "Numerical analysis subprocess provider for smartmoney-cub-harness.\n"
                "Reads one JSON request from stdin and writes one JSON result to stdout.\n"
                "Supported operations: inverse_linear, markov_propagate.\n"
                f"Safety: {SAFETY_DECLARATION}\n"
            )
            sys.stdout.flush()
            return 0
        bounded_args = str(redact(args))[:100]
        return _emit_error("invalid_arguments", f"Unrecognized CLI arguments: {bounded_args}", 2)

    # Read binary bytes when buffer is available, or fallback to text stream for tests
    try:
        if hasattr(sys.stdin, "buffer") and sys.stdin.buffer is not None:
            raw_bytes = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            raw_text = sys.stdin.read(MAX_INPUT_BYTES + 1)
            raw_bytes = raw_text.encode("utf-8")
    except Exception as exc:
        return _emit_error("stdin_read_error", f"Failed reading from stdin: {exc}", 2)

    if not raw_bytes:
        return _emit_error("empty_input", "stdin received empty input, expected JSON object", 2)

    if len(raw_bytes) > MAX_INPUT_BYTES:
        return _emit_error(
            "input_too_large",
            f"Input size ({len(raw_bytes)} bytes) exceeds maximum budget of {MAX_INPUT_BYTES} bytes",
            2,
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _emit_error("encoding_error", f"Input is not valid UTF-8: {exc}", 2)

    if not text.strip():
        return _emit_error("empty_input", "stdin received empty input, expected JSON object", 2)

    try:
        request = parse_strict_json(text)
    except ValueError as exc:
        return _emit_error("json_decode_error", str(exc), 2)

    if not isinstance(request, dict):
        return _emit_error(
            "invalid_request_type",
            f"Expected top-level JSON object (dict), got {type(request).__name__}",
            2,
        )

    operation = request.get("operation")
    if not isinstance(operation, str) or not operation.strip():
        return _emit_error("missing_operation", "Missing or empty 'operation' field", 2)

    bounded_op = str(operation)[:64]
    if operation not in ALLOWED_OPERATIONS:
        return _emit_error(
            "unsupported_operation",
            f"Unsupported operation {bounded_op!r}. Allowed: {sorted(ALLOWED_OPERATIONS)}",
            2,
        )

    output: dict[str, Any]
    if operation == "inverse_linear":
        try:
            from smartmoney_cub_harness.numerical.inverse import solve_inverse
        except ImportError as exc:
            return _emit_error("import_error", f"Failed to import inverse module: {exc}", 1)
        try:
            output = solve_inverse(request)
        except Exception as exc:
            return _emit_error(type(exc).__name__, str(exc), 1)

    elif operation == "markov_propagate":
        try:
            from smartmoney_cub_harness.numerical.markov import propagate_markov
        except ImportError as exc:
            return _emit_error("import_error", f"Failed to import markov module: {exc}", 1)
        try:
            output = propagate_markov(request)
        except Exception as exc:
            return _emit_error(type(exc).__name__, str(exc), 1)

    else:
        return _emit_error("unsupported_operation", f"Unknown operation: {bounded_op}", 2)

    if not isinstance(output, dict):
        return _emit_error("invalid_output", "Solver did not return a JSON dictionary", 1)

    output.setdefault("safety", SAFETY_DECLARATION)
    output.setdefault("result_kind", "statistical_result")

    try:
        serialized = json.dumps(output, ensure_ascii=True, allow_nan=False) + "\n"
    except (ValueError, TypeError) as exc:
        return _emit_error(
            "serialization_error",
            f"Output contains non-finite numbers or un-serializable data: {exc}",
            1,
        )

    sys.stdout.write(serialized)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
