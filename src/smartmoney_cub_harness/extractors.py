from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# Local extraction for broker screenshots, PDFs, and CSV exports.
#
# Everything in this module runs on this machine. The engine is optional: when
# neither OCR backend is installed the caller still gets a structured response
# explaining what is missing, and the raw file stays untouched on disk.

CSV_SUFFIXES = {".csv", ".tsv", ".txt"}
EXCEL_SUFFIXES = {".xls", ".xlsx"}
JSON_SUFFIXES = {".json"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
PDF_SUFFIXES = {".pdf"}

MIN_PDF_TEXT_CHARS = 40

BUY_WORDS = ("买入", "买", "担保品买入", "融资买入", "证券买入", "buy")
SELL_WORDS = ("卖出", "卖", "担保品卖出", "融券卖出", "证券卖出", "sell")
NON_TRADE_WORDS = ("申购", "配号", "红利", "股息", "转账", "银证", "利息", "中签", "新股")

DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
DATE_COMPACT_RE = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
DATE_SLASH_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(20\d{2})(?!\d)")
TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")
TIME_COMPACT_RE = re.compile(r"(?<!\d)([01]\d|2[0-3])([0-5]\d)([0-5]\d)(?!\d)")
SYMBOL_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
NUMBER_RE = re.compile(r"(?<![\d.])(\d{1,9}(?:\.\d{1,4})?)(?![\d])")

HEADER_HINTS = (
    "证券代码", "股票代码", "代码", "成交日期", "发生日期", "交易日期",
    "买卖标志", "操作", "业务名称", "symbol", "code", "成交均价", "成交数量", "trade_date"
)


def ocr_backend_status() -> dict[str, Any]:
    """Report which optional local engines are importable."""
    return {
        "rapidocr": importlib.util.find_spec("rapidocr") is not None,
        "onnxruntime": importlib.util.find_spec("onnxruntime") is not None,
        "pypdf": importlib.util.find_spec("pypdf") is not None,
        "pypdfium2": importlib.util.find_spec("pypdfium2") is not None,
        "safety": SAFETY_DECLARATION,
    }


def detect_source_kind(file_name: str, media_type: str = "", content: bytes = b"") -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in CSV_SUFFIXES:
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".xls":
        return "xls"
    if suffix in JSON_SUFFIXES:
        return "json"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in PDF_SUFFIXES or media_type == "application/pdf" or content[:4] == b"%PDF":
        return "pdf"
    lowered = (media_type or "").lower()
    if lowered.startswith("image/"):
        return "image"
    if "openxmlformats" in lowered:
        return "xlsx"
    if "ms-excel" in lowered:
        return "xls"
    if "json" in lowered or content[:1] in (b"{", b"["):
        return "json"
    if lowered.startswith("text/") or lowered in {"application/csv", "text/csv"}:
        return "csv"
    return "unknown"


def extract(
    content: bytes,
    *,
    file_name: str,
    media_type: str = "",
    source_kind: str | None = None,
    portfolio_id: str = "PORT-DEFAULT",
) -> dict[str, Any]:
    kind = source_kind or detect_source_kind(file_name, media_type, content)
    if kind == "csv":
        return extract_csv(content, file_name=file_name, portfolio_id=portfolio_id)
    if kind == "xls":
        return extract_xls(content, file_name=file_name, portfolio_id=portfolio_id)
    if kind == "xlsx":
        return extract_xlsx(content, file_name=file_name, portfolio_id=portfolio_id)
    if kind == "json":
        return extract_json(content, file_name=file_name, portfolio_id=portfolio_id)
    if kind == "pdf":
        return extract_pdf(content, file_name=file_name, portfolio_id=portfolio_id)
    if kind == "image":
        return extract_image(content, file_name=file_name, portfolio_id=portfolio_id)
    return {
        "status": "unsupported",
        "engine": "none",
        "engine_version": "",
        "reason": "unrecognized_source_kind",
        "rows": [],
        "mean_confidence": None,
        "safety": SAFETY_DECLARATION,
    }


# ---- CSV ----------------------------------------------------------------


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312", "big5", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def _detect_delimiter(line: str) -> str:
    counts = {
        "\t": line.count("\t"),
        ",": line.count(","),
        ";": line.count(";"),
        "|": line.count("|"),
    }
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def extract_csv(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    text = decode_text(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return _empty_result("csv", "csv", file_name, reason="empty_file")

    start_index = 0
    for index, line in enumerate(lines[:25]):
        if any(hint in line for hint in HEADER_HINTS):
            start_index = index
            break

    delimiter = _detect_delimiter(lines[start_index])
    reader = csv.DictReader(io.StringIO("\n".join(lines[start_index:])), delimiter=delimiter)
    rows: list[dict[str, Any]] = []
    for row_index, raw in enumerate(reader):
        if not raw:
            continue
        clean = {str(key).strip().lstrip("\ufeff"): (value or "").strip() for key, value in raw.items() if key}
        if not any(clean.values()):
            continue
        candidate = _candidate_from_mapping(clean, portfolio_id=portfolio_id, row_index=row_index)
        if candidate:
            rows.append(candidate)

    return {
        "status": "ok" if rows else "empty",
        "engine": "csv",
        "engine_version": "builtin",
        "file_name": file_name,
        "rows": rows,
        "mean_confidence": _mean_confidence(rows),
        "safety": SAFETY_DECLARATION,
    }


def _parse_table_rows(
    table_rows: list[list[str]],
    *,
    file_name: str,
    portfolio_id: str,
    engine: str,
) -> dict[str, Any]:
    if not table_rows:
        return _empty_result(engine, engine, file_name, reason="empty_table")

    start_index = 0
    for idx, r in enumerate(table_rows[:25]):
        line_str = " ".join(r)
        if any(hint in line_str for hint in HEADER_HINTS):
            start_index = idx
            break

    headers = [str(h).strip().lstrip("\ufeff") for h in table_rows[start_index]]
    rows: list[dict[str, Any]] = []
    for row_index, raw_cells in enumerate(table_rows[start_index + 1:]):
        clean: dict[str, Any] = {}
        for col_idx, col_name in enumerate(headers):
            if not col_name:
                continue
            val = raw_cells[col_idx] if col_idx < len(raw_cells) else ""
            clean[col_name] = str(val).strip()
        if not any(clean.values()):
            continue
        candidate = _candidate_from_mapping(clean, portfolio_id=portfolio_id, row_index=row_index)
        if candidate:
            rows.append(candidate)

    return {
        "status": "ok" if rows else "empty",
        "engine": engine,
        "engine_version": "builtin",
        "file_name": file_name,
        "rows": rows,
        "mean_confidence": _mean_confidence(rows),
        "safety": SAFETY_DECLARATION,
    }


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._in_cell = False
            self._current_row.append("".join(self._current_cell).strip())
        elif tag == "tr":
            if any(self._current_row):
                self.rows.append(self._current_row)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def extract_html_table(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    text = decode_text(content)
    parser = _HTMLTableParser()
    parser.feed(text)
    return _parse_table_rows(parser.rows, file_name=file_name, portfolio_id=portfolio_id, engine="html_table")


def extract_xml_spreadsheet(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    text = decode_text(content)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return _empty_result("xml_spreadsheet", "xml_spreadsheet", file_name, reason="invalid_xml")
    table_rows: list[list[str]] = []
    for row in root.findall(".//{*}Row"):
        cells = row.findall("{*}Cell")
        row_vals: list[str] = []
        for cell in cells:
            data = cell.find("{*}Data")
            row_vals.append((data.text or "").strip() if data is not None else "")
        if any(row_vals):
            table_rows.append(row_vals)
    return _parse_table_rows(table_rows, file_name=file_name, portfolio_id=portfolio_id, engine="xml_spreadsheet")


def extract_xlsx(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as z:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.findall(".//{*}si"):
                    parts = [t.text or "" for t in si.findall(".//{*}t")]
                    shared_strings.append("".join(parts))

            sheet_names = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            if not sheet_names:
                return _empty_result("xlsx", "xlsx", file_name, reason="no_worksheets_found")
            sheet_names.sort()
            sheet_root = ET.fromstring(z.read(sheet_names[0]))

            def col_index(cell_ref: str) -> int:
                letters = "".join(c for c in cell_ref if c.isalpha())
                idx = 0
                for ch in letters.upper():
                    idx = idx * 26 + (ord(ch) - ord("A") + 1)
                return max(0, idx - 1)

            table_rows: list[list[str]] = []
            for row in sheet_root.findall(".//{*}row"):
                cells = row.findall("{*}c")
                if not cells:
                    continue
                row_vals: list[str] = []
                for cell in cells:
                    r_attr = cell.get("r", "")
                    t_attr = cell.get("t", "")
                    v_tag = cell.find("{*}v")
                    is_tag = cell.find("{*}is")
                    target_col = col_index(r_attr) if r_attr else len(row_vals)
                    while len(row_vals) < target_col:
                        row_vals.append("")
                    val = ""
                    if t_attr == "s" and v_tag is not None and v_tag.text:
                        try:
                            val = shared_strings[int(v_tag.text)]
                        except (IndexError, ValueError):
                            val = v_tag.text or ""
                    elif t_attr == "inlineStr" and is_tag is not None:
                        val = "".join(t.text or "" for t in is_tag.findall(".//{*}t"))
                    elif v_tag is not None and v_tag.text:
                        val = v_tag.text
                    row_vals.append(val.strip())
                if any(row_vals):
                    table_rows.append(row_vals)
            return _parse_table_rows(table_rows, file_name=file_name, portfolio_id=portfolio_id, engine="xlsx")
    except Exception as err:
        return _empty_result("xlsx", "xlsx", file_name, reason=f"xlsx_read_error_{err}")


def extract_xls(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    if content.startswith(b"PK\x03\x04"):
        return extract_xlsx(content, file_name=file_name, portfolio_id=portfolio_id)
    raw_head = content[:500].lower()
    if b"<?xml" in raw_head and (b"workbook" in raw_head or b"worksheet" in raw_head):
        return extract_xml_spreadsheet(content, file_name=file_name, portfolio_id=portfolio_id)
    if b"<html" in raw_head or b"<!doctype" in raw_head or b"<table" in raw_head:
        return extract_html_table(content, file_name=file_name, portfolio_id=portfolio_id)
    result = extract_csv(content, file_name=file_name, portfolio_id=portfolio_id)
    return {
        "status": result["status"],
        "engine": "xls_text",
        "engine_version": "builtin",
        "file_name": file_name,
        "rows": result["rows"],
        "mean_confidence": result["mean_confidence"],
        "safety": SAFETY_DECLARATION,
    }


def extract_json(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    text = decode_text(content)
    try:
        data = json.loads(text)
    except Exception:
        return _empty_result("json", "json", file_name, reason="invalid_json")

    items: list[dict[str, Any]] = []
    if isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for candidate_key in ("trades", "fills", "records", "rows", "data", "items"):
            if isinstance(data.get(candidate_key), list):
                items = [x for x in data[candidate_key] if isinstance(x, dict)]
                break
        if not items:
            items = [data]

    rows: list[dict[str, Any]] = []
    for row_index, raw in enumerate(items):
        candidate = _candidate_from_mapping(raw, portfolio_id=portfolio_id, row_index=row_index)
        if candidate:
            rows.append(candidate)

    return {
        "status": "ok" if rows else "empty",
        "engine": "json",
        "engine_version": "builtin",
        "file_name": file_name,
        "rows": rows,
        "mean_confidence": _mean_confidence(rows),
        "safety": SAFETY_DECLARATION,
    }


def _candidate_from_mapping(raw: dict[str, Any], *, portfolio_id: str, row_index: int) -> dict[str, Any] | None:
    def pick(*keys: str) -> Any:
        for key in keys:
            for candidate_key, value in raw.items():
                if candidate_key == key or candidate_key.lower() == key.lower():
                    if value not in (None, ""):
                        return value
        return None

    symbol_raw = pick("证券代码", "股票代码", "代码", "symbol", "code", "ticker")
    action_raw = pick("操作", "买卖标志", "业务名称", "交易类别", "action", "side")
    date_raw = pick("成交日期", "发生日期", "交易日期", "date", "trade_date")
    if symbol_raw is None and date_raw is None and action_raw is None:
        return None

    symbol_match = SYMBOL_RE.search(str(symbol_raw or ""))
    symbol = symbol_match.group(1) if symbol_match else str(symbol_raw or "").strip()
    side = classify_side(action_raw)
    trade_date = normalize_date(str(date_raw or ""))
    trade_time = normalize_time(str(pick("成交时间", "委托时间", "时间", "time") or ""))
    price = to_float(pick("成交均价", "成交价格", "成交价", "委托价格", "价格", "price"))
    quantity = to_int(pick("成交数量", "成交量", "数量", "volume", "quantity", "shares"))

    # Fee aggregation: check explicit total fee, otherwise sum fee components.
    fee_keys = ("手续费", "佣金", "印花税", "过户费", "其他费用", "规费", "经手费", "证管费", "结算费")
    explicit_total = pick("总费用", "费用合计", "合计费用", "total_fee")
    if explicit_total is not None and to_float(explicit_total) is not None:
        fee = abs(to_float(explicit_total) or 0.0)
    else:
        components = []
        for key in fee_keys:
            val = pick(key)
            if val is not None:
                flt = to_float(val)
                if flt is not None:
                    components.append(abs(flt))
        if components:
            fee = round(sum(components), 4)
        else:
            fee = to_float(pick("费用", "fee", "commission"))
            if fee is not None:
                fee = abs(fee)

    field_confidence = {
        "trade_date": 1.0 if trade_date else 0.0,
        "trade_time": 1.0 if trade_time else 0.0,
        "symbol": 1.0 if symbol_match else 0.0,
        "side": 1.0 if side else 0.0,
        "price": 1.0 if price is not None else 0.0,
        "quantity": 1.0 if quantity is not None else 0.0,
    }
    warnings: list[str] = []
    if symbol and not symbol_match:
        warnings.append("symbol_is_not_six_digits")
    if any(word in str(action_raw or "") for word in NON_TRADE_WORDS):
        warnings.append("row_may_not_be_a_trade")

    return {
        "portfolio_id": portfolio_id,
        "row_index": row_index,
        "trade_date": trade_date,
        "trade_time": trade_time,
        "symbol": symbol,
        "name": str(pick("证券名称", "股票名称", "名称", "name") or "").strip(),
        "side": side,
        "price": price,
        "quantity": quantity,
        "fee": fee,
        "thesis": str(pick("买入理由", "理由", "thesis", "note", "备注") or "").strip(),
        "invalidation_price": to_float(pick("止损价", "止损", "invalidation_price")),
        "regime": str(pick("情绪周期", "周期", "regime") or "").strip(),
        "field_confidence": field_confidence,
        "raw_text": " | ".join(f"{k}={v}" for k, v in raw.items() if v not in (None, "")),
        "warnings": warnings,
    }


# ---- PDF ----------------------------------------------------------------


def extract_pdf(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    text = ""
    engine = "pypdf"
    engine_version = "unknown"
    if importlib.util.find_spec("pypdf") is not None:
        import pypdf  # noqa: PLC0415 - optional dependency, imported on demand

        engine_version = getattr(pypdf, "__version__", "unknown")
        reader = pypdf.PdfReader(io.BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)

    if len(text.strip()) >= MIN_PDF_TEXT_CHARS:
        rows = parse_table_text(text, portfolio_id=portfolio_id)
        return {
            "status": "ok" if rows else "empty",
            "engine": engine,
            "engine_version": engine_version,
            "file_name": file_name,
            "rows": rows,
            "mean_confidence": _mean_confidence(rows),
            "text_chars": len(text),
            "safety": SAFETY_DECLARATION,
        }

    # No usable text layer: this is a scanned PDF, so it needs local OCR.
    return _ocr_pdf(content, file_name=file_name, portfolio_id=portfolio_id)


def _ocr_pdf(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    if importlib.util.find_spec("pypdfium2") is None or not ocr_backend_status()["rapidocr"]:
        return {
            "status": "engine_missing",
            "engine": "rapidocr",
            "engine_version": "",
            "file_name": file_name,
            "rows": [],
            "mean_confidence": None,
            "reason": "scanned_pdf_needs_local_ocr",
            "missing": _missing_engine_names(),
            "safety": SAFETY_DECLARATION,
        }

    import pypdfium2  # noqa: PLC0415

    pdf = pypdfium2.PdfDocument(io.BytesIO(content))
    pages_text: list[str] = []
    for index in range(len(pdf)):
        page = pdf[index]
        bitmap = page.render(scale=2.0)
        image = bitmap.to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        pages_text.append(ocr_image_bytes(buffer.getvalue())["text"])
    text = "\n".join(pages_text)
    rows = parse_table_text(text, portfolio_id=portfolio_id)
    return {
        "status": "ok" if rows else "empty",
        "engine": "rapidocr+pypdfium2",
        "engine_version": "local",
        "file_name": file_name,
        "rows": rows,
        "mean_confidence": _mean_confidence(rows),
        "text_chars": len(text),
        "safety": SAFETY_DECLARATION,
    }


# ---- images -------------------------------------------------------------


def extract_image(content: bytes, *, file_name: str, portfolio_id: str) -> dict[str, Any]:
    status = ocr_backend_status()
    if not status["rapidocr"]:
        return {
            "status": "engine_missing",
            "engine": "rapidocr",
            "engine_version": "",
            "file_name": file_name,
            "rows": [],
            "mean_confidence": None,
            "reason": "image_needs_local_ocr",
            "missing": _missing_engine_names(),
            "safety": SAFETY_DECLARATION,
        }
    result = ocr_image_bytes(content)
    rows = parse_table_text(result["text"], portfolio_id=portfolio_id, line_scores=result["line_scores"])
    return {
        "status": "ok" if rows else "empty",
        "engine": "rapidocr",
        "engine_version": result.get("version") or "local",
        "file_name": file_name,
        "rows": rows,
        "mean_confidence": _mean_confidence(rows),
        "text_chars": len(result["text"]),
        "safety": SAFETY_DECLARATION,
    }


def _missing_engine_names() -> list[str]:
    status = ocr_backend_status()
    missing = []
    if not status["rapidocr"]:
        missing.append("rapidocr")
    if not status["pypdfium2"]:
        missing.append("pypdfium2")
    return missing


def ocr_image_bytes(content: bytes) -> dict[str, Any]:
    """Run local OCR on image bytes and return text plus per-line confidence."""
    engine = _rapidocr_engine()
    result = engine(content)
    lines: list[str] = []
    scores: list[float] = []
    texts = getattr(result, "txts", None)
    boxes = getattr(result, "boxes", None)
    line_scores = getattr(result, "scores", None)
    if texts is not None:
        for index, text in enumerate(texts):
            lines.append(str(text))
            scores.append(float(line_scores[index]) if line_scores is not None else 1.0)
        del boxes
    else:
        for item in result or []:
            _box, text, score = item
            lines.append(str(text))
            scores.append(float(score))
    return {
        "text": "\n".join(lines),
        "line_scores": scores,
        "mean_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
    }


_RAPIDOCR_ENGINE: Any = None


def _rapidocr_engine() -> Any:
    # Loading the model costs seconds, so one process keeps a single instance.
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        from rapidocr import RapidOCR  # noqa: PLC0415

        _RAPIDOCR_ENGINE = RapidOCR()
    return _RAPIDOCR_ENGINE


# ---- text table parsing -------------------------------------------------


def parse_table_text(
    text: str,
    *,
    portfolio_id: str,
    line_scores: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Pull trade rows out of OCR or PDF text.

    Rows are only produced when a date and a six-digit symbol are both present,
    so a header, a page number, or an account summary cannot become a trade.
    """
    rows: list[dict[str, Any]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        symbol_match = SYMBOL_RE.search(line)
        date_match = DATE_RE.search(line)
        # A wrapped row is common in PDFs: the date lands on one line and the
        # symbol on the next. Only join lines when this line already looks like
        # part of a row, so a header or a page footer cannot pull a real trade
        # from the following line and duplicate it.
        window = line
        if (symbol_match is None) != (date_match is None) and index + 1 < len(lines):
            window = line + " " + lines[index + 1]
            symbol_match = symbol_match or SYMBOL_RE.search(window)
            date_match = date_match or DATE_RE.search(window)
        if not symbol_match or not date_match:
            continue
        side = classify_side(window)
        if side is None:
            continue

        score = line_scores[index] if line_scores and index < len(line_scores) else 0.6
        candidate = _candidate_from_text(
            window,
            portfolio_id=portfolio_id,
            row_index=index,
            symbol=symbol_match.group(1),
            trade_date=normalize_date(date_match.group(0)),
            side=side,
            base_confidence=score,
        )
        rows.append(candidate)
    return rows


def _candidate_from_text(
    line: str,
    *,
    portfolio_id: str,
    row_index: int,
    symbol: str,
    trade_date: str,
    side: str,
    base_confidence: float,
) -> dict[str, Any]:
    time_match = TIME_RE.search(line)
    remainder = line
    for match in (DATE_RE.search(line), TIME_RE.search(line)):
        if match:
            remainder = remainder.replace(match.group(0), " ")
    remainder = SYMBOL_RE.sub(" ", remainder)
    for word in BUY_WORDS + SELL_WORDS:
        remainder = remainder.replace(word, " ")

    numbers = [float(value) for value in NUMBER_RE.findall(remainder)]
    # Quantity is a whole number of shares; the price is a decimal. Separating
    # them this way is a heuristic, so the confidence stays below certain and
    # the user is asked to check each field.
    integer_like = [value for value in numbers if value >= 100 and float(value).is_integer()]
    decimal_like = [value for value in numbers if not float(value).is_integer() or value < 100]
    quantity = int(max(integer_like)) if integer_like else None
    price = decimal_like[0] if decimal_like else None
    amount_like = [value for value in numbers if value >= 10000]
    if price is None and amount_like and quantity:
        price = round(amount_like[0] / quantity, 4)

    name_match = re.search(r"[\u4e00-\u9fa5]{2,6}", remainder)
    confidence_scale = 0.6 + 0.4 * max(0.0, min(1.0, base_confidence))
    field_confidence = {
        "trade_date": round(0.9 * confidence_scale, 3),
        "trade_time": round(0.8 * confidence_scale, 3) if time_match else 0.0,
        "symbol": round(0.95 * confidence_scale, 3),
        "side": round(0.85 * confidence_scale, 3),
        "price": round(0.6 * confidence_scale, 3) if price is not None else 0.0,
        "quantity": round(0.7 * confidence_scale, 3) if quantity is not None else 0.0,
    }
    warnings: list[str] = []
    if time_match is None:
        warnings.append("trade_time_not_found")
    if price is None:
        warnings.append("price_not_found")
    if quantity is None:
        warnings.append("quantity_not_found")
    if any(word in line for word in NON_TRADE_WORDS):
        warnings.append("row_may_not_be_a_trade")

    return {
        "portfolio_id": portfolio_id,
        "row_index": row_index,
        "trade_date": trade_date,
        "trade_time": normalize_time(time_match.group(0)) if time_match else "",
        "symbol": symbol,
        "name": name_match.group(0) if name_match else "",
        "side": side,
        "price": price,
        "quantity": quantity,
        "fee": None,
        "thesis": "",
        "invalidation_price": None,
        "regime": "",
        "field_confidence": field_confidence,
        "raw_text": line,
        "warnings": warnings,
    }


def classify_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    for word in SELL_WORDS:
        if word in text:
            return "SELL"
    for word in BUY_WORDS:
        if word in text:
            return "BUY"
    return None


def normalize_date(value: str) -> str | None:
    text = str(value or "").strip()
    match = DATE_RE.search(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None
    compact = DATE_COMPACT_RE.search(text)
    if compact:
        year, month, day = (int(part) for part in compact.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None
    slash = DATE_SLASH_RE.search(text)
    if slash:
        m, d, y = (int(part) for part in slash.groups())
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def normalize_time(value: str) -> str:
    text = str(value or "").strip()
    match = TIME_RE.search(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        second = int(match.group(3)) if match.group(3) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
            return f"{hour:02d}:{minute:02d}:{second:02d}"
        return ""
    compact = TIME_COMPACT_RE.search(text)
    if compact:
        hour, minute, second = (int(part) for part in compact.groups())
        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
            return f"{hour:02d}:{minute:02d}:{second:02d}"
    return ""


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("¥", "").replace("￥", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(abs(number))


def _mean_confidence(rows: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for row in rows:
        values.extend(float(score) for score in (row.get("field_confidence") or {}).values())
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _empty_result(engine: str, name: str, file_name: str, *, reason: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "engine": name,
        "engine_version": engine,
        "file_name": file_name,
        "rows": [],
        "mean_confidence": None,
        "reason": reason,
        "safety": SAFETY_DECLARATION,
    }
