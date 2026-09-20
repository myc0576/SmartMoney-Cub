from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "leak-scan.py"

Q = chr(34)

# Fake credentials are assembled at run time rather than written out in full. A
# literal key in this file would itself be a leak the scanner exists to catch, and
# keeping the shape explicit still proves the pattern matches a real-looking value.
FAKE_APIKEY = "apikey_" + "0123456789abcdef" * 3
FAKE_OPENAI = "sk-" + "abcdef0123456789" * 2
FAKE_GITHUB = "ghp_" + "0123456789abcdefghijklmnop"
FAKE_PASSWORD = "hunter2024correcthorsebattery"
FAKE_HOME = "/Users/" + "someone" + "/checkout/data"
FAKE_EXECUTION = "live" + "_" + "order"


def rules_for(line: str, path: str = "src/example.py") -> set[str]:
    """Return the rule names the scanner reports for one added diff line."""
    diff = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n+{line}\n"
    completed = subprocess.run(
        [sys.executable, str(SCANNER), "--stdin"],
        input=diff,
        capture_output=True,
        text=True,
        check=False,
    )
    found: set[str] = set()
    for raw in completed.stderr.splitlines():
        if ": " in raw and "(" in raw:
            found.add(raw.split(": ", 1)[1].split(" (", 1)[0])
    return found


# ---- the scanner must catch what it exists for -----------------------------


def test_scanner_catches_a_prefixed_api_key_value() -> None:
    line = "api_key = " + Q + FAKE_APIKEY + Q
    assert "secret_value" in rules_for(line)


def test_scanner_catches_a_prefixed_key_without_an_assignment() -> None:
    line = "value = " + Q + FAKE_OPENAI + Q
    assert "secret_value" in rules_for(line)


def test_scanner_catches_a_long_assigned_secret() -> None:
    line = "PASSWORD = " + Q + FAKE_PASSWORD + Q
    assert "secret_value" in rules_for(line)


def test_scanner_catches_a_github_token_prefix() -> None:
    line = "token = " + Q + FAKE_GITHUB + Q
    assert "secret_value" in rules_for(line)


def test_scanner_catches_live_order_keywords() -> None:
    line = "route = " + Q + FAKE_EXECUTION + Q
    assert "execution_keyword" in rules_for(line)


def test_scanner_catches_a_local_absolute_path_in_shipping_code() -> None:
    line = "PATH = " + Q + FAKE_HOME + Q
    assert "local_absolute_path" in rules_for(line)


# ---- the scanner must not fire on legitimate content -----------------------


def test_scanner_allows_a_credential_name_in_prose() -> None:
    line = "    " + Q + "TYPESAFE_API_KEY is name-declared with the value staying in the user environment." + Q + ","
    assert rules_for(line) == set()


def test_scanner_allows_an_environment_lookup() -> None:
    line = "        self.api_key = api_key if api_key is not None else os.environ.get(" + Q + "TYPESAFE_API_KEY" + Q + ")"
    assert rules_for(line) == set()


def test_scanner_allows_a_frontend_form_field() -> None:
    line = "api_key: model.key.trim() || void 0, clear_key: false,"
    assert rules_for(line) == set()


def test_scanner_allows_a_placeholder_value() -> None:
    line = "api_key = " + Q + "CHANGEME" + Q
    assert rules_for(line) == set()


def test_scanner_allows_a_local_path_inside_a_test_fixture() -> None:
    line = "    path = " + Q + FAKE_HOME + Q
    assert rules_for(line, path="tests/test_redaction.py") == set()


# ---- the repository itself must scan clean --------------------------------


def test_current_worktree_diff_scans_clean() -> None:
    """The gate a release runs must pass on the tree that ships."""
    completed = subprocess.run(
        [sys.executable, str(SCANNER), "--verbose"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
