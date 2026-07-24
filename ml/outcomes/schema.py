"""Versioned schema and validation for candidate outcomes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping


OUTCOME_SCHEMA_VERSION = "outcome_v1"
OUTCOME_CLASSES = frozenset({
    "sl_before_tp1", "tp1_then_sl", "tp2_then_sl", "tp3_hit",
    "expired", "right_censored",
})
PARTITION_COLUMNS = ("strategy_name", "timeframe", "outcome_class", "year")


class OutcomeValidationError(ValueError):
    """An outcome row is incomplete, inconsistent, or unsafe to export."""


@dataclass(frozen=True)
class OutcomeRecord:
    candidate_id: str
    strategy_name: str
    timeframe: str
    direction: str
    outcome_policy_version: str
    outcome_class: str
    entry_triggered: bool
    entry_triggered_at: str
    entry_price: float
    tp1_hit: bool
    tp1_hit_at: str | None
    tp2_hit: bool
    tp2_hit_at: str | None
    tp3_hit: bool
    tp3_hit_at: str | None
    sl_hit: bool
    sl_hit_at: str | None
    expired: bool
    expiry_at: str
    right_censored: bool
    resolution_timestamp: str
    exit_price: float | None
    holding_seconds: float
    mfe_r: float
    mae_r: float
    gross_realized_r: float | None
    net_realized_r: float | None
    execution_cost_r: float
    ambiguous_parent_candles: int
    lower_timeframe_resolutions: int
    conservative_fallbacks: int
    candidate_dataset_id: str
    candidate_dataset_checksum: str
    source_dataset_id: str
    source_dataset_checksum: str
    source_commit: str | None
    created_at: str
    schema_version: str = OUTCOME_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def validate_outcome(outcome: OutcomeRecord | Mapping) -> None:
    row = outcome.to_dict() if isinstance(outcome, OutcomeRecord) else dict(outcome)
    if not str(row.get("candidate_id", "")).strip():
        raise OutcomeValidationError("candidate_id must be non-empty")
    if row.get("schema_version") != OUTCOME_SCHEMA_VERSION:
        raise OutcomeValidationError(f"schema_version must be {OUTCOME_SCHEMA_VERSION!r}")
    if row.get("outcome_policy_version") != OUTCOME_SCHEMA_VERSION:
        raise OutcomeValidationError("outcome_policy_version does not match the schema")
    outcome_class = row.get("outcome_class")
    if outcome_class not in OUTCOME_CLASSES:
        raise OutcomeValidationError(f"Unknown outcome class: {outcome_class!r}")
    if row.get("direction") not in {"long", "short"}:
        raise OutcomeValidationError("direction must be long or short")
    if row.get("entry_triggered") is not True:
        raise OutcomeValidationError("outcome_v1 requires market-on-close entry")
    if float(row.get("entry_price", 0)) <= 0:
        raise OutcomeValidationError("entry_price must be positive")
    hits = [bool(row.get(f"tp{index}_hit")) for index in (1, 2, 3)]
    if hits[1] and not hits[0] or hits[2] and not all(hits[:2]):
        raise OutcomeValidationError("Take-profit hits must be sequential")
    for index, hit in enumerate(hits, start=1):
        if hit != bool(row.get(f"tp{index}_hit_at")):
            raise OutcomeValidationError(f"tp{index}_hit timestamp disagrees with flag")
    if bool(row.get("sl_hit")) != bool(row.get("sl_hit_at")):
        raise OutcomeValidationError("sl_hit timestamp disagrees with flag")
    if outcome_class == "tp3_hit" and not hits[2]:
        raise OutcomeValidationError("tp3_hit class requires TP3")
    if outcome_class in {"sl_before_tp1", "tp1_then_sl", "tp2_then_sl"}:
        expected_hits = {"sl_before_tp1": 0, "tp1_then_sl": 1, "tp2_then_sl": 2}[outcome_class]
        if not row.get("sl_hit") or sum(hits) != expected_hits:
            raise OutcomeValidationError("Stop outcome class disagrees with TP history")
    if bool(row.get("expired")) != (outcome_class == "expired"):
        raise OutcomeValidationError("expired flag disagrees with outcome class")
    if bool(row.get("right_censored")) != (outcome_class == "right_censored"):
        raise OutcomeValidationError("right_censored flag disagrees with outcome class")
    if float(row.get("holding_seconds", -1)) < 0:
        raise OutcomeValidationError("holding_seconds must be non-negative")
    if float(row.get("mfe_r", -1)) < 0 or float(row.get("mae_r", -1)) < 0:
        raise OutcomeValidationError("MFE and MAE must be non-negative")
    gross, net = row.get("gross_realized_r"), row.get("net_realized_r")
    if outcome_class == "right_censored":
        if gross is not None or net is not None:
            raise OutcomeValidationError("Censored outcomes cannot have realized R")
    else:
        if gross is None or net is None:
            raise OutcomeValidationError("Resolved outcomes require gross and net R")
        expected_net = float(gross) - float(row.get("execution_cost_r", 0))
        if abs(float(net) - expected_net) > 1e-9:
            raise OutcomeValidationError("net_realized_r disagrees with cost policy")


def validate_outcomes(outcomes: Iterable[OutcomeRecord]) -> None:
    rows = []
    for outcome in outcomes:
        validate_outcome(outcome)
        rows.append(outcome.to_dict())
    if not rows:
        return
    import pandas as pd

    frame = pd.DataFrame(rows)
    duplicates = frame[frame.duplicated("candidate_id", keep=False)]
    if not duplicates.empty:
        raise OutcomeValidationError("Duplicate candidate IDs in outcome dataset")

