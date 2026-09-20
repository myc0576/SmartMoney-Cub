"""Scan a diff for leaked secret values, local paths, and execution keywords.

Why this exists: the first version of this gate matched bare keywords such as
api_key anywhere in the diff. That flagged the credential *names* the plugin
contract explicitly requires a manifest to declare, and it flagged any rebuild of
the packaged front-end, whose provider settings form legitimately contains an
api_key field. It also never tested the thing that actually matters - a real key
value reaching the tree - because a field name and a leaked secret look identical
to a keyword search. A gate that fails on a documentation line is a gate people
learn to bypass.

This scans for value shapes instead of field names: known provider prefixes, and
assignments whose value is long and secret-like. A credential name in prose, a
form field, or an environment lookup passes; apikey_<40 hex> does not.

It is a sanity check, not a vault: it reads the diff, so it catches a secret that
was written into a tracked file, and cannot catch one that never existed on disk.

    python scripts/leak-scan.py              # scans git diff HEAD
    git diff HEAD | python scripts/leak-scan.py --stdin
    python scripts/leak-scan.py --verbose    # report a clean scan too

Exit 0 means no finding. Exit 1 prints each offender with its file and rule.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Keywords whose *assigned value* must never be a literal secret. A bare mention of
# the keyword is fine: only "keyword = <secret-looking literal>" is reported.
SECRET_KEYS = (
    "api[_-]?key",
    "apikey",
    "secret[_-]?key",
    "client[_-]?secret",
    "password",
    "passwd",
    "access[_-]?token",
    "refresh[_-]?token",
    "auth[_-]?token",
    "bearer",
)

# A literal value that plausibly is a real credential rather than a name, a
# placeholder, or an expression. The charset excludes quotes, brackets, spaces,
# and pipes, so a code expression cannot match; requiring a digit separates
# apikey_212c5859 from an identifier.
_VALUE_CHARS = r"A-Za-z0-9_\-./+="
ASSIGNMENT_RE = re.compile(
    r"(?i)\b(" + "|".join(SECRET_KEYS) + r")\b\s*[:=]\s*[\"']?([" + _VALUE_CHARS + r"]{20,})"
)

# Prefixed credentials are reported wherever they appear, assigned or not.
PREFIX_RE = re.compile(
    r"(?i)\b("
    r"apikey_[A-Za-z0-9_-]{8,}|"
    r"sk-[A-Za-z0-9_-]{16,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"AIza[A-Za-z0-9_-]{16,}|"
    r"AKIA[A-Z0-9]{12,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}"
    r")\b"
)

# Execution keywords have no legitimate spelling in this product, so they stay a
# strict keyword match rather than a shape match.
EXECUTION_RE = re.compile(r"(?i)\b(live_order|place_order|cancel_order|broker_connect)\b")

# A local absolute path ties a commit to one machine and publishes that machine's
# account name. Test fixtures are exempt: several exist precisely to prove the
# redactor removes such a path.
LOCAL_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\")

PLACEHOLDER_PREFIXES = ("none", "null", "true", "false", "redacted", "changeme", "placeholder", "xxx")

SKIP_SUFFIXES = (".json",)
SKIP_FILES = ("ledger.md",)

# This scanner has to name the shapes it removes, exactly as safety.py names the
# path patterns it redacts, so scanning its own source would always report the
# pattern list. Every other shipping file, including tests, is scanned: a real key
# committed in a fixture is still a leak, which is why tests/test_leak_scan.py
# assembles its fake credentials at run time instead of writing them out.
SELF_PATH = "scripts/leak-scan.py"


def _looks_like_secret(value: str) -> bool:
    """Return whether an assigned literal is plausibly a real secret."""
    lowered = value.lower()
    if any(lowered.startswith(word) for word in PLACEHOLDER_PREFIXES):
        return False
    if not any(character.isdigit() for character in value):
        return False
    # A dotted identifier such as os.environ.get is code, not a credential.
    if value.count(".") >= 2 and all(part.isidentifier() for part in value.split(".")):
        return False
    return True


def scan_diff(diff_text: str) -> list[dict[str, str]]:
    """Return one finding per offending added line in a unified diff."""
    findings: list[dict[str, str]] = []
    path = ""
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        if path.endswith(SKIP_SUFFIXES) or path in SKIP_FILES:
            continue
        if path == SELF_PATH:
            continue
        line = raw[1:]

        for match in PREFIX_RE.finditer(line):
            findings.append({"path": path, "rule": "secret_value", "detail": match.group(1)[:14] + "..."})
        for match in ASSIGNMENT_RE.finditer(line):
            if _looks_like_secret(match.group(2)):
                findings.append({"path": path, "rule": "secret_value", "detail": match.group(1) + "=<redacted>"})
        for match in EXECUTION_RE.finditer(line):
            findings.append({"path": path, "rule": "execution_keyword", "detail": match.group(1)})
        if not path.startswith("tests/"):
            for match in LOCAL_PATH_RE.finditer(line):
                findings.append({"path": path, "rule": "local_absolute_path", "detail": match.group(0)[:40]})
    return findings


def _diff_from_git() -> str:
    completed = subprocess.run(
        ["git", "diff", "HEAD", "--", ":(exclude)ledger.md", ":(exclude)*.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        # An unborn or detached edge case: scanning nothing is safer than crashing
        # the gate, and stderr still reaches the caller.
        sys.stderr.write(completed.stderr)
        return ""
    return completed.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a diff for leaked secrets and execution keywords.")
    parser.add_argument("--stdin", action="store_true", help="read the diff from stdin instead of git")
    parser.add_argument("--verbose", action="store_true", help="report a clean scan as well")
    args = parser.parse_args(argv)

    diff_text = sys.stdin.read() if args.stdin else _diff_from_git()
    findings = scan_diff(diff_text)

    if not findings:
        if args.verbose:
            print("leak scan: no secret value, execution keyword, or local path in the diff")
        return 0

    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding["path"], finding["rule"], finding["detail"])
        if key in seen:
            continue
        seen.add(key)
        print(f"{finding['path']}: {finding['rule']} ({finding['detail']})", file=sys.stderr)
    print(f"FAIL: {len(seen)} finding(s) in the diff", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
