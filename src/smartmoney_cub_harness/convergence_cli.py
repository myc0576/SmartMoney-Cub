from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from smartmoney_cub_harness import __version__
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import DEFAULT_PORTFOLIO_ID, Store

# Command line entry points for the convergence workbench. Every command keeps
# the read-only contract and reports the store location instead of absolute
# paths that leak a machine layout.

DEFAULT_STATE_DIR = "state/convergence"


def state_root(state_dir: str | None = None) -> Path:
    return Path(state_dir) if state_dir else Path(DEFAULT_STATE_DIR)


def run_workbench(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    state_dir: str | None = None,
    workspace_db: str | None = None,
    open_browser: bool = True,
    token: str | None = None,
) -> int:
    from smartmoney_cub_harness.workbench.server import (
        bundled_asset_dir,
        is_loopback,
        start_workbench,
    )

    if not is_loopback(host) and not token:
        sys.stderr.write(
            "refusing to bind " + host + " without --token: "
            "a review journal must not be exposed on a network by default\n"
        )
        return 2

    def announce(url: str) -> None:
        sys.stderr.write("smartmoney-cub workbench: " + url + "\n")
        sys.stderr.write("state: " + str(state_root(state_dir)) + "\n")
        sys.stderr.write(SAFETY_DECLARATION + "\n")

    start_workbench(
        root=state_root(state_dir),
        host=host,
        port=port,
        asset_dir=bundled_asset_dir(),
        open_browser=open_browser,
        access_token=token,
        workspace_db=workspace_db,
        ready=announce,
    )
    return 0


def import_file(
    path: str,
    *,
    state_dir: str | None = None,
    portfolio_id: str | None = None,
    as_json: bool = False,
) -> int:
    from smartmoney_cub_harness.workbench.server import WorkbenchService

    source = Path(path)
    if not source.is_file():
        _fail("no such file: " + source.name, as_json=as_json)
        return 2
    service = WorkbenchService(state_root(state_dir))
    try:
        import base64

        payload = {
            "file_name": source.name,
            "media_type": _media_type(source),
            "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
            "portfolio_id": portfolio_id or DEFAULT_PORTFOLIO_ID,
        }
        result = service.upload(payload)
    finally:
        service.close()

    if as_json:
        _print_json(result)
        return 0
    extraction = result["extraction"]
    sys.stdout.write(
        "parsed " + str(extraction["row_count"]) + " row(s) with " + str(extraction["engine"]) + "\n"
    )
    if extraction["status"] == "engine_missing":
        sys.stdout.write(
            "this file needs the local OCR extra: pip install \"smartmoney-cub-harness[ocr]\"\n"
        )
    for row in extraction["rows"]:
        sys.stdout.write(
            "  "
            + str(row.get("trade_date") or "?")
            + " "
            + str(row.get("side") or "?")
            + " "
            + str(row.get("symbol") or "?")
            + " price="
            + str(row.get("price"))
            + " qty="
            + str(row.get("quantity"))
            + "\n"
        )
    sys.stdout.write("extraction_id: " + extraction["extraction_id"] + "\n")
    sys.stdout.write("nothing is written until you run: smcub import commit <extraction_id>\n")
    return 0


def import_commit(
    extraction_id: str,
    *,
    rows_path: str | None = None,
    state_dir: str | None = None,
    portfolio_id: str | None = None,
    as_json: bool = False,
) -> int:
    from smartmoney_cub_harness.workbench.server import WorkbenchService

    service = WorkbenchService(state_root(state_dir))
    try:
        payload: dict[str, Any] = {"extraction_id": extraction_id}
        if portfolio_id:
            payload["portfolio_id"] = portfolio_id
        if rows_path:
            payload["rows"] = json.loads(Path(rows_path).read_text(encoding="utf-8"))
        result = service.commit_import(payload)
    finally:
        service.close()

    if as_json:
        _print_json(result)
        return 0 if result.get("status") != "rejected" else 2
    if result.get("status") == "rejected":
        sys.stdout.write("rejected: no rows were written\n")
        for row in result.get("rejected", []):
            sys.stdout.write("  row " + str(row["row_index"]) + ": " + "; ".join(row["errors"]) + "\n")
        return 2
    sys.stdout.write(
        "committed " + str(result["inserted_count"]) + " row(s), skipped "
        + str(len(result.get("skipped") or [])) + " duplicate row(s)\n"
    )
    sys.stdout.write("ledger status: " + str(result.get("ledger_status")) + "\n")
    return 0


def import_list(*, state_dir: str | None = None) -> int:
    store = Store(state_root(state_dir))
    try:
        documents = store.list_documents()
        counts = store.counts()
    finally:
        store.close()
    sys.stdout.write(
        str(counts["source_document"]) + " local document(s), "
        + str(counts["fill_record"]) + " fill row(s)\n"
    )
    for document in documents:
        sys.stdout.write(
            "  " + document["imported_at"] + "  " + document["source_kind"].ljust(6)
            + "  " + document["file_name"] + "  " + str(document["byte_size"]) + " bytes\n"
        )
    return 0


def store_status(*, state_dir: str | None = None, as_json: bool = False) -> int:
    root = state_root(state_dir)
    store = Store(root)
    try:
        counts = store.counts()
    finally:
        store.close()
    payload = {
        "status": "ok",
        "version": __version__,
        "state_dir": str(root),
        "counts": counts,
        "engine": _engine_status(),
        "safety": SAFETY_DECLARATION,
    }
    if as_json:
        _print_json(payload)
        return 0
    sys.stdout.write("smartmoney-cub " + __version__ + "\n")
    sys.stdout.write("state: " + str(root) + "\n")
    for key, value in counts.items():
        sys.stdout.write("  " + key.ljust(16) + str(value) + "\n")
    engine = payload["engine"]
    sys.stdout.write(
        "local OCR: " + ("available" if engine.get("rapidocr") else "not installed (pip install \"smartmoney-cub-harness[ocr]\")") + "\n"
    )
    sys.stdout.write(SAFETY_DECLARATION + "\n")
    return 0


def store_backup(destination: str, *, state_dir: str | None = None, as_json: bool = False) -> int:
    store = Store(state_root(state_dir))
    try:
        result = store.backup(destination)
    finally:
        store.close()
    if as_json:
        _print_json(result)
        return 0
    sys.stdout.write("backup written: " + result["path"] + "\n")
    return 0


def skill_install(*, target: str = "codex", force: bool = False, as_json: bool = False) -> int:
    from smartmoney_cub_harness.skillpack import install_skill

    result = install_skill(target=target, force=force)
    if as_json:
        _print_json(result)
        return 0 if result["status"] == "ok" else 2
    if result["status"] != "ok":
        sys.stdout.write(result.get("error", "install failed") + "\n")
        return 2
    sys.stdout.write("installed smartmoney-cub skill into " + result["destination"] + "\n")
    sys.stdout.write("run: smcub skill show   (prints the packaged definition)\n")
    return 0


def skill_show() -> int:
    from smartmoney_cub_harness.skillpack import skill_text

    sys.stdout.write(skill_text())
    return 0


def _engine_status() -> dict[str, bool]:
    from smartmoney_cub_harness.extractors import ocr_backend_status

    return ocr_backend_status()


def _media_type(path: Path) -> str:
    mapping = {
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    return mapping.get(path.suffix.lower(), "application/octet-stream")


def _fail(message: str, *, as_json: bool = False) -> None:
    if as_json:
        _print_json({"status": "error", "error": message, "safety": SAFETY_DECLARATION})
    else:
        sys.stderr.write(message + "\n")


def _print_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
