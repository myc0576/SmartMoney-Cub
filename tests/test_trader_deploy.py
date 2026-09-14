# ABOUTME: Guards the Task 10 deployment artifacts and the product README.
# ABOUTME: The deferred-feature list is prose, so it is pinned here by test.

"""Deployment artifacts and the product README.

The product README is the record of what v1 does, what it never does, and what
is deferred past v1. Prose drifts silently, so the phrases the product owner
asked to be recorded are asserted here rather than trusted.

The deploy artifacts are checked for the properties a reviewer would verify by
reading them: the image installs the hosted extra and runs unprivileged, the
compose file takes its secrets from the environment and waits for a healthy
database, nginx publishes the /trader prefix without buffering streamed
responses, and the systemd unit is non-root and restarts on failure.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs" / "trader-product.md"
README = REPO_ROOT / "README.md"
DEPLOY = REPO_ROOT / "deploy"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _doc() -> str:
    return _read(DOCS)


def _lowered_doc() -> str:
    return _doc().lower()


def test_product_readme_exists_and_states_v1_scope() -> None:
    """What v1 does, and the boundary it never crosses."""
    doc = _doc()
    assert "What v1 does" in doc
    assert "Non-goals" in doc
    assert "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in doc
    assert "docs/trader-product-spec.md" in doc


def test_product_readme_lists_the_explicit_non_goals() -> None:
    lowered = _lowered_doc()
    for phrase in (
        "no orders",
        "no cancellation",
        "no broker account mutation",
        "no advice",
    ):
        assert phrase in lowered, phrase
    assert "no execution automation" in lowered
    assert "no stock picking" in lowered


def test_deferred_features_are_named_for_after_v1() -> None:
    """Every deferred item, so none is quietly forgotten."""
    lowered = _lowered_doc()
    deferred = (
        "broker direct-connect and read-only key sync",
        "multi-user billing and quotas",
        "spaces and mentor-student mode",
        "community features and leaderboards",
        "realtime notification push",
        "a mobile client",
    )
    for phrase in deferred:
        assert phrase in lowered, phrase
    assert "deferred past v1" in lowered
    assert "planned for after v1" in lowered


def test_product_readme_records_the_alphatech_entry_point() -> None:
    doc = _doc()
    assert "alphatech.net.cn/trader" in doc
    assert "Alpha Canvas" in doc
    assert "Commerce Workbench" in doc


def test_root_readme_links_to_the_product_readme() -> None:
    readme = _read(README)
    assert "docs/trader-product.md" in readme
    # A bare mention is not a link; it has to be a Markdown link target.
    assert re.search(r"\]\(docs/trader-product\.md\)", readme)


def test_deploy_directory_ships_every_artifact() -> None:
    for name in (
        "Dockerfile",
        "docker-compose.yml",
        "nginx.conf",
        "trader.service",
        "README.md",
    ):
        assert (DEPLOY / name).is_file(), name


def test_dockerfile_builds_the_hosted_product_without_baking_a_secret() -> None:
    dockerfile = _read(DEPLOY / "Dockerfile")
    assert dockerfile.startswith("# syntax=docker/dockerfile:1")
    assert "FROM python:3.12-slim" in dockerfile
    assert "pip install \".[hosted]\"" in dockerfile
    assert "trader serve --mode hosted" in dockerfile
    # Runs unprivileged.
    assert re.search(r"(?m)^USER\s+(?!root)\S+", dockerfile)
    assert "useradd" in dockerfile
    # No secret is baked in: the database URL and the token arrive at run time.
    assert "DATABASE_URL" in dockerfile
    assert not re.search(r"(?m)^ENV\s+DATABASE_URL", dockerfile)
    assert not re.search(r"(?m)^ENV\s+TRADER_ACCESS_TOKEN", dockerfile)
    assert "EXPOSE 8787" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_compose_is_valid_yaml_with_a_healthcheck_on_both_services() -> None:
    """Parsed with a real YAML loader when one is installed."""
    import pytest

    yaml = pytest.importorskip("yaml", reason="PyYAML is not installed here")
    payload = yaml.safe_load(_read(DEPLOY / "docker-compose.yml"))
    assert isinstance(payload, dict)
    services = payload["services"]
    assert set(services) == {"app", "db"}
    assert services["db"]["image"] == "postgres:16"
    for name in ("app", "db"):
        assert services[name]["healthcheck"]["test"], name
        assert services[name].get("volumes"), name
    # Named volumes, so the journal survives a rebuild.
    assert set(payload["volumes"]) == {"db_data", "smcub_state"}
    # The app waits for the database instead of racing it.
    assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_takes_its_secrets_from_the_environment() -> None:
    compose = _read(DEPLOY / "docker-compose.yml")
    # ':?' refuses to start without the value instead of committing a default.
    assert "${POSTGRES_PASSWORD:?" in compose
    assert "${TRADER_ACCESS_TOKEN:?" in compose
    # Every assignment of a secret is an interpolation, never a literal value.
    assignments = re.findall(r"(?m)^\s*POSTGRES_PASSWORD:\s*(.+)$", compose)
    assert assignments, "the compose file sets POSTGRES_PASSWORD"
    for value in assignments:
        assert value.strip().startswith("${"), value


def test_nginx_publishes_the_trader_prefix_and_leaves_streaming_unbuffered() -> None:
    nginx = _read(DEPLOY / "nginx.conf")
    assert "location /trader/" in nginx
    assert "proxy_pass http://smcub_trader/" in nginx
    # TLS placeholders, not a committed certificate.
    assert "ssl_certificate " in nginx
    assert "ssl_certificate_key " in nginx
    assert "ssl_protocols TLSv1.2 TLSv1.3" in nginx
    # The assistant streams its turns over one long-lived response.
    assert "proxy_buffering off" in nginx
    assert "proxy_set_header Upgrade $http_upgrade" in nginx
    assert "proxy_set_header Connection $connection_upgrade" in nginx


def test_systemd_unit_runs_unprivileged_and_restarts_on_failure() -> None:
    unit = _read(DEPLOY / "trader.service")
    assert "[Service]" in unit
    assert "[Install]" in unit
    assert re.search(r"(?m)^User=(?!root)\S+", unit)
    assert re.search(r"(?m)^Group=(?!root)\S+", unit)
    assert re.search(r"(?m)^Restart=on-failure$", unit)
    assert "trader serve" in unit
    assert "--mode hosted" in unit
    assert "--database-url ${DATABASE_URL}" in unit
    assert "--token ${TRADER_ACCESS_TOKEN}" in unit
    # Both secrets come from a root-readable file, not from the unit body.
    assert "EnvironmentFile=" in unit


def test_deploy_readme_documents_three_routes() -> None:
    readme = _read(DEPLOY / "README.md")
    routes = re.findall(r"(?m)^## Route \d+[^\n]*", readme)
    assert len(routes) == 3, routes
    # The facts a reader must not get wrong.
    assert "postgresql://" in readme
    assert "--token" in readme
    assert "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in readme
    assert "does **not** mount" in readme
    assert "/api/trader/*" in readme
    assert "mode hosted" in readme


def test_changelog_records_the_trader_product_at_the_top() -> None:
    changelog = _read(REPO_ROOT / "CHANGELOG.md")
    entries = re.findall(r"(?m)^## .+$", changelog)
    assert "Trader Product v1" in entries[0], entries[:3]
    assert "deferred past v1" in changelog
    assert "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in changelog


# ---- the deployment's own refusal path -----------------------------------
#
# These run the command the service units and the image run, and assert how it
# behaves when the database is unavailable. That path is where the operator
# stands at 3am, and a raw traceback there tells them less than one line does.


def _serve_argv(*extra: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "smartmoney_cub_harness.cli",
        "trader",
        "serve",
        "--no-browser",
        *extra,
    ]


def test_an_unreachable_hosted_database_is_refused_in_one_clean_line() -> None:
    """A database outage is reported, not dumped as a stack trace.

    Regression: open_store validates only the URL's shape, and the first real
    connection happens when the service migrates the schema. That call sat
    outside the store guard, so an unreachable database produced an unhandled
    StoreError with a full traceback while every documented refusal printed one
    line and exited 2.
    """
    proc = subprocess.run(
        _serve_argv(
            "--mode",
            "hosted",
            "--port",
            "0",
            "--database-url",
            # A name that cannot resolve: no DNS, no port, no credentials.
            "postgresql://nonexistent-host.invalid:5432/smcub",
            "--token",
            "toy-token",
        ),
        capture_output=True,
        text=True,
        timeout=90,
        cwd=REPO_ROOT,
    )
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, combined
    assert proc.returncode == 2, (proc.returncode, combined)
    assert "could not open the tenant store" in combined, combined


def test_hosted_mode_without_a_database_url_is_refused_before_connecting() -> None:
    """The documented refusal, kept as the baseline the outage path matches."""
    proc = subprocess.run(
        _serve_argv("--mode", "hosted", "--port", "0", "--token", "toy-token"),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2, (proc.returncode, combined)
    assert "Traceback" not in combined, combined
    assert "--database-url" in combined, combined
    assert "no local fallback" in combined, combined


def test_binding_beyond_loopback_without_a_token_is_refused() -> None:
    """The image binds 0.0.0.0, so this refusal is what keeps a journal closed."""
    proc = subprocess.run(
        _serve_argv("--host", "0.0.0.0", "--port", "0"),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2, (proc.returncode, combined)
    assert "without --token" in combined, combined
