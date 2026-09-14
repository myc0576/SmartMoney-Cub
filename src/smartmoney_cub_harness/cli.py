from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from smartmoney_cub_harness import __version__
from smartmoney_cub_harness.case_bank import collect_offline_case
from smartmoney_cub_harness.evidence_pack import build_evidence_pack, replay_evidence_pack
from smartmoney_cub_harness.evaluator import evaluate_decision
from smartmoney_cub_harness.evolution_ledger import append_ledger_event
from smartmoney_cub_harness.launcher import launcher_diagnostics
from smartmoney_cub_harness.loop import run_agent_loop
from smartmoney_cub_harness.manifest import validate_run_manifest
from smartmoney_cub_harness.memory import save_memory_record
from smartmoney_cub_harness.mentor_fit import build_mentor_fit
from smartmoney_cub_harness.outcome import build_outcome, resolve_price_source
from smartmoney_cub_harness.plugin_cli import (
    plugin_catalog,
    plugin_disable,
    plugin_doctor,
    plugin_enable,
    plugin_install,
    plugin_inspect,
    plugin_list,
    plugin_logs,
    plugin_remove,
    plugin_run,
    profile_dump,
    profile_reload,
    profile_show,
)
from smartmoney_cub_harness.plugins.profiles import BUILTIN_PROFILES
from smartmoney_cub_harness.privacy_audit import inspect_run_artifacts, load_payload_json, privacy_audit
from smartmoney_cub_harness.registry import register_candidate
from smartmoney_cub_harness.run_capture import capture_run, get_command_preset, parse_command
from smartmoney_cub_harness.run_envelope import validate_run_envelope
from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.self_evolve import confirm_promotion, run_self_evolve
from smartmoney_cub_harness.share_cli import build_share_pack_from_source
from smartmoney_cub_harness.trader_cli import run_trader_serve
from smartmoney_cub_harness.tradingagents_adapter import (
    check_tradingagents_environment,
    ingest_tradingagents_report,
    run_tradingagents_local_bridge,
)
from smartmoney_cub_harness.workspace_cli import (
    workspace_add_case,
    workspace_import_csv,
    workspace_list_cases,
    workspace_record_outcome,
    workspace_show_case,
    workspace_summary,
)


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2))


def evaluate_run(run_dir: str | Path, horizon: str = "d1") -> dict[str, Any]:
    run_path = Path(run_dir)
    decision_path = run_path / "decision.json"
    outcome_path = run_path / f"outcome_{horizon}.json"
    eval_path = run_path / "eval.json"
    decision = _read_json(decision_path)
    if str(decision.get("action_label", "")).upper() == "ERROR":
        result = {
            "status": "error_decision_not_evaluated",
            "grade": "not_evaluated",
            "decision_path": str(decision_path),
            "eval_path": str(eval_path),
            "safety": SAFETY_DECLARATION,
        }
        _write_json(eval_path, result)
        return result

    outcome = _read_json(outcome_path)
    result = evaluate_decision(decision, outcome)
    result.update(
        {
            "status": "evaluated",
            "decision_path": str(decision_path),
            "outcome_path": str(outcome_path),
            "eval_path": str(eval_path),
            "safety": SAFETY_DECLARATION,
        }
    )
    _write_json(eval_path, result)
    return result


def doctor() -> dict[str, Any]:
    return {
        "status": "ok",
        "package": "smartmoney-cub-harness",
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        # network_required documents that the core is usable with no network: the
        # package imports and runs fully offline. Built-in market sources are
        # opt-in at call time, so no network is required to import or run the core.
        "network_required": False,
        "telemetry": False,
        "upload": False,
        "credentials_required": False,
        "github_auth_required": False,
        # external_api_required stays False: built-in market sources are opt-in at
        # call time, not required to import or run the core.
        "external_api_required": False,
        "broker_api_required": False,
        "execution_integrations": "disabled",
        "default_data_mode": "offline_json_fixtures",
        # market_data_mode defaults to offline; online sources are opt-in per call.
        "market_data_mode": "offline",
        # tenant_mode defaults to the single local user for offline use and CI.
        "tenant_mode": "local_single_user",
        "launcher": launcher_diagnostics(),
        "safety": SAFETY_DECLARATION,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smcub",
        description=(
            "Local-first trading journal and review harness: read-only over markets "
            "and execution, writable over your own journal."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-manifest", help="Validate a run manifest JSON file")
    validate.add_argument("manifest")

    validate_envelope = sub.add_parser("validate-envelope", help="Validate a run envelope JSON file")
    validate_envelope.add_argument("envelope")

    capture = sub.add_parser("capture-run", help="Run offline commands and save replay artifacts")
    capture.add_argument("--root", default=".")
    capture.add_argument("--mode", required=True, choices=["intraday", "after-close"])
    capture.add_argument("--preset", choices=["toy", "after-close"])
    capture.add_argument("--command", dest="inline_commands", action="append", default=[])
    capture.add_argument("--decision-time")
    capture.add_argument("--timeout-seconds", type=int, default=300)
    capture.add_argument(
        "--sandbox",
        action="store_true",
        help="Write under tmp/sandbox; this does not isolate the subprocess",
    )
    capture.add_argument("--agent-name", default="external-agent")
    capture.add_argument("--agent-version")
    capture.add_argument("--agent-interface", default="command")

    build_evidence = sub.add_parser(
        "build-evidence-pack", help="Freeze offline runs into a replayable evidence pack"
    )
    build_evidence.add_argument("output_dir")
    build_evidence.add_argument("--sample", dest="sample_dirs", action="append", required=True)
    build_evidence.add_argument("--rule-candidate", required=True)
    build_evidence.add_argument("--horizon", choices=["d1", "d3"], default="d1")

    replay_evidence = sub.add_parser(
        "replay-evidence-pack", help="Verify and replay a frozen evidence pack"
    )
    replay_evidence.add_argument("pack_dir")

    build_outcome_cmd = sub.add_parser("build-outcome", help="Build D1/D3 outcome JSON for a run")
    build_outcome_cmd.add_argument("run_dir")
    build_outcome_cmd.add_argument("--horizon", choices=["d1", "d3"], required=True)
    build_outcome_cmd.add_argument("--price-source", required=True)

    evaluate_run_cmd = sub.add_parser("evaluate-run", help="Evaluate a run directory")
    evaluate_run_cmd.add_argument("run_dir")
    evaluate_run_cmd.add_argument("--horizon", choices=["d1", "d3"], default="d1")

    register = sub.add_parser("register-candidate", help="Register a rule candidate")
    register.add_argument("registry")
    register.add_argument("candidate")
    register.add_argument("--confirm-promote", action="store_true")

    doctor_cmd = sub.add_parser("doctor", help="Show local package health and safety settings")
    doctor_cmd.set_defaults(command="doctor")

    loop_cmd = sub.add_parser("loop", help="Run the offline toy agent loop")
    loop_cmd.add_argument("--preset", choices=["toy"], default="toy")
    loop_cmd.add_argument("--agent-trigger", default="")
    loop_cmd.add_argument("--horizon", choices=["d1", "d3"], default="d1")
    loop_cmd.add_argument("--json", action="store_true", help="Print the final loop summary as JSON")

    mentor_fit = sub.add_parser("mentor-fit", help="Build offline toy mentor-fit style anchor JSON")
    mentor_fit.add_argument("input", help="JSON payload with toy cases and optional public templates")

    self_evolve = sub.add_parser("self-evolve", help="Run the local private CSV self-evolution loop")
    self_evolve.add_argument("--input-csv", required=True)
    self_evolve.add_argument("--max-iterations", type=int, default=20)
    self_evolve.add_argument("--time-budget-min", type=float, default=10.0)
    self_evolve.add_argument("--horizon", choices=["d1", "d3"], default="d1")
    self_evolve.add_argument("--state-root", default="state/self_evolve")
    self_evolve.add_argument("--resume")
    self_evolve.add_argument("--interactive-confirm", action="store_true")

    confirm = sub.add_parser("confirm-promotion", help="Record a manual promotion decision")
    confirm.add_argument("promotion_packet")
    confirm.add_argument("--decision", required=True, choices=["promote", "defer", "reject"])
    confirm.add_argument("--note", default="")

    privacy_cmd = sub.add_parser("privacy-audit", help="Show offline privacy and safety settings")
    privacy_cmd.set_defaults(command="privacy-audit")

    ta_doctor = sub.add_parser("tradingagents-doctor", help="Check optional TradingAgents adapter readiness")
    ta_doctor.set_defaults(command="tradingagents-doctor")

    ta_ingest = sub.add_parser("tradingagents-ingest", help="Import a local TradingAgents report as a review packet")
    ta_ingest.add_argument("--report", required=True)
    ta_ingest.add_argument("--ticker", required=True)
    ta_ingest.add_argument("--analysis-date", required=True)
    ta_ingest.add_argument("--output")

    ta_run = sub.add_parser("tradingagents-run", help="Run optional local TradingAgents bridge as review-only evidence")
    ta_run.add_argument("--ticker", required=True)
    ta_run.add_argument("--analysis-date", required=True)
    ta_run.add_argument("--output")
    ta_run.add_argument("--allow-network", action="store_true")
    ta_run.add_argument("--ack-external-llm", action="store_true")
    ta_run.add_argument("--provider")
    ta_run.add_argument("--deep-model")
    ta_run.add_argument("--quick-model")
    ta_run.add_argument("--max-debate-rounds", type=int)

    inspect = sub.add_parser("inspect-artifacts", help="Inspect a loop run directory for required safe artifacts")
    inspect.add_argument("run_dir")

    collect_case = sub.add_parser("collect-case", help="Collect a toy offline case from a run directory")
    collect_case.add_argument("run_dir")
    collect_case.add_argument("--output")

    append_ledger = sub.add_parser("append-ledger", help="Append a redacted event to an evolution ledger JSONL file")
    append_ledger.add_argument("--event", required=True)
    append_ledger.add_argument("--payload-json", required=True)
    append_ledger.add_argument("--ledger")

    save_memory = sub.add_parser("save-memory", help="Write local Markdown memory from a case record")
    save_memory.add_argument("case_record")
    save_memory.add_argument("--output")

    dashboard_cmd = sub.add_parser(
        "dashboard", help="Launch the local AI trading journal & copilot web dashboard"
    )
    dashboard_cmd.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    dashboard_cmd.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    dashboard_cmd.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    workbench_cmd = sub.add_parser(
        "workbench", help="Launch the local-first review workbench (A-plan interface)"
    )
    workbench_cmd.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    workbench_cmd.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    workbench_cmd.add_argument("--state-dir", default=None, help="Override the local state directory")
    workbench_cmd.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    workbench_cmd.add_argument(
        "--token",
        default=None,
        help="Required access token when binding beyond loopback",
    )

    trader_cmd = sub.add_parser(
        "trader", help="Run the trader product's HTTP surface (journal, analytics, backtest)"
    )
    trader_sub = trader_cmd.add_subparsers(dest="trader_command", required=True)
    trader_serve = trader_sub.add_parser(
        "serve", help="Serve the trader product and the review workbench on one port"
    )
    trader_serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    trader_serve.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    trader_serve.add_argument(
        "--mode",
        choices=["local", "hosted"],
        default="local",
        help="local is a single offline user; hosted resolves an alphatech identity",
    )
    trader_serve.add_argument(
        "--database-url",
        default=None,
        help="Postgres URL for the tenant store; required in hosted mode",
    )
    trader_serve.add_argument(
        "--state-dir", default=None, help="Local store directory (local mode only)"
    )
    trader_serve.add_argument(
        "--token",
        default=None,
        help="Required access token when binding beyond loopback",
    )
    trader_serve.add_argument("--no-browser", action="store_true", help="Do not open a browser")

    import_cmd = sub.add_parser("import", help="Import broker records into the local store")
    import_sub = import_cmd.add_subparsers(dest="import_command", required=True)
    import_file = import_sub.add_parser("file", help="Import a CSV, PDF, or screenshot file")
    import_file.add_argument("path")
    import_file.add_argument("--state-dir", default=None)
    import_file.add_argument("--portfolio-id", default=None)
    import_file.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    import_commit = import_sub.add_parser("commit", help="Commit reviewed rows from an extraction")
    import_commit.add_argument("extraction_id")
    import_commit.add_argument("--rows", default=None, help="JSON file with corrected rows")
    import_commit.add_argument("--state-dir", default=None)
    import_commit.add_argument("--portfolio-id", default=None)
    import_commit.add_argument("--json", action="store_true")
    import_sub.add_parser("list", help="List local documents already imported")

    store_cmd = sub.add_parser("store", help="Inspect and maintain the local review store")
    store_sub = store_cmd.add_subparsers(dest="store_command", required=True)
    store_status = store_sub.add_parser("status", help="Show local store counts and paths")
    store_status.add_argument("--state-dir", default=None)
    store_status.add_argument("--json", action="store_true")
    store_backup = store_sub.add_parser("backup", help="Copy the local store aside")
    store_backup.add_argument("destination")
    store_backup.add_argument("--state-dir", default=None)
    store_backup.add_argument("--json", action="store_true")

    skill_cmd = sub.add_parser("skill", help="Install the agent skill for a supported host")
    skill_sub = skill_cmd.add_subparsers(dest="skill_command", required=True)
    skill_install = skill_sub.add_parser("install", help="Write the skill into a host directory")
    skill_install.add_argument("--target", default="codex", help="codex, claude, deepseek-harness, or a path")
    skill_install.add_argument("--force", action="store_true", help="Overwrite an existing skill directory")
    skill_install.add_argument("--json", action="store_true")
    skill_sub.add_parser("show", help="Print the packaged skill definition")

    plugin_cmd = sub.add_parser("plugin", help="Discover, inspect, and run read-only plugins")
    plugin_sub = plugin_cmd.add_subparsers(dest="plugin_command", required=True)

    def add_common(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument("--profile", default="default-offline", choices=sorted(BUILTIN_PROFILES))
        parser_obj.add_argument("--plugin-dir", action="append", default=[])
        parser_obj.add_argument("--state-db")

    plugin_list_cmd = plugin_sub.add_parser("list", help="List discovered plugins and entry points")
    add_common(plugin_list_cmd)

    plugin_inspect_cmd = plugin_sub.add_parser("inspect", help="Validate and show a plugin manifest")
    plugin_inspect_cmd.add_argument("manifest")

    plugin_enable_cmd = plugin_sub.add_parser("enable", help="Activate a discovered plugin")
    plugin_enable_cmd.add_argument("plugin_id")
    add_common(plugin_enable_cmd)

    plugin_disable_cmd = plugin_sub.add_parser("disable", help="Deactivate a plugin and roll back its effects")
    plugin_disable_cmd.add_argument("plugin_id")
    add_common(plugin_disable_cmd)

    plugin_remove_cmd = plugin_sub.add_parser("remove", help="Revoke a plugin entry while keeping its audit trail")
    plugin_remove_cmd.add_argument("plugin_id")
    plugin_remove_cmd.add_argument("--state-db")

    plugin_doctor_cmd = plugin_sub.add_parser("doctor", help="Check plugin tree, capabilities, and gates")
    add_common(plugin_doctor_cmd)

    plugin_logs_cmd = plugin_sub.add_parser("logs", help="Show recorded plugin lifecycle events")
    plugin_logs_cmd.add_argument("plugin_id")
    plugin_logs_cmd.add_argument("--state-db")
    plugin_logs_cmd.add_argument("--limit", type=int, default=50)

    plugin_run_cmd = plugin_sub.add_parser("run", help="Run a plugin capability as wrapped review evidence")
    plugin_run_cmd.add_argument("plugin_id")
    plugin_run_cmd.add_argument("--capability")
    plugin_run_cmd.add_argument("--request")
    plugin_run_cmd.add_argument("--decision-time", required=True)
    plugin_run_cmd.add_argument("--available-at", required=True)
    plugin_run_cmd.add_argument("--data-source", default="")
    plugin_run_cmd.add_argument("--data-quality", default="ok")
    plugin_run_cmd.add_argument("--result-kind", default="review_observation")
    plugin_run_cmd.add_argument("--workspace-db", help="Persist the wrapped evidence into this workspace")
    plugin_run_cmd.add_argument("--case-id", help="Link the recorded evidence to a review case")
    add_common(plugin_run_cmd)

    plugin_sub.add_parser("catalog", help="List curated external projects and integration levels")

    plugin_install_cmd = plugin_sub.add_parser(
        "install",
        help="Register a locally obtained plugin (never downloads)",
    )
    plugin_install_cmd.add_argument("source", help="Local plugin directory or manifest path")
    add_common(plugin_install_cmd)

    profile_cmd = sub.add_parser("profile", help="Inspect and reload plugin composition profiles")
    profile_sub = profile_cmd.add_subparsers(dest="profile_command", required=True)
    profile_show_cmd = profile_sub.add_parser("show", help="Show one resolved profile and its entry tree")
    profile_show_cmd.add_argument("name", choices=sorted(BUILTIN_PROFILES))
    profile_dump_cmd = profile_sub.add_parser("dump", help="Dump every built-in profile as JSON")
    profile_dump_cmd.add_argument("--output")
    profile_reload_cmd = profile_sub.add_parser("reload", help="Rebuild the plugin tree explicitly")
    add_common(profile_reload_cmd)

    share_pack_cmd = sub.add_parser(
        "share-pack", help="Build a privacy-reduced static HTML review pack for local sharing"
    )
    share_pack_cmd.add_argument("--csv", help="Optional broker or 同花顺 CSV; omit to use labelled demo data")
    share_pack_cmd.add_argument("--output", help="Output directory for the static HTML pack")
    share_pack_cmd.add_argument("--regime", default="生长")
    share_pack_cmd.add_argument("--title", default="SmartMoney-Cub Review Pack")
    share_pack_cmd.add_argument("--write", action="store_true", help="Write the pack to --output")

    workspace_cmd = sub.add_parser(
        "workspace", help="Query and update the local SQLite review workspace"
    )
    workspace_sub = workspace_cmd.add_subparsers(dest="workspace_command", required=True)

    ws_add = workspace_sub.add_parser("add-case", help="Record a review case with its risk contract")
    ws_add.add_argument("payload", help="JSON payload describing the case")
    ws_add.add_argument("--db")

    ws_list = workspace_sub.add_parser("list-cases", help="List review cases with optional filters")
    ws_list.add_argument("--db")
    ws_list.add_argument("--action")
    ws_list.add_argument("--symbol")
    ws_list.add_argument("--regime")

    ws_show = workspace_sub.add_parser("show-case", help="Show one case with outcomes and evidence")
    ws_show.add_argument("case_id")
    ws_show.add_argument("--db")

    ws_outcome = workspace_sub.add_parser("record-outcome", help="Record a D1/D3 style outcome")
    ws_outcome.add_argument("case_id")
    ws_outcome.add_argument("--horizon", required=True)
    ws_outcome.add_argument("--return-pct", type=float, required=True)
    ws_outcome.add_argument("--max-adverse-excursion-pct", type=float)
    ws_outcome.add_argument("--outcome-time")
    ws_outcome.add_argument("--detail", default="")
    ws_outcome.add_argument("--db")

    ws_import = workspace_sub.add_parser("import-csv", help="Import broker CSV round trips as facts")
    ws_import.add_argument("csv_path")
    ws_import.add_argument("--db")
    ws_import.add_argument("--regime", default="")

    ws_summary = workspace_sub.add_parser("summary", help="Show workspace counts and sample limits")
    ws_summary.add_argument("--db")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-manifest":
        result = validate_run_manifest(_read_json(args.manifest))
        _print_json(result)
        return 0 if result["ok"] else 2

    if args.command == "validate-envelope":
        result = validate_run_envelope(_read_json(args.envelope))
        _print_json(result)
        return 0 if result["valid"] else 2

    if args.command == "capture-run":
        commands = [parse_command(value) for value in args.inline_commands]
        if not commands:
            commands = get_command_preset(args.preset or args.mode)
        _print_json(
            capture_run(
                root=args.root,
                mode=args.mode,
                commands=commands,
                decision_time=args.decision_time,
                timeout_seconds=args.timeout_seconds,
                sandbox=args.sandbox,
                agent_name=args.agent_name,
                agent_version=args.agent_version,
                agent_interface=args.agent_interface,
            )
        )
        return 0

    if args.command == "build-evidence-pack":
        result = build_evidence_pack(
            args.output_dir,
            args.sample_dirs,
            _read_json(args.rule_candidate),
            horizon=args.horizon,
        )
        _print_json(result)
        return 0

    if args.command == "replay-evidence-pack":
        result = replay_evidence_pack(args.pack_dir)
        _print_json(result)
        return 0 if result.get("evidence_status") == "verified" else 2

    if args.command == "build-outcome":
        resolved = resolve_price_source(args.price_source)
        outcome_path = build_outcome(args.run_dir, horizon=args.horizon, price_source=resolved)
        _print_json({"status": "ok", "outcome_path": str(outcome_path), "safety": SAFETY_DECLARATION})
        return 0

    if args.command == "evaluate-run":
        _print_json(evaluate_run(args.run_dir, horizon=args.horizon))
        return 0

    if args.command == "register-candidate":
        _print_json(register_candidate(args.registry, _read_json(args.candidate), confirm_promote=args.confirm_promote))
        return 0

    if args.command == "doctor":
        _print_json(doctor())
        return 0

    if args.command == "loop":
        _print_json(
            run_agent_loop(
                preset=args.preset,
                horizon=args.horizon,
                agent_trigger=args.agent_trigger,
            )
        )
        return 0

    if args.command == "mentor-fit":
        _print_json(build_mentor_fit(_read_json(args.input)))
        return 0

    if args.command == "self-evolve":
        result = run_self_evolve(
            input_csv=args.input_csv,
            max_iterations=args.max_iterations,
            time_budget_min=args.time_budget_min,
            horizon=args.horizon,
            state_root=args.state_root,
            resume=args.resume,
        )
        if args.interactive_confirm and result.get("promotion_status") == "promotion_recommended":
            sys.stderr.write("Promotion recommended. Enter promote, defer, or reject: ")
            decision = input().strip().lower()
            sys.stderr.write("Optional note: ")
            note = input()
            packet_path = Path(args.state_root) / str(result["loop_id"]) / "promotion_packet.json"
            result["confirmation"] = confirm_promotion(packet_path, decision=decision, note=note)
        _print_json(result)
        return 0

    if args.command == "confirm-promotion":
        _print_json(confirm_promotion(args.promotion_packet, decision=args.decision, note=args.note))
        return 0

    if args.command == "privacy-audit":
        _print_json(privacy_audit())
        return 0

    if args.command == "tradingagents-doctor":
        _print_json(check_tradingagents_environment())
        return 0

    if args.command == "tradingagents-ingest":
        try:
            result = ingest_tradingagents_report(
                report=args.report,
                ticker=args.ticker,
                analysis_date=args.analysis_date,
            )
        except FileNotFoundError as exc:
            result = {
                "status": "error",
                "error": {"code": "report_missing", "message": str(exc)},
                "safety": SAFETY_DECLARATION,
            }
            _print_json(result)
            return 2
        if args.output:
            _write_json(Path(args.output), result)
            result["output"] = str(Path(args.output))
        _print_json(result)
        return 0

    if args.command == "tradingagents-run":
        result = run_tradingagents_local_bridge(
            ticker=args.ticker,
            analysis_date=args.analysis_date,
            allow_network=args.allow_network,
            ack_external_llm=args.ack_external_llm,
            provider=args.provider,
            deep_model=args.deep_model,
            quick_model=args.quick_model,
            max_debate_rounds=args.max_debate_rounds,
        )
        if args.output and result.get("status") == "ok":
            _write_json(Path(args.output), result)
            result["output"] = str(Path(args.output))
        _print_json(result)
        return 0 if result.get("status") == "ok" else 2

    if args.command == "inspect-artifacts":
        _print_json(inspect_run_artifacts(args.run_dir))
        return 0

    if args.command == "collect-case":
        _print_json(collect_offline_case(args.run_dir, output_path=args.output))
        return 0

    if args.command == "append-ledger":
        payload_path = Path(args.payload_json)
        ledger_path = Path(args.ledger) if args.ledger else payload_path.with_name("evolution_ledger.jsonl")
        _print_json(append_ledger_event(ledger_path, args.event, load_payload_json(payload_path)))
        return 0

    if args.command == "save-memory":
        _print_json(save_memory_record(args.case_record, output_path=args.output))
        return 0

    if args.command == "dashboard":
        from smartmoney_cub_harness.dashboard.server import start_dashboard_server

        start_dashboard_server(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0

    if args.command == "workbench":
        from smartmoney_cub_harness.convergence_cli import run_workbench

        return run_workbench(
            host=args.host,
            port=args.port,
            state_dir=args.state_dir,
            open_browser=not args.no_browser,
            token=args.token,
        )

    if args.command == "trader":
        return run_trader_serve(
            host=args.host,
            port=args.port,
            mode=args.mode,
            database_url=args.database_url,
            state_dir=args.state_dir,
            open_browser=not args.no_browser,
            token=args.token,
        )

    if args.command == "import":
        from smartmoney_cub_harness.convergence_cli import (
            import_commit,
            import_file,
            import_list,
        )

        if args.import_command == "file":
            return import_file(
                args.path,
                state_dir=args.state_dir,
                portfolio_id=args.portfolio_id,
                as_json=args.json,
            )
        if args.import_command == "commit":
            return import_commit(
                args.extraction_id,
                rows_path=args.rows,
                state_dir=args.state_dir,
                portfolio_id=args.portfolio_id,
                as_json=args.json,
            )
        if args.import_command == "list":
            return import_list(state_dir=args.state_dir)

    if args.command == "store":
        from smartmoney_cub_harness.convergence_cli import store_backup, store_status

        if args.store_command == "status":
            return store_status(state_dir=args.state_dir, as_json=args.json)
        if args.store_command == "backup":
            return store_backup(args.destination, state_dir=args.state_dir, as_json=args.json)

    if args.command == "skill":
        from smartmoney_cub_harness.convergence_cli import skill_install, skill_show

        if args.skill_command == "install":
            return skill_install(target=args.target, force=args.force, as_json=args.json)
        if args.skill_command == "show":
            return skill_show()

    if args.command == "plugin":
        if args.plugin_command == "list":
            _print_json(
                plugin_list(
                    profile_name=args.profile,
                    plugin_dirs=args.plugin_dir,
                    state_db=args.state_db,
                )
            )
            return 0
        if args.plugin_command == "inspect":
            result = plugin_inspect(args.manifest)
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.plugin_command == "enable":
            result = plugin_enable(
                args.plugin_id,
                profile_name=args.profile,
                plugin_dirs=args.plugin_dir,
                state_db=args.state_db,
            )
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.plugin_command == "disable":
            result = plugin_disable(
                args.plugin_id,
                profile_name=args.profile,
                state_db=args.state_db,
            )
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.plugin_command == "remove":
            result = plugin_remove(args.plugin_id, state_db=args.state_db)
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.plugin_command == "doctor":
            _print_json(
                plugin_doctor(
                    profile_name=args.profile,
                    plugin_dirs=args.plugin_dir,
                    state_db=args.state_db,
                )
            )
            return 0
        if args.plugin_command == "logs":
            _print_json(plugin_logs(args.plugin_id, state_db=args.state_db, limit=args.limit))
            return 0
        if args.plugin_command == "catalog":
            _print_json(plugin_catalog())
            return 0
        if args.plugin_command == "install":
            result = plugin_install(
                args.source,
                profile_name=args.profile,
                state_db=args.state_db,
            )
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.plugin_command == "run":
            result = plugin_run(
                args.plugin_id,
                capability=args.capability,
                request_path=args.request,
                workspace_db=args.workspace_db,
                case_id=args.case_id,
                decision_time=args.decision_time,
                available_at=args.available_at,
                data_source=args.data_source,
                data_quality=args.data_quality,
                result_kind=args.result_kind,
                profile_name=args.profile,
                plugin_dirs=args.plugin_dir,
                state_db=args.state_db,
            )
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        parser.error(f"unknown plugin command: {args.plugin_command}")
        return 2

    if args.command == "profile":
        if args.profile_command == "show":
            _print_json(profile_show(args.name))
            return 0
        if args.profile_command == "dump":
            _print_json(profile_dump(output_path=args.output))
            return 0
        if args.profile_command == "reload":
            _print_json(
                profile_reload(
                    profile_name=args.profile,
                    plugin_dirs=args.plugin_dir,
                    state_db=args.state_db,
                )
            )
            return 0
        parser.error(f"unknown profile command: {args.profile_command}")
        return 2

    if args.command == "share-pack":
        try:
            result = build_share_pack_from_source(
                csv_path=args.csv,
                output_dir=args.output,
                regime=args.regime,
                title=args.title,
                write=args.write,
            )
        except (OSError, ValueError) as exc:
            _print_json(
                {
                    "status": "error",
                    "error": {"code": type(exc).__name__, "message": str(exc)},
                    "safety": SAFETY_DECLARATION,
                }
            )
            return 2
        _print_json(result)
        return 0 if result.get("status") == "ok" else 2

    if args.command == "workspace":
        if args.workspace_command == "add-case":
            result = workspace_add_case(_read_json(args.payload), db_path=args.db)
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.workspace_command == "list-cases":
            _print_json(
                workspace_list_cases(
                    db_path=args.db,
                    action=args.action,
                    symbol=args.symbol,
                    regime=args.regime,
                )
            )
            return 0
        if args.workspace_command == "show-case":
            result = workspace_show_case(args.case_id, db_path=args.db)
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.workspace_command == "record-outcome":
            result = workspace_record_outcome(
                case_id=args.case_id,
                horizon=args.horizon,
                return_pct=args.return_pct,
                max_adverse_excursion_pct=args.max_adverse_excursion_pct,
                outcome_time=args.outcome_time,
                detail=args.detail,
                db_path=args.db,
            )
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.workspace_command == "import-csv":
            result = workspace_import_csv(args.csv_path, db_path=args.db, regime=args.regime)
            _print_json(result)
            return 0 if result["status"] == "ok" else 2
        if args.workspace_command == "summary":
            _print_json(workspace_summary(db_path=args.db))
            return 0
        parser.error(f"unknown workspace command: {args.workspace_command}")
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
