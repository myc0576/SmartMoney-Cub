from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    PROVIDER_CATALOG,
    ProviderError,
    catalog_view,
    default_settings,
    install_provider,
    list_provider_ids,
    load_credentials,
    load_settings,
    normalize_provider_id,
    public_provider_view,
    remove_provider,
    resolve_provider,
    save_credentials,
    update_provider,
)
from smartmoney_cub_harness.workbench.server import WorkbenchService

# The provider surface follows the harness model-routing convention: install from
# a catalog, add a custom provider for a gateway, discover models from the
# endpoint, and pick a model rather than typing one.


def test_a_fresh_install_starts_with_the_gateway_and_the_offline_fallback(tmp_path) -> None:
    settings = load_settings(tmp_path)
    assert list_provider_ids(settings) == [ALPHATECH_PROVIDER_ID, OFFLINE_PROVIDER_ID]


def test_the_catalog_offers_more_than_one_provider(tmp_path) -> None:
    entries = catalog_view(load_settings(tmp_path))
    identifiers = [entry["provider_id"] for entry in entries]
    # The catalog is the point: a user is not limited to two hardcoded routes.
    assert len(identifiers) >= 4
    assert "deepseek" in identifiers
    by_id = {entry["provider_id"]: entry for entry in entries}
    # A provider shipped in the default configuration is already installed, and
    # the offline fallback is never offered as an installable route.
    assert by_id[ALPHATECH_PROVIDER_ID]["installed"] is True
    assert "offline" not in by_id
    assert by_id["deepseek"]["installed"] is False

    install_provider(tmp_path, "deepseek", from_catalog=True)
    after = {entry["provider_id"]: entry for entry in catalog_view(load_settings(tmp_path))}
    assert after["deepseek"]["installed"] is True


def test_installing_from_the_catalog_copies_its_models_and_endpoint(tmp_path) -> None:
    result = install_provider(tmp_path, "moonshot", from_catalog=True)
    provider = result["provider"]
    assert provider["base_url"] == PROVIDER_CATALOG["moonshot"]["base_url"]
    assert provider["protocol"] == "openai-chat"
    assert provider["models"]
    # A newly installed provider stays above the offline entry.
    assert list_provider_ids(load_settings(tmp_path))[-1] == OFFLINE_PROVIDER_ID


def test_a_custom_provider_needs_a_base_url_and_a_known_protocol(tmp_path) -> None:
    with pytest.raises(ProviderError):
        install_provider(tmp_path, "my-gateway", base_url="")
    with pytest.raises(ProviderError):
        install_provider(tmp_path, "my-gateway", base_url="https://gw.example/v1", protocol="grpc")


def test_a_custom_provider_accepts_models_with_reasoning_levels(tmp_path) -> None:
    result = install_provider(
        tmp_path,
        "my-gateway",
        display_name="公司中转站",
        base_url="https://gw.example/v1",
        protocol="openai-responses",
        models=[
            {"id": "reasoner", "reasoning_efforts": ["off", "high", "max"], "default_effort": "high"},
            "plain-chat",
        ],
    )
    provider = result["provider"]
    assert provider["label"] == "公司中转站"
    assert provider["protocol"] == "openai-responses"
    assert [model["id"] for model in provider["models"]] == ["reasoner", "plain-chat"]
    assert provider["reasoning_efforts"] == ["off", "high", "max"]
    # A model that declares no levels keeps an empty list, so the effort row is
    # simply absent for it instead of offering an invented level.
    assert provider["models"][1]["reasoning_efforts"] == []


def test_an_unknown_reasoning_level_is_refused(tmp_path) -> None:
    with pytest.raises(ProviderError) as error:
        install_provider(
            tmp_path,
            "my-gateway",
            base_url="https://gw.example/v1",
            models=[{"id": "m", "reasoning_efforts": ["turbo"]}],
        )
    assert "turbo" in str(error.value)


def test_a_default_effort_must_be_one_the_model_offers(tmp_path) -> None:
    with pytest.raises(ProviderError):
        install_provider(
            tmp_path,
            "my-gateway",
            base_url="https://gw.example/v1",
            models=[{"id": "m", "reasoning_efforts": ["off", "high"], "default_effort": "max"}],
        )


def test_provider_ids_are_normalized_and_validated(tmp_path) -> None:
    assert normalize_provider_id("  My-Gateway  ") == "my-gateway"
    with pytest.raises(ProviderError):
        normalize_provider_id("1st-bad")
    with pytest.raises(ProviderError):
        normalize_provider_id("has space")


def test_the_offline_fallback_cannot_be_removed(tmp_path) -> None:
    install_provider(tmp_path, "deepseek", from_catalog=True)
    remove_provider(tmp_path, "deepseek")
    assert "deepseek" not in list_provider_ids(load_settings(tmp_path))
    with pytest.raises(ProviderError):
        remove_provider(tmp_path, OFFLINE_PROVIDER_ID)


def test_removing_a_provider_also_drops_its_local_key(tmp_path) -> None:
    install_provider(tmp_path, "deepseek", from_catalog=True, api_key="sk-secret")
    assert load_credentials(tmp_path)["providers"]["deepseek"]["api_key"] == "sk-secret"
    remove_provider(tmp_path, "deepseek")
    assert "deepseek" not in (load_credentials(tmp_path).get("providers") or {})


def test_updating_a_provider_keeps_its_key_and_model_list(tmp_path) -> None:
    install_provider(tmp_path, "deepseek", from_catalog=True, api_key="sk-keep")
    update_provider(tmp_path, "deepseek", display_name="深寻", base_url="https://relay.example/v1")
    credentials = load_credentials(tmp_path)
    assert credentials["providers"]["deepseek"]["api_key"] == "sk-keep"
    view = public_provider_view(
        "deepseek", credentials=credentials, settings=load_settings(tmp_path)
    )
    assert view["label"] == "深寻"
    assert view["base_url"] == "https://relay.example/v1"
    assert view["models"]


def test_a_default_model_must_be_in_the_model_list(tmp_path) -> None:
    install_provider(tmp_path, "my-gateway", base_url="https://gw.example/v1", models=["a"])
    with pytest.raises(ProviderError):
        update_provider(tmp_path, "my-gateway", default_model="not-there")
    result = update_provider(tmp_path, "my-gateway", default_model="a")
    assert result["provider"]["default_model"] == "a"


def test_an_environment_key_is_reported_as_the_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALPHATECH_API_KEY", "sk-from-env")
    view = public_provider_view(
        ALPHATECH_PROVIDER_ID,
        credentials=load_credentials(tmp_path),
        settings=load_settings(tmp_path),
    )
    assert view["has_key"] is True
    assert view["key_source"] == "environment"
    assert "sk-from-env" not in json.dumps(view)


def test_a_provider_missing_its_endpoint_is_reported_instead_of_hidden(tmp_path) -> None:
    settings = default_settings()
    settings["providers"]["broken"] = {
        "provider_id": "broken",
        "label": "Broken",
        "base_url": "",
        "protocol": "openai-chat",
        "models": [],
        "removable": True,
    }
    settings["order"].append("broken")
    from smartmoney_cub_harness.agent.providers import save_settings

    save_settings(tmp_path, settings)
    with pytest.raises(ProviderError):
        resolve_provider("broken", settings=load_settings(tmp_path))
    assert "broken" in list_provider_ids(load_settings(tmp_path))


# ---- service and wire ---------------------------------------------------


class _DiscoveryProvider(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "b-model"}]})
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)


class _UnhelpfulProvider(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        data = json.dumps({"unexpected": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _serve(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def test_discovery_deduplicates_and_sorts_the_endpoint_listing(tmp_path) -> None:
    server, base_url = _serve(_DiscoveryProvider)
    try:
        service = WorkbenchService(tmp_path)
        try:
            install_provider(tmp_path, "gw", base_url=base_url, api_key="k")
            result = service.discover_models({"provider_id": "gw"})
            assert result["models"] == ["a-model", "b-model"]
            assert "\"api_key\"" not in json.dumps(result)
            assert result["safety"] == "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_discovery_explains_an_unrecognized_listing(tmp_path) -> None:
    server, base_url = _serve(_UnhelpfulProvider)
    try:
        service = WorkbenchService(tmp_path)
        try:
            install_provider(tmp_path, "gw", base_url=base_url, api_key="k")
            with pytest.raises(Exception) as error:
                service.discover_models({"provider_id": "gw"})
            # The message tells the user to add ids by hand instead of failing oddly.
            assert "by hand" in str(error.value)
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_discovery_needs_a_key_before_it_calls_out(tmp_path) -> None:
    service = WorkbenchService(tmp_path)
    try:
        install_provider(tmp_path, "gw", base_url="https://gw.example/v1")
        with pytest.raises(Exception) as error:
            service.discover_models({"provider_id": "gw"})
        assert "API key" in str(error.value)
    finally:
        service.close()


def test_the_default_selection_is_stored_and_survives_a_restart(tmp_path) -> None:
    service = WorkbenchService(tmp_path)
    try:
        install_provider(
            tmp_path,
            "gw",
            base_url="https://gw.example/v1",
            api_key="k",
            models=[{"id": "m1", "reasoning_efforts": ["off", "high"], "default_effort": "high"}],
        )
        service.update_settings(
            {"default_provider_id": "gw", "default_model": "m1", "default_reasoning": "high"}
        )
        assert service.default_selection() == {
            "provider_id": "gw",
            "model": "m1",
            "reasoning": "high",
        }
    finally:
        service.close()

    reopened = WorkbenchService(tmp_path)
    try:
        assert reopened.default_selection()["model"] == "m1"
        meta = reopened.meta()
        assert meta["default_provider"] == "gw"
        assert meta["default_model"] == "m1"
        assert meta["default_reasoning"] == "high"
        assert [provider["provider_id"] for provider in meta["providers"]] == [
            ALPHATECH_PROVIDER_ID,
            "gw",
            OFFLINE_PROVIDER_ID,
        ]
    finally:
        reopened.close()


def test_a_removed_default_provider_falls_back_instead_of_breaking(tmp_path) -> None:
    service = WorkbenchService(tmp_path)
    try:
        install_provider(tmp_path, "gw", base_url="https://gw.example/v1", models=["m"])
        service.update_settings({"default_provider_id": "gw", "default_model": "m"})
        service.remove_provider("gw")
        selection = service.default_selection()
        assert selection["provider_id"] in {ALPHATECH_PROVIDER_ID, OFFLINE_PROVIDER_ID}
        assert selection["provider_id"] != "gw"
        # A session that pointed at the removed provider answers locally.
        session = service.create_session({"title": "复盘", "provider_id": "gw", "model": "m"})
        events = list(service.stream_turn(session["session"]["session_id"], {"text": "复盘"}))
        assert events[-1]["kind"] == "done"
        assert service.store.list_audits() == []
    finally:
        service.close()


def test_the_service_exposes_the_catalog_and_protocols(tmp_path) -> None:
    service = WorkbenchService(tmp_path)
    try:
        settings = service.settings()
        assert [item["id"] for item in settings["protocols"]] == [
            "openai-chat",
            "openai-responses",
            "anthropic-messages",
        ]
        assert settings["catalog"]
        assert settings["defaults"]["provider_id"]
    finally:
        service.close()


def test_adding_a_provider_through_the_service_returns_no_secret(tmp_path) -> None:
    service = WorkbenchService(tmp_path)
    try:
        result = service.add_provider(
            {"provider_id": "gw", "base_url": "https://gw.example/v1", "api_key": "sk-hidden"}
        )
        assert result["provider"]["provider_id"] == "gw"
        assert "sk-hidden" not in json.dumps(result)
        assert result["settings"]["providers"]
    finally:
        service.close()


def test_an_invalid_provider_request_is_a_client_error(tmp_path) -> None:
    from smartmoney_cub_harness.workbench.server import ApiError

    service = WorkbenchService(tmp_path)
    try:
        with pytest.raises(ApiError) as error:
            service.add_provider({"provider_id": "No Good", "base_url": "https://x.example/v1"})
        assert error.value.status == 400
    finally:
        service.close()
