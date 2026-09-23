"""Tenant-scoped connection orchestration and durable journal ingestion.

Adapters own external reads; this controller writes only the user's journal.
Durable adapter events are replayed idempotently into the journal, so a crash
between an external checkpoint and a journal commit cannot silently lose fills.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from threading import RLock
import json
import secrets
import time
from urllib.parse import urlparse
from typing import Any, Callable, Mapping

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.auth import AuthContext
from .manager import ConnectionManager
from .manifests import list_manifests, get_manifest
from .models import CredentialBundle, NormalizedEvent


def _key(*parts: Any) -> str:
    return sha256("\0".join(str(part) for part in parts).encode()).hexdigest()[:32]


def journal_row(event: NormalizedEvent) -> dict[str, Any] | None:
    """Only execution events become fills; cash flows and unknown types stay raw."""
    side = str(event.side or "").upper()
    if event.event_type.lower() not in ("fill", "trade", "buy", "sell", "execution") or side not in ("BUY", "SELL", "BUY_OPEN", "BUY_CLOSE", "SELL_OPEN", "SELL_CLOSE"):
        return None
    if not event.symbol or event.symbol == "unknown" or not event.account_id or event.account_id == "unknown-account":
        raise ValueError("instrument_or_account_mapping_required")
    when = str(event.occurred_at or "")
    if len(when) < 10 or event.price is None or event.quantity is None:
        raise ValueError("execution_timestamp_price_and_quantity_required")
    metadata = dict(event.metadata)
    return {"trade_id": "CON-" + _key(event.source, event.account_id, metadata.get("instrument_id") or event.symbol, event.external_id),
            "account_id": "ACC-" + _key(event.source, event.account_id),
            "symbol": event.symbol, "name": str(metadata.get("name") or event.symbol),
            "side": side, "position_effect": metadata.get("position_effect") or (side.split("_")[1] if "_" in side else "AUTO"),
            "trade_date": when[:10], "trade_time": when[11:] if len(when) > 10 else "",
            "price": str(event.price), "quantity": str(event.quantity),
            "fee": str(event.fee) if event.fee is not None else None,
            "currency": event.currency or "UNKNOWN", "asset_class": event.asset,
            "instrument_id": metadata.get("instrument_id") or event.symbol,
            "market": metadata.get("market") or "UNKNOWN", "multiplier": metadata.get("multiplier", 1),
            "timezone": metadata.get("timezone") or "unknown",
            "source_precision": metadata.get("time_precision") or ("timestamp" if len(when) > 10 else "date"),
            "provenance": {"source": event.source, "external_id": event.external_id,
                           "revision": str(event.revision), "available_at": event.available_at,
                           "data_quality": event.data_quality, "raw_event": event.to_dict()}}


class ConnectionController:
    def __init__(self, service: Any, root: Path | None, factory: Callable | None = None) -> None:
        self.service, self.root, self.factory = service, root, factory
        self._managers: dict[str, ConnectionManager] = {}
        self._lock = RLock()
        self._oauth_pending: dict[str, dict[str, Any]] = {}
        self.oauth_client = None
        self._pending_adapters: dict[tuple[str, str], tuple[str, float, Any]] = {}
        self._watchers: dict[str, Any] = {}

    def _configure_watch(self, ctx: AuthContext, config: Mapping[str, Any]) -> None:
        from .watcher import StatementWatcher
        previous = self._watchers.pop(ctx.user_id, None)
        if previous:
            previous.close()
        if ctx.mode != "local" or config.get("watch_enabled") is not True:
            return
        def tick():
            try:
                self.sync(ctx, "local-statement-directory")
            except Exception as exc:
                self.service.store.put_document(ctx.user_id, "connection_status", "local-statement-directory",
                    {"provider_id": "local-statement-directory", "connected": False, "partial": True,
                     "errors": ["watch_failed:" + type(exc).__name__], "safety": SAFETY_DECLARATION})
        watcher = StatementWatcher(tick, interval=30)
        self._watchers[ctx.user_id] = watcher
        watcher.start()

    def resume_local_watch(self) -> None:
        from smartmoney_cub_harness.trader.auth import resolve_identity
        if self.service.auth_mode != "local":
            return
        ctx = resolve_identity({}, mode="local")
        for doc in self.service.store.list_documents(ctx.user_id, "connection_config", limit=100):
            payload = doc["payload"]
            if doc["document_id"] == "local-statement-directory" and payload.get("active"):
                self._configure_watch(ctx, payload.get("config") or {})

    def close(self) -> None:
        watchers, self._watchers = list(self._watchers.values()), {}
        for watcher in watchers:
            watcher.close()
        self._pending_adapters.clear()
        self._oauth_pending.clear()

    def oauth_start(self, ctx: AuthContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        from .snaptrade import SnapTradeOAuthClient, oauth_http
        redirect = str(payload.get("redirect_uri") or "")
        parsed = urlparse(redirect)
        expected_path = "/api/trader/connections/snaptrade-personal-mcp/oauth/callback"
        # Local callback only until a hosted operator explicitly supplies an
        # authenticated callback integration. No arbitrary redirect/token host.
        if ctx.mode != "local" or parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.path != expected_path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("local_loopback_oauth_callback_required")
        if self.root is None:
            raise ValueError("connection_state_root_required")
        client = self.oauth_client or SnapTradeOAuthClient(oauth_http)
        registration = client.register_dynamic_client(redirect_uri=redirect)
        state = secrets.token_urlsafe(32)
        url, verifier = client.authorization_url(client_id=registration["client_id"], redirect_uri=redirect, state=state)
        with self._lock:
            self._oauth_pending = {key: value for key, value in self._oauth_pending.items() if value["expires"] > time.time()}
            self._oauth_pending[state] = {"user_id": ctx.user_id, "expires": time.time() + 600,
                                           "client_id": registration["client_id"], "redirect_uri": redirect, "verifier": verifier}
        return {"status": "ok", "authorization_url": url, "state": state, "expires_in": 600, "safety": SAFETY_DECLARATION}

    def oauth_complete(self, ctx: AuthContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        from .snaptrade import SnapTradeOAuthClient, oauth_http
        state, code = str(payload.get("state") or ""), str(payload.get("code") or "")
        with self._lock:
            pending = self._oauth_pending.get(state)
            if not pending or pending["user_id"] != ctx.user_id or pending["expires"] <= time.time() or not code:
                raise ValueError("oauth_state_invalid_or_expired")
            self._oauth_pending.pop(state)
        client = self.oauth_client or SnapTradeOAuthClient(oauth_http)
        tokens = dict(client.exchange_code(code=code, verifier=pending["verifier"], client_id=pending["client_id"], redirect_uri=pending["redirect_uri"]))
        tokens.update({"client_id": pending["client_id"], "expires_at_epoch": time.time() + float(tokens.get("expires_in") or 600)})
        return self.connect(ctx, "snaptrade-personal-mcp", {"credentials": tokens})

    def _build(self, provider_id, values, config):
        if self.factory:
            return self.factory(provider_id, values, config)
        from .factory import build_connection
        return build_connection(provider_id, values, config)

    def _manager(self, ctx: AuthContext) -> ConnectionManager:
        if self.root is None:
            raise ValueError("connection_state_root_required")
        if ctx.user_id not in self._managers:
            manager = ConnectionManager(state_path=self.root / _key(ctx.user_id) / "state.json")
            configs = self.service.store.list_documents(ctx.user_id, "connection_config", limit=100)
            for doc in configs:
                config = doc["payload"]
                if not config.get("active"):
                    continue
                provider_id = doc["document_id"]
                credentials = manager.credentials(provider_id)
                if credentials is None:
                    continue
                try:
                    connection = self._build(provider_id, credentials.values, config.get("config") or {})
                    manager.register(connection)
                    manager.set_credentials(provider_id, credentials)
                except Exception as exc:
                    # An unavailable optional SDK must not disable unrelated
                    # connections or prevent local credential removal.
                    self.service.store.put_document(ctx.user_id, "connection_status", provider_id,
                        {"provider_id": provider_id, "connected": False, "revoked": False,
                         "credential_fields": sorted(credentials.values), "scope": None,
                         "errors": ["restore_failed:" + type(exc).__name__], "safety": SAFETY_DECLARATION})
            self._managers[ctx.user_id] = manager
        return self._managers[ctx.user_id]

    def view(self, ctx: AuthContext) -> dict[str, Any]:
        # Listing a catalogue must not make authenticated network requests.
        statuses = [doc["payload"] for doc in self.service.store.list_documents(ctx.user_id, "connection_status", limit=100)]
        for status in statuses:
            if status.get("provider_id") == "local-statement-directory":
                status["watch_active"] = ctx.user_id in self._watchers
        accounts = self.service.store.list_accounts(ctx.user_id)
        return {"status": "ok", "manifests": [manifest.to_dict() for manifest in list_manifests()],
                "statuses": statuses,
                "accounts": [{"account_id": item["account_id"], "display_name": item["name"],
                              "provider": item.get("broker", ""), "currency": item.get("currency"),
                              "asset_class": "source_declared", "status": "journal_account"} for item in accounts],
                "state_available": self.root is not None, "safety": SAFETY_DECLARATION}

    def connect(self, ctx: AuthContext, provider_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        get_manifest(provider_id)
        if not isinstance(payload, Mapping):
            raise ValueError("request_body_must_be_an_object")
        values, config = payload.get("credentials") or {}, payload.get("config") or {}
        if not isinstance(values, Mapping) or not isinstance(config, Mapping):
            raise ValueError("credentials_and_config_must_be_objects")
        if ctx.mode != "local" and provider_id in ("local-statement-directory", "metatrader-investor"):
            raise PermissionError("local_machine_connection_requires_local_mode")
        if "watch_enabled" in config and (provider_id != "local-statement-directory" or not isinstance(config["watch_enabled"], bool)):
            raise ValueError("watch_is_local_statement_only_boolean")
        with self._lock:
            self.service._ensure_tenant(ctx)
            manager = self._manager(ctx)
            pending_key = (ctx.user_id, provider_id)
            fingerprint = _key(json.dumps([dict(values), dict(config)], sort_keys=True))
            pending = self._pending_adapters.get(pending_key)
            adapter = pending[2] if pending and pending[0] == fingerprint and pending[1] > time.time() else self._build(provider_id, dict(values), dict(config))
            # Permission facts must come from the adapter, never the JSON body.
            bundle = CredentialBundle(provider_id, dict(values))
            validation = adapter.validate_read_access(bundle)
            if not validation.allowed:
                if validation.status == "pending":
                    self._pending_adapters[pending_key] = (fingerprint, time.time() + 600, adapter)
                else:
                    self._pending_adapters.pop(pending_key, None)
                return {"status": "error", "code": "read_scope_unverified", "scope": validation.to_dict(),
                        "safety": SAFETY_DECLARATION}
            self._pending_adapters.pop(pending_key, None)
            manager.register(adapter)
            manager.set_credentials(provider_id, bundle)
            self.service.store.put_document(ctx.user_id, "connection_config", provider_id,
                                            {"active": True, "config": dict(config), "provider_id": provider_id})
            status = {**manager.status(provider_id), "scope": validation.to_dict()}
            self.service.store.put_document(ctx.user_id, "connection_status", provider_id, status)
        if provider_id == "local-statement-directory":
            self._configure_watch(ctx, config)
        return {"status": "ok", "connection": status, "safety": SAFETY_DECLARATION}

    def sync(self, ctx: AuthContext, provider_id: str) -> dict[str, Any]:
        with self._lock:
            manager = self._manager(ctx)
            result = manager.sync(provider_id, max_attempts=2, max_pages=100)
            errors = list(result.errors)
            imported, updated, skipped = 0, 0, 0
            if not result.blocked:
                for account in result.accounts:
                    self.service.upsert_account(ctx, {"account_id": "ACC-" + _key(provider_id, account.account_id),
                                                     "name": account.display_name, "broker": provider_id,
                                                     "currency": account.currency or "UNKNOWN"})
                # All durable events, not only the latest delta, close the
                # checkpoint/journal crash gap. Stable ids make this idempotent.
                for event in manager.records(provider_id):
                    try:
                        row = journal_row(event)
                        if row is None:
                            skipped += 1
                            if event.data_quality == "requires_mapping" or event.event_type.startswith("unmapped"):
                                errors.append("event_requires_mapping:" + _key(event.external_id))
                            continue
                        write = self.service.import_trades(ctx, rows=[row], source_format=provider_id)
                        imported += int(write.get("inserted_count") or 0)
                        updated += int(write.get("updated_count") or 0)
                    except ValueError:
                        errors.append("event_requires_mapping:" + _key(event.external_id))
                    except Exception:
                        errors.append("journal_import_failed:" + _key(event.external_id))
            status = {**manager.status(provider_id), "scope": result.scope.to_dict() if result.scope else None,
                      "partial": bool(result.partial or errors), "last_sync": self._now(),
                      "errors": errors, "positions": [position.to_dict() for position in result.positions]}
            self.service.store.put_document(ctx.user_id, "connection_status", provider_id, status)
        return {"status": "error" if result.blocked else "ok", "connection": status,
                "imported_count": imported, "updated_count": updated, "skipped_nonexecution_count": skipped,
                "partial": bool(result.partial or errors), "errors": errors, "safety": SAFETY_DECLARATION}

    def disconnect(self, ctx: AuthContext, provider_id: str) -> dict[str, Any]:
        if provider_id == "local-statement-directory":
            self._configure_watch(ctx, {})
        with self._lock:
            manager = self._manager(ctx)
            disconnected = manager.disconnect(provider_id)
            self._pending_adapters.pop((ctx.user_id, provider_id), None)
            self.service.store.put_document(ctx.user_id, "connection_config", provider_id, {"active": False})
            status = {"provider_id": provider_id, "connected": False, "revoked": True,
                      "credential_fields": [], "scope": None, "errors": list(disconnected.errors),
                      "remote_revocation_pending": bool(disconnected.errors), "safety": SAFETY_DECLARATION}
            self.service.store.put_document(ctx.user_id, "connection_status", provider_id, status)
        return {"status": "ok", "connection": status, "journal_preserved": True, "safety": SAFETY_DECLARATION}

    @staticmethod
    def _now():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
