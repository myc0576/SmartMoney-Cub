# User Guide

This harness helps a subjective trader review decisions after evidence arrives. It does not tell you what to trade and does not touch execution.

## 30-Second Quickstart

```bash
pip install -e ".[dev]"
smcub doctor
smcub capture-run --mode after-close --preset toy --sandbox --decision-time "2026-06-01T15:31:00+08:00"
smcub build-outcome tmp/sandbox/20260601/20260601_153100-after-close --horizon d1 --price-source smartmoney_cub_harness:data/sample_prices.json
smcub build-evidence-pack tmp/toy-evidence-pack --sample tmp/sandbox/20260601/20260601_153100-after-close --rule-candidate examples/toy_strategy/sample_rule_candidate.json --horizon d1
smcub replay-evidence-pack tmp/toy-evidence-pack
```

This runs a deterministic offline toy capture, builds the D1 outcome and evidence pack, and verifies the replay result. For the full Agent Loop, run `smcub loop --preset toy --agent-trigger "自进化"`, then inspect `loop_report.md` and `trace.jsonl`.

## First-Run Workbench Path (GUI)

1. Start the local workbench with `npx smartmoney-cub` (or `smcub workbench`) and open `http://127.0.0.1:8787`.
2. From the **Overview** first-run guide, click **Import trades / Try toy sample**.
3. Drop a local broker statement (CSV/TSV/PDF/screenshot) or click **Load offline toy sample (4 round-trips)** to populate the editable review table with synthetic symbols (`TOY.CUB`, `TOY.ALPHA`, `TOY.BETA`).
4. Verify each row, click **Confirm import**, and jump straight to **Overview** or **Insights** to inspect KPIs, cumulative P&L, and evidence-backed pattern candidates.

## Normal Inputs

The public repo ships toy examples only. In private local work, the workflow can structure:

- Trading plan text.
- Trading journal CSV.
- TongHuaShun or broker screenshots.
- Read-only exports.
- Manual notes.

Keep private inputs outside the public repo.

## Review Fields

A useful non-silent observation should carry:

- Decision time.
- Data source.
- Available time.
- Data quality.
- Thesis.
- Invalidation.
- Time stop.
- Give-up conditions.
- D1/D3 outcome.
- Evaluation grade.
- Failure tags.
- Challenger rule candidate if the review suggests a rule change.

## Safe CLI Path

```bash
smcub privacy-audit
smcub loop --preset toy --agent-trigger "自进化"
smcub inspect-artifacts <run_dir>
```

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` must remain present in generated artifacts.
