from __future__ import annotations

from typing import Final

PLUGIN_API_VERSION: Final[str] = "1"

# The API version a plugin declares compatibility with, expressed as a
# semver-style major range such as ">=1,<2".
SUPPORTED_API_RANGE: Final[str] = ">=1,<2"


class TrustLevel:
    """Where a plugin is allowed to run and how much it is trusted."""

    CORE = "core"
    REVIEW_ONLY = "review-only"
    DATA_NETWORK = "data-network"
    UNTRUSTED_EXTERNAL = "untrusted-external"

    ALL = (CORE, REVIEW_ONLY, DATA_NETWORK, UNTRUSTED_EXTERNAL)


class PluginKind:
    """How a plugin is loaded at runtime."""

    ENTRY_POINT = "entry-point"
    LOCAL_PATH = "local-path"
    SUBPROCESS = "subprocess"
    COMPANION = "companion"

    ALL = (ENTRY_POINT, LOCAL_PATH, SUBPROCESS, COMPANION)


class CapabilityName:
    """Well-known service capability names.

    Plugins may declare additional names; these are the first-party seams the
    harness consumes directly.
    """

    TRADE_IMPORT = "trade_import"
    MARKET_CONTEXT = "market_context"
    REVIEWER = "reviewer"
    CHALLENGER = "challenger"
    EVALUATOR = "evaluator"
    REPLAY = "replay"
    REPORT_RENDERER = "report_renderer"
    MEMORY = "memory"
    LLM_PROVIDER = "llm_provider"
    AGENT_BRIDGE = "agent_bridge"

    ALL = (
        TRADE_IMPORT,
        MARKET_CONTEXT,
        REVIEWER,
        CHALLENGER,
        EVALUATOR,
        REPLAY,
        REPORT_RENDERER,
        MEMORY,
        LLM_PROVIDER,
        AGENT_BRIDGE,
    )


class DataTimeSemantics:
    """How a plugin's data relates to decision time."""

    POINT_IN_TIME = "point_in_time"
    HISTORICAL_EXPORT = "historical_export"
    LIVE_FETCH = "live_fetch"
    DERIVED_STATIC = "derived_static"

    ALL = (POINT_IN_TIME, HISTORICAL_EXPORT, LIVE_FETCH, DERIVED_STATIC)


class ResultKind:
    """Normalized plugin output kinds.

    The separation matters: an external model opinion must never be labelled a
    fact or a statistical result.
    """

    FACT_DATA = "fact_data"
    MODEL_OPINION = "model_opinion"
    STATISTICAL_RESULT = "statistical_result"
    USER_RECORD = "user_record"
    REVIEW_OBSERVATION = "review_observation"

    ALL = (FACT_DATA, MODEL_OPINION, STATISTICAL_RESULT, USER_RECORD, REVIEW_OBSERVATION)


# Result kinds that may only ever feed review, never execution or champion mutation.
REVIEW_ONLY_RESULT_KINDS = (ResultKind.MODEL_OPINION, ResultKind.REVIEW_OBSERVATION)
