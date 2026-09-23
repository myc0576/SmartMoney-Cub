"""The rule evolution timeline.

Why this module exists: the rule library stores one row per rule -- its current
status and its metrics -- and the evolution ledger stores one line per event.
Neither answers the question a trader actually asks about a rule: how did it get
here, and what changed when it did. Reading both together and ordering them in
time answers it, and doing that in one place keeps the answer identical wherever
it is shown.

Two properties are deliberate:

* Events are sorted by their own timestamp rather than by the order they were
  written, because the ledger is append-only and a replay or a backfill can land
  an older event after a newer one. A timeline that trusted file order would show
  the story backwards.
* A stage that never happened is simply absent. Nothing is synthesized to fill the
  shape of a ladder: a rule that was never verified shows no verification step,
  because a reader who sees one would believe it happened.
"""

from __future__ import annotations

from typing import Any

# The stages a rule passes through, in the order the product describes them. This
# is a reading aid, not a source of events: it labels a step and breaks a tie
# between two events written in the same second. It never invents one.
STAGE_ORDER: tuple[str, ...] = (
    "candidate_discovered",
    "challenger_rule_proposed",
    "challenger_verified",
    "champion_promoted",
)

STAGE_LABELS: dict[str, str] = {
    "candidate_discovered": "发现",
    "challenger_rule_proposed": "提出 Challenger",
    "challenger_verified": "验证",
    "champion_promoted": "人工确认 Champion",
    "promotion_confirmation_recorded": "人工确认",
}

# The event a promotion writes. A tuple because the spelling has existed in two
# forms, and both appear in ledgers already on disk.
PROMOTION_EVENTS: tuple[str, ...] = ("champion_promoted", "promotion_confirmation_recorded")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _sort_key(event: dict[str, Any]) -> tuple[str, int]:
    """Sort by the event's own time, then by the canonical stage order.

    A missing timestamp sorts first rather than last: an event with no time is an
    event whose position is unknown, and putting it at the end would read as the
    most recent one -- a claim the record does not support.
    """
    created = _clean(event.get("created_at")) or _clean(event.get("at"))
    stage = _clean(event.get("event"))
    rank = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER)
    return (created, rank)


def build_timeline(
    *,
    rules: list[dict[str, Any]],
    ledger_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One entry per rule, each carrying its own ordered event stream.

    The rules are rows from the rule library. The ledger entries are lines from
    the evolution ledger. A rule that appears only in the ledger still gets an
    entry: it was discovered even if it has not reached the rule table yet.
    """
    by_rule: dict[str, dict[str, Any]] = {}

    for rule in rules:
        rule_id = _clean(rule.get("rule_id"))
        if not rule_id:
            continue
        metrics = rule.get("metrics") or {}
        by_rule[rule_id] = {
            "rule_id": rule_id,
            "family": _clean(rule.get("family")),
            "title": _clean(rule.get("title")),
            "status": _clean(rule.get("status")),
            "metrics": metrics,
            "promotion_note": _clean(rule.get("promotion_note")),
            "promoted_at": _clean(rule.get("promoted_at")),
            "updated_at": _clean(rule.get("updated_at")),
            "events": [],
            "evidence": _evidence_from_metrics(metrics),
        }

    for entry in ledger_entries:
        rule_id = _clean(entry.get("rule_id"))
        if not rule_id:
            # A ledger line that names no rule is not part of any rule's story. It
            # is dropped rather than filed under a placeholder, which would put an
            # unrelated event on some rule's timeline.
            continue
        item = by_rule.get(rule_id)
        if item is None:
            item = {
                "rule_id": rule_id,
                "family": _clean(entry.get("family")),
                "title": _clean(entry.get("title")),
                "status": "",
                "metrics": {},
                "promotion_note": "",
                "promoted_at": "",
                "updated_at": "",
                "events": [],
                "evidence": _evidence_from_metrics({}),
            }
            by_rule[rule_id] = item
        stage = _clean(entry.get("event"))
        item["events"].append({
            "event": stage,
            "label": STAGE_LABELS.get(stage, stage.replace("_", " ")),
            "at": _clean(entry.get("created_at")) or _clean(entry.get("at")),
            "detail": _detail(entry),
        })

    out: list[dict[str, Any]] = []
    for item in by_rule.values():
        item["events"].sort(key=_sort_key)
        # A champion whose ledger predates the promotion gets the confirmation
        # recorded on the row appended to the stream, so the timeline does not end
        # on "proposed" for a rule that is already champion. The appended event
        # carries the promotion note, which is the human artifact itself.
        if item["status"] == "champion" and item["promotion_note"]:
            if not any(event["event"] in PROMOTION_EVENTS for event in item["events"]):
                item["events"].append({
                    "event": "promotion_confirmation_recorded",
                    "label": STAGE_LABELS["promotion_confirmation_recorded"],
                    "at": item["promoted_at"] or item["updated_at"],
                    "detail": item["promotion_note"],
                })
                item["events"].sort(key=_sort_key)
        # The stages actually reached, in canonical order, for a caller that wants
        # to render a ladder rather than a list.
        item["stages"] = [
            stage for stage in STAGE_ORDER
            if any(event["event"] == stage for event in item["events"])
        ]
        out.append(item)

    out.sort(key=lambda item: (item["status"] != "champion", item["rule_id"]))
    return out


def _detail(entry: dict[str, Any]) -> str:
    """One readable line for an event.

    The ledger row is loose about where a human-readable note goes, so the known
    spellings are tried in order. An event with none gets an empty string rather
    than a generated sentence: a step may show with no note, and inventing one
    would put words in the record's mouth.
    """
    for key in ("detail", "note", "summary", "reason"):
        value = _clean(entry.get(key))
        if value:
            return value
    return ""


def _evidence_from_metrics(metrics: Any) -> dict[str, Any]:
    """What backs this rule, taken from the row's own metrics.

    A rule whose metrics carry no trade identifiers reports an empty list and the
    confidence "none". That is the honest answer: the rule table does not store
    which trades produced a rule, so a caller that displayed a trade as evidence
    would be guessing. The source field says where an association came from, so a
    reader can tell a real association from the absence of one.
    """
    if not isinstance(metrics, dict):
        metrics = {}
    trade_ids: list[str] = []
    for key in ("trade_ids", "evidence_trade_ids", "samples"):
        value = metrics.get(key)
        if isinstance(value, list):
            trade_ids.extend(_clean(item) for item in value if _clean(item))
        elif isinstance(value, str) and value.strip():
            trade_ids.extend(part.strip() for part in value.split(",") if part.strip())

    sample_count = metrics.get("sample_count")
    try:
        trigger_count = int(sample_count) if sample_count is not None else 0
    except (TypeError, ValueError):
        trigger_count = 0

    if trade_ids:
        confidence = "high" if trigger_count >= 20 else "low"
        source = "metrics"
    else:
        confidence = "none"
        source = "unassociated"

    return {
        "trade_ids": trade_ids,
        "trigger_count": trigger_count if trade_ids else 0,
        "confidence": confidence,
        "source": source,
    }

