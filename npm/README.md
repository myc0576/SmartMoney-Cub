# smartmoney-cub

A local-first trading journal and review workbench. Import your own fills, see
performance analytics, define and score playbooks, backtest a JSON strategy, and
keep the review assistant alongside. Read-only with respect to markets and
execution.

    npx smartmoney-cub

That command creates a private Python environment under ~/.smartmoney-cub, installs
the harness if it is not there yet, and opens the local web interface on
http://127.0.0.1:8787.

## What it does not do

It does not place, modify, or cancel orders. It does not connect to a broker. It
does not upload your screenshots, PDFs, or CSV exports. It does not send your
account number, name, exact quantities, exact amounts, or exact timestamps to any
external model.

## Commands

    npx smartmoney-cub                      open the local workbench
    npx smartmoney-cub trader serve         open the trading journal
    npx smartmoney-cub doctor               check the local environment
    npx smartmoney-cub install              install or update the Python harness
    npx smartmoney-cub install --with-ocr   add the local OCR engine for screenshots
    npx smartmoney-cub store status         inspect the local store
    npx smartmoney-cub import file PATH     parse a file locally
    npx smartmoney-cub skill install --target codex

## Privacy

Raw files stay on disk in your local state directory. Only redacted structured
fields are sent to a model provider, and every outbound request is recorded in a
local audit table listing which fields were sent and how many values were
replaced. See docs/privacy.md and docs/review-agent.md in the repository.

Safety: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
