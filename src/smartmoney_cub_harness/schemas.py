from __future__ import annotations

SAFETY_DECLARATION = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

PACKAGE_NAME = "smartmoney-cub-harness"
PACKAGE_IMPORT_NAME = "smartmoney_cub_harness"

MANIFEST_SCHEMA = "smartmoney_cub_run_manifest.v1"
RUN_ENVELOPE_SCHEMA = "smartmoney_cub_run_envelope.v1"
EVIDENCE_PACK_SCHEMA = "smartmoney_cub_evidence_pack.v1"
EVIDENCE_REPLAY_SCHEMA = "smartmoney_cub_evidence_replay.v1"
DECISION_SCHEMA = "smartmoney_cub_decision.v1"
OUTCOME_SCHEMA = "smartmoney_cub_outcome.v1"
REGISTRY_SCHEMA = "smartmoney_cub_rule_registry.v1"
CASE_SCHEMA = "smartmoney_cub_case_record.v1"
LEDGER_SCHEMA = "smartmoney_cub_evolution_ledger.v1"
MEMORY_SCHEMA = "smartmoney_cub_markdown_memory.v1"
PRIVATE_CASE_CSV_SCHEMA = "smartmoney_cub_private_case_csv.v1"
SELF_EVOLVE_CONTRACT_SCHEMA = "smartmoney_cub_self_evolve_contract.v1"
SELF_EVOLVE_STATE_SCHEMA = "smartmoney_cub_self_evolve_state.v1"
PROMOTION_PACKET_SCHEMA = "smartmoney_cub_promotion_packet.v1"
TRADINGAGENTS_REVIEW_PACKET_SCHEMA = "smartmoney_cub_tradingagents_review_packet.v1"
MENTOR_FIT_SCHEMA = "smartmoney_cub_mentor_fit.v1"

# Convergence (local-first review workbench) schemas.
REVIEW_STORE_SCHEMA = "smartmoney_cub_review_store.v1"
SOURCE_DOCUMENT_SCHEMA = "smartmoney_cub_source_document.v1"
AUDIT_SCHEMA = "smartmoney_cub_outbound_audit.v1"
REVIEW_AGENT_SCHEMA = "smartmoney_cub_review_agent.v1"
SETTINGS_SCHEMA = "smartmoney_cub_settings.v1"

VALID_ACTION_LABELS = {"SILENT", "ALERT", "ERROR", "WATCH", "AVOID", "EMPTY_POSITION"}
VALID_DATA_QUALITY_FLAGS = {"ok", "stale", "partial", "missing", "error"}
VALID_HORIZONS = {"d1": 1, "d3": 3}

REQUIRED_MANIFEST_FIELDS = ("schema", "run_id", "decision_time", "mode", "data_sources")
REQUIRED_SOURCE_FIELDS = ("name", "fetch_time", "available_at", "data_quality_flag")

REQUIRED_ALERT_DECISION_FIELDS = (
    "invalidation_price",
    "time_stop",
    "give_up_conditions",
    "data_source",
    "available_at",
    "data_quality_flag",
)
