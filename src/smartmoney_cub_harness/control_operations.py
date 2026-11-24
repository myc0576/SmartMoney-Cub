"""Versioned inventory of business operations shared by CLI and integrations.

An operation maps to the existing service/HTTP contract; this is not a second
implementation of journal, market, or review logic. Registration never opens a
database, imports a provider, or makes a network request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    path: str
    handler: str = ""
    network: bool = False
    writes: bool = False
    confirmation: bool = False
    stream: bool = False

    def describe(self):
        return {**asdict(self), "capability": self.name,
                "human_only": self.name in HUMAN_ONLY,
                "command": "smcub operation " + self.name,
                "modes": ["local", "http"] if self.path else ["local"],
                "safety": SAFETY_DECLARATION}


HUMAN_ONLY = {"providers.add", "providers.update", "providers.remove", "settings.update", "settings.open", "connections.authorize"}


# Trader names follow their documented route table, held in sync by tests.
TRADER_NAMES = (
    "health.show", "meta.show", "market.providers", "market.bars",
    "journal.list", "journal.import", "journal.show", "accounts.list", "accounts.save",
    "connections.list", "connections.manifests", "connections.accounts",
    "connections.connect", "connections.sync", "connections.disconnect",
    "connections.oauth-start", "connections.oauth-complete", "connections.oauth-callback",
    "analytics.summary", "analytics.breakdown", "calendar.show", "insight.mistakes",
    "insight.edges", "insight.patterns", "insight.decide", "playbook.list", "playbook.save",
    "backtest.run", "backtest.list", "backtest.show", "replay.create", "replay.list",
    "replay.show", "replay.action",
)


def _build():
    from smartmoney_cub_harness.trader.api.routes import ROUTES
    if len(ROUTES) != len(TRADER_NAMES):
        raise RuntimeError("trader routes changed: update CLI operation coverage")
    result = {}
    online = {"market.bars", "connections.connect", "connections.sync", "connections.oauth-start",
              "connections.oauth-complete", "connections.oauth-callback", "backtest.run", "replay.create"}
    human = {"connections.connect", "connections.disconnect", "connections.oauth-start",
             "connections.oauth-complete", "connections.oauth-callback"}
    for name, route in zip(TRADER_NAMES, ROUTES):
        result[name] = Operation(name, route.method, route.template, network=name in online,
                                 writes=route.method != "GET" or name in online,
                                 confirmation=name in human)
    # name, method, path, service method. Method parameters are adapted by name.
    rows = """
overview.show GET /api/overview overview
documents.list GET /api/documents documents
import.upload POST /api/import/upload upload
import.commit-reviewed POST /api/import/commit commit_import
import.manual POST /api/import/manual add_manual_fill
rules.list GET /api/rules rules
rules.timeline GET /api/rules/timeline rules_timeline
rules.promote POST /api/rules/{rule_id}/promote promote_rule
governance.show GET /api/governance governance_view
governance.profile-create POST /api/governance/profile generate_profile
governance.profile-edit POST /api/governance/profile/{profile_id} edit_profile
governance.challenger POST /api/governance/challengers create_chat_challenger
governance.evaluate POST /api/governance/strategies/{strategy_id}/evaluate evaluate_strategy
governance.request-promotion POST /api/governance/strategies/{strategy_id}/promote request_promotion
governance.confirm-promotion POST /api/governance/promotions/{promotion_id}/confirm confirm_promotion
governance.rollback POST /api/governance/strategies/{strategy_id}/rollback rollback_strategy
plugin.market GET /api/plugins/market plugin_market
plugin.list GET /api/plugins plugins
plugin.catalog GET /api/plugins/market plugin_market
plugin.detail GET /api/plugins/detail plugin_detail
plugin.install-catalog POST /api/plugins/install install_plugin
plugin.probe POST /api/plugins/probe probe_plugin
plugin.uninstall POST /api/plugins/uninstall uninstall_plugin
plugin.configure POST /api/plugins/market/{plugin_id}/configure install_market_plugin
plugin.update POST /api/plugins/market/{plugin_id}/update update_market_plugin
plugin.reload POST /api/plugins/reload plugin_reload
plugin.activate POST /api/plugins/enable plugin_enable
plugin.deactivate POST /api/plugins/disable plugin_disable
plugin.enable POST /api/plugins/enable plugin_enable
plugin.disable POST /api/plugins/disable plugin_disable
assistant.list GET /api/assistant/sessions sessions
assistant.create POST /api/assistant/sessions create_session
assistant.show GET /api/assistant/sessions/{session_id} session_detail
assistant.update POST /api/assistant/sessions/{session_id} update_session
assistant.fork POST /api/assistant/sessions/{session_id}/fork fork_session
assistant.send POST /api/assistant/sessions/{session_id}/messages stream_turn
assistant.cancel POST /api/assistant/sessions/{session_id}/cancel cancel_turn
assistant.resume POST /api/assistant/sessions/{session_id}/resume resume_turn
assistant.scope GET /api/assistant/sessions/{session_id}/review/scope review_scope
assistant.confirm-scope POST /api/assistant/sessions/{session_id}/review/confirm confirm_review_scope
assistant.challenger POST /api/assistant/sessions/{session_id}/review/challenger record_challenger
assistant.package POST /api/assistant/sessions/{session_id}/review/package record_review_package
assistant.preview POST /api/assistant/sessions/{session_id}/preview session_preview
assistant.agents GET /api/assistant/agents review_agents
assistant.agent-detail GET /api/assistant/agents/{agent_id} review_agent_detail
assistant.agent-probe POST /api/assistant/agents/{agent_id}/probe review_agent_probe
assistant.agent-enable POST /api/assistant/agents/{agent_id}/enable review_agent_toggle
assistant.agent-disable POST /api/assistant/agents/{agent_id}/disable review_agent_toggle
assistant.presets GET /api/assistant/agent-presets review_agent_presets
assistant.preset-create POST /api/assistant/agent-presets save_review_agent_preset
assistant.preset-save POST /api/assistant/agent-presets/{preset_id} save_review_agent_preset
assistant.preset-delete POST /api/assistant/agent-presets/{preset_id}/remove delete_review_agent_preset
assistant.default GET /api/assistant/agent-default review_agent_default
assistant.set-default POST /api/assistant/agent-default set_review_agent_default
assistant.from-trade POST /api/assistant/reviews/from-trade review_from_trade
settings.show GET /api/settings settings
settings.update POST /api/settings update_settings
settings.open POST /api/settings/open-file open_config_file
providers.add POST /api/settings/providers add_provider
providers.update POST /api/settings/providers/{provider_id} add_provider
providers.remove POST /api/settings/providers/{provider_id}/remove remove_provider
providers.discover POST /api/settings/discover discover_models
providers.test POST /api/settings/test test_provider
providers.check-models POST /api/settings/providers/{provider_id}/check-models check_models
preferences.show GET /api/preferences preferences
preferences.update POST /api/preferences update_preferences
audit.list GET /api/audit audits
jev.status GET /api/jev/status jev_status
jev.tracks GET /api/jev/tracks jev_tracks
agents.list GET /api/agents agents
agents.apply POST /api/agents/apply agents_apply
agents.disable POST /api/agents/disable agents_disable
agents.restore POST /api/agents/restore agents_restore
benchmark.latest GET /api/benchmark/latest benchmark_latest
benchmark.image GET /api/benchmark/images/{run_id}/{filename} benchmark_image
"""
    confirmations = {"rules.promote", "governance.confirm-promotion", "governance.rollback",
                     "plugin.install-catalog", "plugin.uninstall", "plugin.update", "plugin.configure",
                     "providers.add", "providers.update", "providers.remove", "settings.update", "settings.open",
                     "assistant.preset-delete", "agents.apply", "agents.restore", "agents.disable"}
    network = {"plugin.install-catalog", "plugin.update", "providers.discover", "providers.test",
               "providers.check-models", "assistant.send", "assistant.resume", "assistant.agent-probe"}
    for line in rows.splitlines():
        if not line.strip():
            continue
        name, method, path, handler = line.split()
        result[name] = Operation(name, method, path, handler, name in network,
                                 method != "GET", name in confirmations,
                                 name in {"assistant.send", "assistant.resume"})
    for name in ("providers.setup", "connections.setup", "plugin.setup", "backtest.validate",
                 "permissions.request", "replay.step", "replay.seek", "replay.rewind",
                 "replay.play", "replay.pause", "connections.watch"):
        result[name] = Operation(name, "POST" if name.startswith("replay.") else "GET", "",
                                 writes=name.startswith(("replay.", "permissions.", "connections.watch")))
    result["connections.authorize"] = Operation("connections.authorize", "POST", "", network=True, writes=True, confirmation=True)
    return result


OPERATIONS = _build()


def capabilities():
    return {"status": "ok", "schema": "cli.capabilities.v1", "protocol_version": 1,
            "operations": [op.describe() for op in OPERATIONS.values()],
            "safety": SAFETY_DECLARATION,
            "filesystem": "Service initialization may create local databases; business writes are declared per operation."}
