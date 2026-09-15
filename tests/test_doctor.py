from __future__ import annotations

from smartmoney_cub_harness.cli import doctor
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# Doctor semantics after the trader-product rewrite: the harness is read-only with
# respect to markets and execution, and writable with respect to the user's own
# local and tenant-scoped journal. "network_required: false" therefore means the
# core imports and runs with no network; built-in market sources are opt-in at
# call time. The execution ban (execution_integrations "disabled",
# broker_api_required false) and the safety declaration are unchanged.


def test_doctor_reports_offline_no_credentials_required():
    result = doctor()

    assert result["network_required"] is False
    assert result["telemetry"] is False
    assert result["upload"] is False
    assert result["credentials_required"] is False
    assert result["github_auth_required"] is False
    assert result["external_api_required"] is False
    assert result["broker_api_required"] is False
    assert result["execution_integrations"] == "disabled"
    assert result["market_data_mode"] == "offline"
    assert result["tenant_mode"] == "local_single_user"
    assert result["safety"] == SAFETY_DECLARATION


def test_doctor_includes_path_free_launcher_diagnostics():
    result = doctor()

    assert set(result["launcher"]) == {
        "launcher_found",
        "launcher_count",
        "multiple_launchers",
        "resolved_to_current_environment",
    }
    assert all(not isinstance(value, str) for value in result["launcher"].values())
