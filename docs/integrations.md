# Integrations

`smartmoney-cub-harness` can reference and learn from strong open-source projects, but every integration stays inside the read-only review contract.

The goal is not to create stronger execution signals. The goal is to turn external analysis, reports, skills, and data shapes into better local review artifacts.

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

## Integration Contract

Every integration must preserve these rules:

- Inputs are read-only.
- Public examples use toy offline data only.
- External reports are evidence for review, not trading instructions.
- Agent outputs may create challenger rule candidates only.
- Champion mutation requires explicit human confirmation.
- No integration may place orders, cancel orders, modify accounts, automate brokers, or handle credentials.
- No integration may publish real trades, real watchlists, account data, private strategy prompts, or local private paths.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `recommended-companion` | Useful alongside the harness, but not imported or executed by the harness runtime. |
| `reserved-slot` | A category intentionally left open for future open-source integrations. |
| `documented-adapter` | A documented local pattern exists, but it remains read-only and optional. |
| `optional-bridge` | A local bridge exists, but users must explicitly install and configure the upstream tool before use. |
| `runtime-integrated` | Code, tests, and docs prove the integration is part of the harness runtime. |

Do not label a project `runtime-integrated` until the repository contains the code path, tests, and safety documentation that prove it.

## Plugin Protocol

External projects are now integrated through the plugin protocol in
[plugins.md](plugins.md) rather than by editing the core. The runtime discovers,
validates, loads, and injects plugins automatically; installation, network access,
and model access stay user-initiated.

The curated catalog is available offline:

```bash
smcub plugin catalog
```

It records three integration levels — `companion`, `adapter`, and
`runtime-plugin` — and the boundary each project must respect. A catalog entry
grades the project; it never ships as a bundled dependency. The core release keeps
`dependencies = []` in `pyproject.toml`.

## Current Matrix

| Project / Category | Status | Harness Role | Required Boundary |
| --- | --- | --- | --- |
| [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | `recommended-companion` | External analysis skill and narrative inspiration; outputs may be saved locally and reviewed by reviewer / challenger agents. | Do not call it an embedded dependency. Do not convert its analysis into buy/sell instructions. |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | `documented-adapter` / `optional-bridge` | User-selected external LLM multi-agent analysis engine. Users may run TradingAgents locally to produce candidate reports, debate summaries, risk notes, watchlist rationale, or decision evidence, then import the output as a review packet. | Users configure their own LLM/API keys outside this repository. The harness must not store, collect, upload, or print key values; must not connect to brokers; and must not convert TradingAgents output into order intent, broker action, or execution plans. |
| Data-source adapters | `reserved-slot` | Normalize read-only exports, toy fixtures, or public examples into manifests. | No broker execution, no account mutation, no credential capture. |
| Report generators | `reserved-slot` | Render loop reports, case records, and ledgers for local reading. | No upload of private review artifacts. |
| Agent skills | `reserved-slot` | Improve reviewer, challenger, archivist, and drift-detector workflows. | No role may bypass the harness contract or promote champion rules automatically. |
| Evaluation / backtest tools | `reserved-slot` | Help evaluate challenger candidates and sample quality. | No future leakage and no execution recommendation surface. |
| Knowledge-memory tools | `reserved-slot` | Organize Markdown memory, case banks, and evolution ledgers. | No cloud sync requirement and no private trading logic publication. |

## UZI-Skill Positioning

UZI-Skill is a strong example of agent-facing financial analysis packaging and a useful companion project for users who already run it in their own agent environment.

In this harness, UZI-Skill should be described carefully:

- Good: "recommended companion", "ecosystem slot", "external analysis that can be reviewed locally".
- Good: "its output can become read-only evidence inside a review packet".
- Not allowed: "built-in integration", unless runtime code and tests are added.
- Not allowed: "use this analysis to trade", "auto-trade from UZI output", or any equivalent execution framing.

## TradingAgents Positioning

TradingAgents is a powerful external LLM multi-agent financial analysis framework. In this project, it is only an external optional analysis engine.

Allowed contributions:

- Candidate reports.
- Debate summaries.
- Risk notes.
- Watchlist rationale.
- Decision evidence.

Not allowed contributions:

- Order intent.
- Broker action.
- Execution plan.
- Account operation.
- Automatic champion mutation.

Current status is `documented-adapter` / `optional-bridge`. It may only be called `runtime-integrated` after this repository contains code, tests, and safety documentation proving the integration remains read-only, local-first, and human-gated.

## Future Integration Checklist

Before adding any new project to the README matrix:

1. Identify the integration status.
2. State the read-only input or artifact it contributes.
3. State what the harness must never do with it.
4. Confirm public examples remain toy-only.
5. Confirm the safety declaration appears in any new manifest, decision, outcome, evaluation, registry, doctor, or loop output touched by the integration.
6. Add tests when the integration becomes runtime behavior.
7. For any LLM-based integration, declare that users configure their own keys outside this repository.
8. Confirm keys never enter artifacts, git, stdout plaintext, or test fixtures.
9. Confirm network calls default to disabled unless the user explicitly provides `--allow-network` and `--ack-external-llm` or an equivalent local consent gate.

## Human Gate

Integrations may improve review quality, evidence organization, and challenger suggestions. They must not turn the harness into an execution system.

Champion rule changes remain human-gated:

```bash
smcub confirm-promotion state/self_evolve/<loop_id>/promotion_packet.json --decision promote --note "manual approval"
```
