# Awesome Jev Ecosystem Submission: SmartMoney-Cub

- **Project Name**: SmartMoney-Cub (`smartmoney-cub-harness`)
- **Repository**: [https://github.com/myc0576/Smartmoney-Cub](https://github.com/myc0576/Smartmoney-Cub)
- **Category**: Trading & Financial Review Systems / AI Decision Governance
- **Safety Declaration**: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
- **License**: MIT

---

## 1. Project Overview

`smartmoney-cub-harness` is a local-first, agent-agnostic trading journal and review harness. It sits between quantitative/discretionary trading logs and external AI agents, providing a deterministic evaluation and rule-evolution loop with an absolute ban on live order execution.

Rather than acting as an automated trading bot, SmartMoney-Cub serves as a trusted referee and reflective mirror:
- Captures run envelopes with declarative provenance and temporal boundaries (`available_at <= decision_time`).
- Replays D+1/D+3 trade outcomes to grade decision discipline, invalidation logic, and risk contracts.
- Manages rule candidate evolution via a strict challenger-champion promotion gate requiring human sign-off.

---

## 2. Jev Integration Architecture

SmartMoney-Cub implements first-class support for Jev-compatible review backends via the standardized `smartmoney_cub_harness.jev` module:

1. **Four-Track Financial Question Pack**:
   - `trading-review`: Evidence sufficiency, major counter-evidence, failure mode, review priority.
   - `financial-filings`: Disclosure supports conclusion, internal contradiction, materiality of change, evidence quality, information gap.
   - `industry-events`: Event class, impact scope, duration, epistemic status, supply-chain impact.
   - `macro-policy`: Policy stance, macro direction, impact horizon, availability at decision time.
2. **Pluggable Backends**:
   - `TypeSafeDirectJevBackend`: Low-overhead direct interface with strict schema enforcement.
   - `OpenRouterJevBackend`: Cloud router adapter for comparing multiple reasoning models.
   - **Fail-Closed Design**: Falls back safely without fabricating scores if credentials or endpoints are unavailable.

---

## 3. Benchmark Verification (`finance-jev-v1`)

To provide reproducible, transparent measurement for financial decision reasoning:
- **Suite**: `finance-jev-v1` consisting of 240 frozen offline synthetic cases (60 cases across 4 tracks; 30 dev + 30 holdout per track).
- **Zero Forward-Looking Bias**: Strictly validated so that `available_at <= decision_time` across all cases.
- **Reproducible Artifacts**: Run manifests sealed with SHA-256 integrity hashes; charts generated deterministically via Pillow.
- **Measured Metrics**: Evaluates schema validity, accuracy, macro-F1, FPR, calibration (Brier & ECE), abstention rates, and McNemar test vs baseline.

---

## 4. Quickstart

```bash
# Install harness with dev tools
git clone https://github.com/myc0576/Smartmoney-Cub.git
cd Smartmoney-Cub
pip install -e ".[dev]"

# Run diagnostics and verify safety boundary
smcub doctor

# Run the frozen offline benchmark suite
smcub benchmark run

# Start the local workbench
smcub workbench
```

---

## 5. Contact & Maintainers

- **Maintainer**: SmartMoney-Cub Team
- **Issues & Discussions**: [GitHub Issues](https://github.com/myc0576/Smartmoney-Cub/issues)
