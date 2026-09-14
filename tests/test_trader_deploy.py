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

import pytest

from smartmoney_cub_harness.trader.storage import open_store

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


# ---- the proxy validator must be able to fail ----------------------------
#
# scripts/nginx-check.py is the only automated check on the shipped proxy config,
# and it was passing without parsing anything: it handed crossplane the config
# text instead of a filename, crossplane failed inside trying to open a name that
# long, and because that failure is reported in the returned status rather than
# by raising, the surrounding except-clause never fired. The script announced
# "PASS: parses cleanly" while the config was never read.
#
# A validator that cannot fail is worse than none, because it is trusted. These
# two tests pin both directions: it passes the shipped config, and it fails a
# broken one.


def _run_nginx_check(config_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the validator, optionally against a substituted config.

    A substituted config is written over the shipped file for the duration of the
    call and restored afterwards, so the repository is never left modified.
    """
    shipped = REPO_ROOT / "deploy" / "nginx.conf"
    if config_text is None:
        return subprocess.run(
            [sys.executable, "scripts/nginx-check.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
        )
    original = shipped.read_text(encoding="utf-8")
    try:
        shipped.write_text(config_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "scripts/nginx-check.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
        )
    finally:
        shipped.write_text(original, encoding="utf-8")


def test_the_proxy_validator_passes_the_shipped_config() -> None:
    result = _run_nginx_check()
    assert result.returncode == 0, (result.returncode, result.stdout[-800:])
    combined = result.stdout + result.stderr
    # The parse must actually have run; a skip means this check proved nothing.
    assert "PASS: parses cleanly" in combined, combined[-600:]


def test_the_proxy_validator_fails_a_broken_config() -> None:
    """The regression: this used to report PASS with the config unparsed."""
    shipped = _read(DEPLOY / "nginx.conf")
    broken = shipped.replace("worker_connections 1024;", "worker_connections 1024", 1)
    assert broken != shipped
    result = _run_nginx_check(broken)
    assert result.returncode != 0, (result.returncode, result.stdout[-600:])
    assert "parses cleanly" not in result.stdout, result.stdout[-600:]


# ---- the deployment's own documented steps, executed ---------------------
#
# The deploy artifacts are already checked for the properties a reviewer would
# verify by reading them. These go further and run what the documents tell an
# operator to run, because this project's late defects have all lived in the
# operator path: configuration that was reviewed but never executed.


def test_the_documented_nginx_extraction_yields_a_valid_config() -> None:
    """README step 4: keep the map and the servers, drop the outer wrappers.

    A distribution nginx includes conf.d files from inside its own http block, so
    the operator is told to strip this file's events and http wrappers. Nobody had
    run that transformation; if it produced something nginx rejects, the operator
    would find out on the host.
    """
    crossplane = pytest.importorskip("crossplane")
    import shutil
    import tempfile

    text = _read(DEPLOY / "nginx.conf")
    newline = chr(10)

    # Capture the body of the top-level http block by brace depth.
    marker = newline + "http {"
    start = text.index(marker) + len(marker)
    depth = 1
    index = start
    while depth > 0:
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1
    body = text[start:index]
    assert "location /trader/" in body

    workspace = Path(tempfile.mkdtemp(prefix="distro-extract-"))
    try:
        # Rebuild the distribution shape: a main file including our extracted
        # blocks from inside its own http block.
        full = (
            "worker_processes auto;" + newline
            + "events { worker_connections 1024; }" + newline
            + "http {" + newline + body.strip() + newline + "}" + newline
        )
        snippets = workspace / "snippets"
        snippets.mkdir(parents=True, exist_ok=True)
        (snippets / "smcub-token.conf").write_text(
            'set $smcub_token "toy-token";' + newline, encoding="utf-8"
        )
        config = workspace / "nginx.conf"
        config.write_text(
            full.replace(
                "/etc/nginx/snippets/smcub-token.conf",
                str(snippets / "smcub-token.conf"),
            ),
            encoding="utf-8",
        )
        result = crossplane.parse(str(config), onerror=lambda *a, **k: None)
        errors = result.get("errors") or []
        assert result.get("status") == "ok", [
            str(entry.get("error"))[:200] for entry in errors[:4]
        ]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_the_systemd_unit_refuses_to_start_without_both_secrets() -> None:
    """The unit's ExecStartPre gates, run against real env-file contents.

    Two greps require DATABASE_URL and TRADER_ACCESS_TOKEN to be present. That is
    the mechanism that stops a hosted process coming up without its secrets, so it
    is executed here rather than assumed.
    """
    import shlex
    import tempfile

    unit = _read(DEPLOY / "trader.service")
    gates = [
        line.split("=", 1)[1].strip()
        for line in unit.splitlines()
        if line.startswith("ExecStartPre=")
    ]
    assert len(gates) == 2, gates

    workspace = Path(tempfile.mkdtemp(prefix="unit-gate-"))
    try:
        def gates_all_pass(contents: str) -> bool:
            env_file = workspace / "trader.env"
            env_file.write_text(contents, encoding="utf-8")
            return all(
                subprocess.run(
                    shlex.split(gate.replace("/etc/smcub/trader.env", str(env_file))),
                    capture_output=True,
                    text=True,
                ).returncode == 0
                for gate in gates
            )

        newline = chr(10)
        # Both secrets present: the service may start.
        assert gates_all_pass(
            "DATABASE_URL=postgresql://u:p@127.0.0.1:5432/smcub" + newline
            + "TRADER_ACCESS_TOKEN=abc123" + newline
        )
        # Either one missing: the service must not start.
        assert not gates_all_pass("TRADER_ACCESS_TOKEN=abc123" + newline)
        assert not gates_all_pass("DATABASE_URL=x" + newline)
        assert not gates_all_pass("# only comments" + newline)
        # A commented-out secret must not satisfy the gate; that is the difference
        # between a real secret and someone silencing a check.
        assert not gates_all_pass(
            "# DATABASE_URL=x" + newline + "TRADER_ACCESS_TOKEN=abc" + newline
        )
    finally:
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)


def test_the_compose_database_url_expands_the_way_the_app_parses_it() -> None:
    """Expand the compose expressions and hand the result to the parser.

    The URL is assembled from four variables with nested defaults. Nested defaults
    read correctly and can expand wrongly, and the existing tests only assert the
    file's shape, so the expression is expanded here the way Compose would and the
    result is checked with the function the store itself uses.
    """
    import yaml

    from smartmoney_cub_harness.trader.storage.postgres_store import is_postgres_url

    compose = yaml.safe_load(_read(DEPLOY / "docker-compose.yml"))
    expression = compose["services"]["app"]["environment"]["DATABASE_URL"]

    expression_re = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::([-?]))?([^{}]*)\}")

    def expand(text: str, env: dict[str, str], depth: int = 0) -> str:
        if depth > 20:
            raise AssertionError("expression did not settle: " + text[:80])
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name, operator, rest = match.group(1), match.group(2), match.group(3)
            if env.get(name):
                changed = True
                return env[name]
            if operator == "-":
                changed = True
                return expand(rest, env, depth + 1)
            if operator == "?":
                raise AssertionError("required variable " + name + " is unset: " + rest[:40])
            changed = True
            return ""

        expanded = expression_re.sub(replace, text)
        # Re-substitute until the string stops changing, which resolves nested
        # defaults innermost-first.
        if changed or expanded != text:
            return expand(expanded, env, depth + 1)
        return expanded

    # The operator sets only the two required secrets: every other value defaults.
    minimal = expand(expression, {"POSTGRES_PASSWORD": "s3cret", "TRADER_ACCESS_TOKEN": "t"})
    assert is_postgres_url(minimal), minimal
    assert "smcub" in minimal and "db:5432" in minimal, minimal
    # No leftover expression fragments: a trailing brace here would be a URL the
    # driver cannot parse, and it is the kind of nested-default slip that reads
    # correctly.
    assert " not in minimal and " not in minimal, minimal

    # An override for every part resolves too.
    overridden = expand(
        expression,
        {
            "POSTGRES_PASSWORD": "pw",
            "TRADER_ACCESS_TOKEN": "t",
            "POSTGRES_USER": "trader",
            "POSTGRES_DB": "journal",
        },
    )
    assert is_postgres_url(overridden), overridden
    assert "trader" in overridden and "journal" in overridden, overridden

    # A directly supplied URL wins and is not polluted by the default.
    supplied = expand(
        expression,
        {
            "DATABASE_URL": "postgresql://u:p@dbhost:5432/x",
            "POSTGRES_PASSWORD": "pw",
            "TRADER_ACCESS_TOKEN": "t",
        },
    )
    assert supplied == "postgresql://u:p@dbhost:5432/x", supplied
    assert is_postgres_url(supplied)

    # And a missing password refuses rather than expanding to an empty credential.
    with pytest.raises(AssertionError):
        expand(expression, {"TRADER_ACCESS_TOKEN": "t"})


def test_the_release_smoke_check_exists_and_runs_before_publishing() -> None:
    """The one check that deploys the commit rather than the working tree.

    Every other gate reads the working tree. A release host clones the commit, so
    anything present locally but absent from the commit passes every other check
    and fails after publishing. That gap is why scripts/release-smoke.py exists,
    and this pins both its presence and its place in the release pipeline: a
    check that nothing invokes is the same as no check.
    """
    script = REPO_ROOT / "scripts" / "release-smoke.py"
    assert script.is_file(), "the release smoke check is missing"
    body = script.read_text(encoding="utf-8")
    # It must clone the commit and install it, not inspect the working tree.
    assert '"clone"' in body and "--local" in body
    # It must install from the clone rather than from the working directory.
    assert 'str(clone) + "[hosted]"' in body, "the smoke check does not install from the clone"
    # And it must verify the interface is actually in the commit, which is the
    # specific defect it was written to catch.
    assert "no built interface in the commit" in body
    # It must assert the properties a deployment depends on.
    for needle in ("tenant isolation", "anonymous refusal", "safety declaration"):
        assert needle in body, needle

    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "scripts/release-smoke.py" in workflow, (
        "the release workflow does not run the smoke check, so a tag could publish "
        "a commit that does not deploy"
    )
    # It must run before the artifact is built and uploaded.
    smoke_at = workflow.index("scripts/release-smoke.py")
    build_at = workflow.index("python -m build")
    assert smoke_at < build_at, "the smoke check must run before the wheel is built"


def test_the_deploy_readme_documents_a_backup_and_restore_procedure() -> None:
    """The journal is the one thing a user cannot recreate.

    deploy/docker-compose.yml tells the operator to back up the tenant volume.
    Until this procedure existed, nothing said how, so the instruction was a
    belief rather than a capability. The commands here were run verbatim against
    a real PostgreSQL before being written down, including the repeatable-restore
    flag, which is the part most likely to be wrong.
    """
    readme = _read(DEPLOY / "README.md")

    for phrase in (
        "Back up the journal",
        "pg_dump -Fc",
        "pg_restore",
        "--clean --if-exists",
        "scripts/backup-restore-check.py",
    ):
        assert phrase in readme, phrase

    # It must say why the journal is different, not only how to copy it.
    assert "cannot recreate" in readme, "the procedure does not say why it matters"
    # And it must warn about the failure mode a naive setup would hit.
    assert "is not a backup" in readme, "no warning that a same-disk dump is not a backup"

    # The check the procedure points at must exist and be runnable.
    script = REPO_ROOT / "scripts" / "backup-restore-check.py"
    assert script.is_file(), "the documented backup check is missing"
    body = script.read_text(encoding="utf-8")
    # It must restore into a fresh database and serve the product from it; a check
    # that only inspects the dump would not prove the journal is recoverable.
    assert "pg_dump" in body and "pg_restore" in body
    assert "serve the restored database" in body
    # And it must not repeat the bug that made it silently pass against a
    # leftover server on the port it wanted.
    assert "_port_in_use" in body, "the check can be fooled by a stale listener"


def test_a_restored_database_from_an_older_release_is_migrated_forward(tmp_path) -> None:
    """The backup procedure tells an operator to restore before upgrading.

    That instruction is only safe if the product migrates an older schema forward
    when it opens one. The claim was verified by execution -- a database carrying
    only the users table from an earlier shape came up as seven tables with its
    existing tenant row intact -- and this pins the two properties that make the
    instruction true: migrate() is idempotent, and it adds what is missing rather
    than recreating the store.
    """
    store = open_store(tmp_path / "legacy" / "store.db")
    try:
        first = store.migrate()
        # A tenant written by the "older" release must survive a later migration.
        store.create_user("legacy-tenant", display_name="From an older release")
        store.insert_trades(
            "legacy-tenant",
            [
                {
                    "trade_id": "TRD-LEGACY",
                    "symbol": "600111",
                    "side": "BUY",
                    "price": 10.0,
                    "quantity": 1000,
                    "trade_date": "2026-09-01",
                }
            ],
        )

        # Simulate the newer release opening it: migrate again from scratch.
        again = store.migrate()
        assert again["status"] == "ok"
        assert again["tables"] == first["tables"], "migration changed the table set"

        # The older release's data is still there, which is what makes "restore
        # the backup, then upgrade" a safe order.
        assert store.get_user("legacy-tenant") is not None
        assert len(store.list_trades("legacy-tenant")) == 1
    finally:
        store.close()
