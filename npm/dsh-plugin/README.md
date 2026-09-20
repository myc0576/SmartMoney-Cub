# smartmoney-cub-dsh-plugin

DeepSeek Harness (DSH) stdio sidecar plugin for the SmartMoney-Cub review workbench.

## Protocol & Safety Boundary

- **Protocol**: `smartmoney_cub_dsh_stdio.v1`
- **Profile**: `smartmoney-review`
- **Safety Declaration**: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

### Allowed Capabilities (Review Lifecycle Only)
- `review_envelope`
- `review_events`
- `review_cancel`
- `review_resume`
- `review_fork`
- `review_close`
- `heartbeat`
- `teardown`

### Forbidden Capabilities (Fail-Closed)
- `shell`, `filesystem`, `network`, `web`, `jobs`, `workflow`, `subagent`, `agent-team`, `broker`, `order`, `trade`, `account`, `order_cancel`

## Usage

Run via stdio JSON-RPC 2.0:

```bash
npx smartmoney-cub-dsh-plugin
```

Supports clean teardown via `teardown` method or standard POSIX signals.

