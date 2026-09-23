from __future__ import annotations

from smartmoney_cub_harness.plugins.catalog import (
    CATEGORY_ORDER,
    catalog_entries,
    catalog_index,
    catalog_payload,
)
from smartmoney_cub_harness.plugins.catalog_contract import (
    INSTALL_BUILTIN,
    INSTALL_GIT,
    INSTALL_KINDS,
    INSTALL_PYPI,
    LEVEL_ADAPTER,
    LEVEL_COMPANION,
    LEVELS,
    CATALOG_SCHEMA,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

FORBIDDEN_CAPABILITIES = ("order", "cancel", "trade_execution", "account_mutation", "broker")


def test_catalog_declares_schema_safety_and_categories() -> None:
    payload = catalog_payload()
    assert payload["schema"] == CATALOG_SCHEMA
    assert payload["safety"] == SAFETY_DECLARATION
    assert tuple(payload["categories"]) == CATEGORY_ORDER
    assert set(payload["by_category"]) == set(CATEGORY_ORDER)
    assert payload["counts"]["total"] == len(catalog_entries())


def test_every_entry_uses_a_known_install_kind() -> None:
    counts = catalog_payload()["counts"]["by_install_kind"]
    assert set(counts) == set(INSTALL_KINDS)
    for entry in catalog_entries():
        assert entry["install"]["kind"] in INSTALL_KINDS, entry["plugin_id"]


def test_catalog_never_declares_execution_capabilities() -> None:
    for entry in catalog_entries():
        for capability in entry["capabilities"]:
            lowered = capability.lower()
            assert not any(fragment in lowered for fragment in FORBIDDEN_CAPABILITIES), entry["plugin_id"]


def test_high_execution_risk_projects_stay_companion_only() -> None:
    high = [entry for entry in catalog_entries() if entry["execution_risk"] == "high"]
    assert "vnpy" not in catalog_index(), "execution frameworks are not marketplace products"
    for entry in high:
        assert entry["level"] == LEVEL_COMPANION, entry["plugin_id"]
        assert entry["install"]["kind"] == INSTALL_GIT, entry["plugin_id"]


def test_catalog_entries_carry_a_boundary_and_license() -> None:
    for entry in catalog_entries():
        assert entry["boundary"].strip(), entry["plugin_id"]
        assert entry["license"].strip(), entry["plugin_id"]
        assert entry["level"] in LEVELS, entry["plugin_id"]


def test_catalog_includes_adapters_and_companions() -> None:
    levels = {entry["level"] for entry in catalog_entries()}
    assert LEVEL_ADAPTER in levels
    assert LEVEL_COMPANION in levels


def test_networked_catalog_entries_are_flagged() -> None:
    networked = [entry for entry in catalog_entries() if entry["repo"].startswith("https://github.com/akfamily")]
    assert networked
    assert networked[0]["network_required"] is True


def test_pypi_entries_carry_a_package_and_module() -> None:
    pypi = [entry for entry in catalog_entries() if entry["install"]["kind"] == INSTALL_PYPI]
    assert len(pypi) >= 10, "most curated projects are ordinary distributions"
    for entry in pypi:
        spec = entry["install"]
        assert spec["package"], entry["plugin_id"]
        assert spec["module"], entry["plugin_id"]
        assert "==" not in spec["package"], entry["plugin_id"]


def test_git_entries_point_at_github() -> None:
    for entry in catalog_entries():
        if entry["install"]["kind"] != INSTALL_GIT:
            continue
        assert entry["install"]["repo"].startswith("https://github.com/"), entry["plugin_id"]
        assert entry["install"]["module"], entry["plugin_id"]


def test_builtin_entries_say_what_ships_with_the_harness() -> None:
    builtin = [entry for entry in catalog_entries() if entry["install"]["kind"] == INSTALL_BUILTIN]
    assert builtin
    for entry in builtin:
        assert entry["install"]["note"].strip(), entry["plugin_id"]


def test_manual_command_matches_the_install_kind() -> None:
    for entry in catalog_entries():
        command = entry["manual_command"]
        kind = entry["install"]["kind"]
        if kind == INSTALL_PYPI:
            assert command.startswith("pip install "), entry["plugin_id"]
        elif kind == INSTALL_GIT:
            assert command.startswith("git clone "), entry["plugin_id"]
        else:
            assert command, entry["plugin_id"]


def test_catalog_index_is_keyed_by_plugin_id() -> None:
    index = catalog_index()
    assert set(index) == {entry["plugin_id"] for entry in catalog_entries()}
    assert index["akshare"]["install"]["package"] == "akshare"


def test_credentials_have_official_obtain_links_and_explicit_ownership() -> None:
    index = catalog_index()
    for plugin_id, key in (("tushare-pro", "TOKEN"), ("fred", "FRED_API_KEY")):
        entry = index[plugin_id]
        assert entry["credential_mode"] == "managed_local"
        requirement = entry["credential_requirements"][0]
        assert requirement["name"] == key
        assert requirement["obtain_url"].startswith("https://")
        assert requirement["required"] is True
    external = index["tradingagents"]
    assert external["credential_mode"] == "external_only"
    assert external["credential_requirements"] == []
    assert external["credential_setup_url"].startswith("https://github.com/TauricResearch/")
