# Philosophy

The project is built around review, restraint, evidence, and human-machine co-evolution. Its philosophical language must always remain engineering language: no mystic forecasting, no price prediction, no stock recommendation framing.

## Where the 易经 Thinking Lives

The useful part of 易经 here is not divination. It is a vocabulary for cycle, timing, position, change, restraint, and opposing evidence.

| 易经思想 | Harness 模块 | 工程化含义 |
| ---- | ---------- | ----- |
| Market Regime / Sentiment Cycle | Decision labels, outcome tags, Markdown memory | Capture whether the market context was early probing, mainline growth, crowded acceleration, widening divergence, or retreat/waiting. |
| Timing & Position | `decision_time`, `available_at`, D1/D3 horizon | The same pattern can carry different risk depending on where it sits in the emotional cycle. |
| Change vs Invariance | Manifest validation, evaluator, registry | Themes, leaders, and preferences change; provenance, invalidation, discipline, and sample review remain. |
| Advance / Retreat / Restraint | `WATCH`, `AVOID`, `EMPTY_POSITION` | A non-action can be a valid decision when market state does not support action. |
| Opposing Evidence | Agent challenger role | Every thesis should face an opposing thesis before it becomes a rule candidate. |

The five cycle labels used in product language are review labels only:

- **初生**: new theme probing.
- **生长**: mainline confirmation.
- **亢龙**: crowded acceleration.
- **衰退**: divergence expanding.
- **潜藏**: retreat, empty-position review, or waiting.

These labels never imply prediction. They help the trader ask: what did I believe the state was, and did later evidence support that belief?

## Where Systems Engineering Lives

Qian Xuesen-style systems engineering appears as decomposition, integration, feedback, and human-machine collaboration.

| 系统工程思想 | Harness 模块 | 工程化含义 |
| ------ | ---------- | ----- |
| Goal Tree | Review notes, future goal records, rule registry | Separate annual, monthly, single-trade, and review goals so one outcome does not define the system. |
| Decomposition & Integration | `manifest`, `decision`, `outcome`, `evaluation` | Break market state, theme, recognizability, position, risk, psychology, and outcome into fields, then integrate them into review artifacts. |
| Feedback Loop | Plan -> Observe -> Decide -> Record -> Outcome -> Evaluate -> Evolve | Delay judgment until evidence arrives; update rules through review, not impulse. |
| Human-Machine Collaboration | Agent integration contract | Human owns final judgment; AI challenges, structures, archives, reviews, and detects drift. |
| Qualitative-to-Quantitative Review | D1/D3 evaluation, challenger -> champion registry | Turn subjective observation into structured records, then metrics, then governed rule promotion. |

## Semi-Quant Posture

`smartmoney-cub-harness` sits between pure discretionary trading and traditional quant systems.

It does not begin with a fixed alpha model. It begins with the messy human decision: thesis, context, emotion, timing, invalidation, evidence, and later outcome.

It does not remove the trader. It makes the trader's experience auditable.

It is not the strategy itself. It is the container where strategy can mature.

## Human Responsibility

The agent can ask better questions, find drift, preserve evidence, and remember past decisions. It cannot take responsibility for the trade.

The system must preserve this boundary in every document, example, and future
extension. Read-only applies to markets and execution; the trader's own journal is
writable, private, and theirs:

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```
