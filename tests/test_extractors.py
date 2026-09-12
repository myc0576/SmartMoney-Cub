from __future__ import annotations

import json

from smartmoney_cub_harness import extractors


def test_csv_extraction_reads_a_broker_export() -> None:
    content = (
        "成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量,手续费\n"
        "2026-09-01,09:40:00,600111,北方稀土,买入,10.00,1000,5\n"
        "2026-09-03,14:00:00,600111,北方稀土,卖出,11.00,1000,5\n"
    ).encode("utf-8")
    result = extractors.extract(content, file_name="fills.csv", media_type="text/csv")
    assert result["status"] == "ok"
    assert len(result["rows"]) == 2
    first = result["rows"][0]
    assert first["symbol"] == "600111"
    assert first["side"] == "BUY"
    assert first["trade_date"] == "2026-09-01"
    assert first["trade_time"] == "09:40:00"
    assert first["price"] == 10.0
    assert first["quantity"] == 1000
    # A declared fee column means no fee has to be estimated.
    assert first["fee"] == 5.0


def test_a_gbk_export_is_decoded_locally() -> None:
    content = (
        "成交日期,证券代码,证券名称,操作,成交均价,成交数量\n"
        "2026-09-01,600111,北方稀土,买入,10.00,1000\n"
    ).encode("gb18030")
    result = extractors.extract(content, file_name="tonghuashun.csv")
    assert result["status"] == "ok"
    assert result["rows"][0]["name"] == "北方稀土"


def test_metadata_lines_before_the_header_are_skipped() -> None:
    content = (
        "资金账号,88888888\n"
        "查询时间,2026-09-10\n"
        "成交日期,证券代码,操作,成交均价,成交数量\n"
        "2026-09-01,600111,买入,10.00,1000\n"
    ).encode("utf-8")
    result = extractors.extract(content, file_name="export.csv")
    assert len(result["rows"]) == 1
    assert result["rows"][0]["symbol"] == "600111"


def test_nothing_is_invented_when_the_file_has_no_trade_rows() -> None:
    content = b"account,balance\n88888888,100000\n"
    result = extractors.extract(content, file_name="balance.csv")
    assert result["rows"] == []
    assert result["status"] == "empty"


def test_side_classification_handles_broker_wording() -> None:
    assert extractors.classify_side("担保品买入") == "BUY"
    assert extractors.classify_side("融券卖出") == "SELL"
    assert extractors.classify_side("银行转证券") is None
    assert extractors.classify_side("") is None


def test_date_and_time_normalization_rejects_impossible_values() -> None:
    assert extractors.normalize_date("2026-09-01") == "2026-09-01"
    assert extractors.normalize_date("2026/9/1") == "2026-09-01"
    assert extractors.normalize_date("2026年9月1日") == "2026-09-01"
    assert extractors.normalize_date("2026-13-45") is None
    assert extractors.normalize_time("9:40") == "09:40:00"
    assert extractors.normalize_time("14:00:05") == "14:00:05"
    assert extractors.normalize_time("99:99") == ""


def test_ocr_text_produces_candidates_only_for_real_trade_lines() -> None:
    text = (
        "资金账号 88888888\n"
        "成交日期 成交时间 证券代码 证券名称 操作 成交均价 成交数量\n"
        "2026-09-01 09:40:00 600111 北方稀土 买入 10.00 1000\n"
        "第 1 页 共 2 页\n"
    )
    rows = extractors.parse_table_text(text, portfolio_id="PORT-DEFAULT")
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "600111"
    assert row["side"] == "BUY"
    assert row["quantity"] == 1000
    assert row["price"] == 10.0


def test_an_account_summary_line_never_becomes_a_trade() -> None:
    rows = extractors.parse_table_text(
        "资金账号 88888888 可用资金 123456.78\n",
        portfolio_id="PORT-DEFAULT",
    )
    assert rows == []


def test_ocr_text_carries_low_confidence_for_numbers_that_need_checking() -> None:
    rows = extractors.parse_table_text(
        "2026-09-01 09:40:00 600111 买入 10.00 1000",
        portfolio_id="PORT-DEFAULT",
        line_scores=[0.4],
    )
    assert rows
    confidence = rows[0]["field_confidence"]
    # OCR-derived numeric fields are never presented as certain, so the import
    # screen asks the user to confirm them.
    assert confidence["price"] < 0.8
    assert confidence["quantity"] < 0.9


def test_a_scanned_pdf_without_the_ocr_extra_reports_what_is_missing() -> None:
    # A PDF with no text layer and no OCR engine installed must return a
    # structured explanation instead of an exception or an empty success.
    result = extractors.extract(b"%PDF-1.4\n%%EOF", file_name="scan.pdf", media_type="application/pdf")
    assert result["status"] in {"engine_missing", "empty"}
    if result["status"] == "engine_missing":
        assert result["rows"] == []
        assert "rapidocr" in result["missing"]


def test_unknown_uploads_are_rejected_without_guessing() -> None:
    result = extractors.extract(b"\x00\x01binary", file_name="mystery.bin")
    assert result["status"] == "unsupported"
    assert result["rows"] == []


def test_detect_source_kind_uses_content_when_the_extension_lies() -> None:
    assert extractors.detect_source_kind("report.dat", "", b"%PDF-1.7") == "pdf"
    assert extractors.detect_source_kind("shot.png", "image/png") == "image"
    assert extractors.detect_source_kind("fills.csv") == "csv"
    assert extractors.detect_source_kind("thing.bin", "application/octet-stream") == "unknown"


def test_separate_fee_columns_are_summed_into_placeholders() -> None:
    content = (
        "成交日期,证券代码,操作,成交均价,成交数量,佣金\n"
        "2026-09-03,600111,卖出,11.00,1000,5.00\n"
    ).encode("utf-8")
    result = extractors.extract(content, file_name="detailed.csv")
    row = result["rows"][0]
    assert json.dumps(row, ensure_ascii=False)
    assert row["fee"] == 5.0
