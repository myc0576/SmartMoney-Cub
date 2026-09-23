"""Interactive Brokers Flex Web Service read-only adapter."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .manifests import get_manifest
from .models import ConnectionAccount, ConnectionCursor, CredentialBundle, EventPage, NormalizedEvent, NormalizedPosition, ScopeValidation
from .protocol import PermissionConnectionError, TransientConnectionError
from .http import open_without_redirect


class FlexTransport:
    def __init__(self, *, base_url: str = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService", timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url != "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService":
            raise ValueError("ibkr_official_endpoint_required")
        self.timeout = timeout

    def request(self, path: str, params: Mapping[str, Any]) -> bytes:
        if path not in ("SendRequest", "GetStatement"):
            raise ValueError("ibkr_read_endpoint_required")
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        request = urllib.request.Request(f"{self.base_url}/{path.lstrip('/')}?{query}", headers={"Accept": "application/xml", "User-Agent": "SmartMoney-Cub/1.0"})
        try:
            with open_without_redirect(request, timeout=self.timeout) as response:
                payload = response.read(64 * 1024 * 1024 + 1)
                if len(payload) > 64 * 1024 * 1024:
                    raise ValueError("ibkr_statement_too_large")
                return payload
        except TimeoutError as exc:
            raise TransientConnectionError("ibkr_flex_timeout") from exc
        except Exception as exc:
            raise RuntimeError(f"ibkr_flex_http_error:{type(exc).__name__}") from None


def _text(root: ET.Element | None, wanted: str) -> str | None:
    if root is None:
        return None
    wanted = wanted.lower()
    for element in root.iter():
        if element.tag.lower().split("}")[-1] == wanted and element.text and element.text.strip():
            return element.text.strip()
        for key, value in element.attrib.items():
            if key.lower() == wanted and value:
                return value
    return None


def _safe_xml(payload: bytes) -> ET.Element:
    if len(payload) > 64 * 1024 * 1024 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("ibkr_flex_unsafe_xml")
    return ET.fromstring(payload)


def _time(value: Any) -> str | None:
    text = str(value or "").strip().replace(",", "").replace(";", "")
    if len(text) == 14 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}T{text[8:10]}:{text[10:12]}:{text[12:14]}"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text or None


def _absolute(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return abs(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return value


def _hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class IBKRFlexConnection:
    def __init__(self, transport: FlexTransport, credentials: CredentialBundle, *, account_id: str | None = None, query_id: str | None = None, page_size: int = 1000) -> None:
        self.transport, self._credentials = transport, credentials
        self.account_id = account_id
        self.query_id = query_id or str(credentials.values.get("query_id") or "")
        self.page_size = page_size
        if not 1 <= page_size <= 1000:
            raise ValueError("ibkr_page_size_out_of_range")
        self._disconnected = False
        self._report: ET.Element | None = None
        self._fingerprint: str | None = None
        self._pending_reference: str | None = None
        self._consumed = False

    def metadata(self):
        return get_manifest("ibkr-flex")

    def bind_credentials(self, credentials: CredentialBundle) -> None:
        if credentials.provider_id != "ibkr-flex":
            raise ValueError("credential provider mismatch")
        self._credentials, self.query_id, self._report, self._fingerprint = credentials, str(credentials.values.get("query_id") or self.query_id), None, None

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self._credentials
        token, query = (str(supplied.values.get("flex_token") or "").strip(), str(supplied.values.get("query_id") or self.query_id).strip()) if supplied else ("", "")
        if not token or not query:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("flex_token_and_query_id_required",))
        fingerprint = hashlib.sha256(f"{token}\0{query}".encode()).hexdigest()
        if self._report is None or self._fingerprint != fingerprint:
            try:
                if self._fingerprint != fingerprint:
                    self._pending_reference = None
                self._fingerprint = fingerprint
                if not self._pending_reference:
                    trigger = _safe_xml(self.transport.request("SendRequest", {"t": token, "q": query, "v": "3"}))
                    if (_text(trigger, "Status") or "").lower() not in {"success", "submitted", "ready"}:
                        raise RuntimeError("ibkr_flex_request_failed")
                    self._pending_reference = _text(trigger, "ReferenceCode")
                reference = self._pending_reference
                if not reference:
                    raise RuntimeError("ibkr_flex_reference_missing")
                # A pending response is NOT an empty statement. Retain its
                # reference for a later user retry instead of restarting it.
                report = _safe_xml(self.transport.request("GetStatement", {"q": reference, "t": token, "v": "3"}))
                if _text(report, "ErrorCode") == "1019":
                    return ScopeValidation(False, "pending", required=("read",), missing=("read",), issues=("flex_statement_generating_retry",))
                if report.tag.lower().split("}")[-1] != "flexqueryresponse" or _text(report, "ErrorCode"):
                    self._pending_reference = None
                    raise RuntimeError("ibkr_flex_invalid_statement_response")
                self._report = report
                self._pending_reference = None
                self._consumed = False
            except Exception as exc:
                return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=(f"flex_read_verification_failed:{type(exc).__name__}",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))

    def _require(self, credentials: CredentialBundle | None) -> None:
        if self._disconnected or not self.validate_read_access(credentials).allowed:
            raise PermissionConnectionError("read_access_not_verified")

    def _elements(self, *tags: str) -> tuple[ET.Element, ...]:
        wanted = {tag.lower() for tag in tags}
        return tuple(element for element in (self._report.iter() if self._report is not None else ()) if element.tag.lower().split("}")[-1] in wanted)

    def list_accounts(self, credentials: CredentialBundle | None = None) -> tuple[ConnectionAccount, ...]:
        self._require(credentials)
        account_ids = {element.attrib.get("accountId") for element in self._elements("FlexStatement") if element.attrib.get("accountId")}
        if not account_ids and self.account_id:
            account_ids.add(self.account_id)
        return tuple(ConnectionAccount(account, f"IBKR {account}", "ibkr-flex", "multi_asset", None, ("read",)) for account in sorted(account_ids))

    def _rows(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(dict(element.attrib) for element in self._elements("Trade", "Execution", "Transaction"))

    def read_events(self, cursor: ConnectionCursor | None = None, credentials: CredentialBundle | None = None) -> EventPage:
        # Completed scans always refresh. Offset-only checkpoints cannot detect
        # corrected executions or newly appended statements.
        if self._consumed and (cursor is None or not cursor.token):
            self._report = None
        self._require(credentials)
        if cursor is not None and cursor.provider_id != "ibkr-flex":
            raise ValueError("cursor provider mismatch")
        offset = int(cursor.token) if cursor and cursor.token else 0
        rows = self._rows()
        chunk = rows[offset : offset + self.page_size]
        events = tuple(self._event(row) for row in chunk)
        next_offset = offset + len(chunk)
        more = next_offset < len(rows)
        self._consumed = not more
        checkpoint = ConnectionCursor("ibkr-flex", str(next_offset) if more else "", revision=_hash({"rows": rows}))
        return EventPage(events=events, next_cursor=checkpoint if more else None, checkpoint_cursor=checkpoint)

    def _event(self, row: Mapping[str, Any]) -> NormalizedEvent:
        identity = str(row.get("tradeID") or row.get("execID") or row.get("transactionID") or _hash(row))
        occurred = _time(row.get("dateTime") or row.get("tradeDate"))
        side = str(row.get("buySell") or row.get("side") or "").lower() or None
        marker = str(row.get("openCloseIndicator") or "").upper()
        effect = {"O": "OPEN", "OPEN": "OPEN", "C": "CLOSE", "CLOSE": "CLOSE"}.get(marker, "AUTO")
        currency = row.get("currency")
        fee_currency = row.get("ibCommissionCurrency") or row.get("commissionCurrency")
        fee = row.get("ibCommission") if row.get("ibCommission") is not None else row.get("commission")
        return NormalizedEvent(identity, _hash(row), str(row.get("accountId") or self.account_id or "unknown-account"), str(row.get("assetCategory") or "unknown").lower(), str(row.get("symbol") or "unknown"), "fill", side, _absolute(row.get("quantity")), row.get("tradePrice") or row.get("price"), currency, _absolute(fee) if fee_currency == currency else None, occurred, None, source="ibkr-flex", metadata={"order_id": row.get("orderID"), "instrument_id": row.get("conid") or row.get("symbol"), "multiplier": row.get("multiplier") or (1 if str(row.get("assetCategory")).upper() in ("STK", "CASH", "CRYPTO") else None), "exchange": row.get("exchange"), "position_effect": effect, "fee_components": [{"amount": fee, "currency": fee_currency}], "time_precision": "second" if occurred and "T" in occurred else "date", "timezone": row.get("timezone") or row.get("timeZone") or "unknown"})

    def read_positions(self, credentials: CredentialBundle | None = None) -> tuple[NormalizedPosition, ...]:
        self._require(credentials)
        return tuple(NormalizedPosition(str(row.get("accountId") or self.account_id or "unknown-account"), str(row.get("assetCategory") or "unknown").lower(), str(row.get("symbol") or "unknown"), row.get("position") or row.get("quantity") or "0", row.get("costBasisPrice"), row.get("positionValue"), row.get("currency"), _time(row.get("reportDate")), source="ibkr-flex", metadata={"cost_basis_money": row.get("costBasisMoney")}) for row in (dict(element.attrib) for element in self._elements("OpenPosition")))

    def disconnect(self) -> None:
        self._credentials, self._report, self._fingerprint, self._disconnected = None, None, None, True
