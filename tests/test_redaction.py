from __future__ import annotations

import json

from smartmoney_cub_harness.redaction import (
    REDACTION_POLICY_VERSION,
    alias_for,
    amount_band,
    prepare_outbound,
    quantity_band,
    scan_for_attachments,
    time_bucket,
)

SALT = "test-salt"


def test_account_and_name_never_reach_the_provider_payload() -> None:
    prepared = prepare_outbound(
        {
            "account": "6222021234567890123",
            "account_no": "88888888",
            "user_name": "张三",
            "id_card": "110101199001011234",
            "phone": "13800138000",
        },
        salt=SALT,
    )
    assert prepared["status"] == "ok"
    serialized = json.dumps(prepared["payload"], ensure_ascii=False)
    for secret in ("6222021234567890123", "88888888", "张三", "110101199001011234", "13800138000"):
        assert secret not in serialized
    assert prepared["redaction_summary"]["counts"]["credential_or_account_key"] >= 1


def test_symbols_and_portfolios_become_device_stable_aliases() -> None:
    prepared = prepare_outbound(
        {"symbol": "600111", "portfolio_id": "PORT-DEFAULT"},
        salt=SALT,
    )
    payload = prepared["payload"]
    assert payload["symbol"] == alias_for("600111", salt=SALT, kind="symbol")
    assert payload["portfolio_id"] == alias_for("PORT-DEFAULT", salt=SALT, kind="portfolio")
    # The alias is stable for the same device salt, so history stays comparable.
    again = prepare_outbound({"symbol": "600111"}, salt=SALT)
    assert again["payload"]["symbol"] == payload["symbol"]
    # A different device salt yields a different alias.
    other = prepare_outbound({"symbol": "600111"}, salt="another-salt")
    assert other["payload"]["symbol"] != payload["symbol"]


def test_exact_quantities_amounts_and_times_are_coarsened() -> None:
    prepared = prepare_outbound(
        {
            "quantity": 12345,
            "amount": 345678.9,
            "price": 28.19,
            "entry_time": "2026-09-01 13:47:22",
            "trade_date": "2026-09-01",
        },
        salt=SALT,
    )
    payload = prepared["payload"]
    assert payload["quantity"] == quantity_band(12345)
    assert payload["amount"] == amount_band(345678.9)
    assert payload["price"].endswith("5") or "-" in payload["price"]
    assert payload["entry_time"] == "13:45-14:00"
    # A date is reduced to a month so a daily pattern is not reconstructable.
    assert payload["trade_date"] == "2026-09"
    assert payload["quantity"] != "12345"
    assert "345678.9" not in json.dumps(payload)


def test_review_relevant_shape_survives_redaction() -> None:
    prepared = prepare_outbound(
        {
            "return_pct": -8.42,
            "holding_days": 3,
            "discipline_score": 60,
            "win_rate": 42.5,
            "profit_factor": 1.8,
            "sample_note": "样本量 25 笔",
        },
        salt=SALT,
    )
    payload = prepared["payload"]
    assert payload["return_pct"] == -8.42
    assert payload["holding_days"] == 3
    assert payload["discipline_score"] == 60
    assert payload["win_rate"] == 42.5
    assert payload["profit_factor"] == 1.8


def test_a_credential_hidden_in_free_text_is_removed() -> None:
    prepared = prepare_outbound(
        {"thesis": "根据 token=abc123secret 对应的接口下单，止损 8.2，联系 13800138000"},
        salt=SALT,
    )
    text = prepared["payload"]["thesis"]
    assert "abc123secret" not in text
    assert "13800138000" not in text
    assert "止损 8.2" in text


def test_paths_and_secrets_are_removed_from_notes() -> None:
    prepared = prepare_outbound(
        {"note": "导出文件在 /Users/someone/Desktop/交割单.csv，key=sk-abcdefghijklmnop"},
        salt=SALT,
    )
    note = prepared["payload"]["note"]
    assert "/Users/someone" not in note
    assert "sk-abcdefghijklmnop" not in note


def test_nested_structures_and_lists_are_redacted_recursively() -> None:
    prepared = prepare_outbound(
        {
            "trades": [
                {"symbol": "000725", "quantity": 5000, "amount": 21000, "account": "888"},
            ],
            "meta": {"portfolio_name": "我的实盘组合"},
        },
        salt=SALT,
    )
    payload = prepared["payload"]
    trade = payload["trades"][0]
    assert trade["symbol"].startswith("symbol-")
    assert trade["account"] == "[REDACTED]"
    assert trade["quantity"] != 5000
    assert payload["meta"]["portfolio_name"].startswith("portfolio-")


def test_an_embedded_attachment_blocks_the_request() -> None:
    prepared = prepare_outbound(
        {"screenshot": "data:image/png;base64," + "A" * 200},
        salt=SALT,
    )
    assert prepared["status"] == "blocked"
    assert prepared["blocked"] is True
    assert prepared["reason"] == "embedded_attachment_material"


def test_declaring_an_attachment_always_blocks() -> None:
    prepared = prepare_outbound({"text": "看一下这张图"}, salt=SALT, attachments_present=True)
    assert prepared["blocked"] is True
    assert prepared["reason"] == "attachments_never_leave_this_machine"
    # There is no override switch, so the payload is absent rather than partial.
    assert "payload" not in prepared


def test_scan_reports_the_offending_path() -> None:
    findings = scan_for_attachments({"request": {"image_data": "data:image/jpeg;base64," + "B" * 100}})
    assert findings == ["request.image_data"]


def test_a_long_opaque_blob_is_treated_as_file_content() -> None:
    import base64

    blob = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 400).decode("ascii")
    findings = scan_for_attachments({"payload": blob})
    assert findings == ["payload"]


def test_payload_hash_is_stable_for_the_same_input() -> None:
    first = prepare_outbound({"symbol": "600111", "quantity": 1000}, salt=SALT)
    second = prepare_outbound({"symbol": "600111", "quantity": 1000}, salt=SALT)
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["redaction_summary"]["policy"] == REDACTION_POLICY_VERSION


def test_sent_keys_are_recorded_without_values() -> None:
    prepared = prepare_outbound({"trades": [{"symbol": "600111"}]}, salt=SALT)
    assert "trades[0].symbol" in prepared["sent_keys"]


def test_time_bucket_rounds_down_to_a_quarter_hour() -> None:
    assert time_bucket("2026-09-01 09:31:00") == "09:30-09:45"
    assert time_bucket("2026-09-01 14:59:00") == "14:45-15:00"
    assert time_bucket("") == "unknown"

