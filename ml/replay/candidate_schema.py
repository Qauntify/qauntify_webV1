"""Versioned schema and fail-safe validation for replay candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from ml.data.validate_dataset import TIMEFRAME_SECONDS


CANDIDATE_SCHEMA_VERSION = "candidate_v1"
CANDIDATE_STATUS = "generated"
PARTITION_COLUMNS = ("symbol", "timeframe", "strategy_name", "year")
FUTURE_DERIVED_FIELDS = frozenset({
    "outcome", "label", "target", "exit_price", "exit_timestamp",
    "bars_to_outcome", "realized_r", "future_return", "win",
})


class CandidateValidationError(ValueError):
    """A candidate is unsafe, ambiguous, or violates the versioned schema."""


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    candidate_timestamp: str
    source_candle_timestamp: str
    symbol: str
    timeframe: str
    strategy_name: str
    strategy_version: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_distance: float
    risk_reward_tp1: float
    risk_reward_tp2: float
    risk_reward_tp3: float
    signal_reason: str
    candidate_status: str
    dataset_id: str
    dataset_checksum: str
    replay_config_version: str
    source_commit: str | None
    created_at: str
    schema_version: str = CANDIDATE_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _as_utc(value: object, field: str):
    import pandas as pd

    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise CandidateValidationError(f"{field} is not a valid timestamp: {value!r}")
    return parsed


def validate_candidate(candidate: CandidateRecord | Mapping) -> None:
    row = candidate.to_dict() if isinstance(candidate, CandidateRecord) else dict(candidate)
    forbidden = sorted(FUTURE_DERIVED_FIELDS.intersection(row))
    if forbidden:
        raise CandidateValidationError(f"Future-derived fields are forbidden: {forbidden!r}")
    direction = row.get("direction")
    if direction not in {"long", "short"}:
        raise CandidateValidationError(f"Unrecognized direction: {direction!r}")
    timeframe = row.get("timeframe")
    if timeframe not in TIMEFRAME_SECONDS:
        raise CandidateValidationError(f"Unrecognized timeframe: {timeframe!r}")
    if not str(row.get("strategy_name", "")).strip():
        raise CandidateValidationError("strategy_name must be non-empty")
    if not str(row.get("strategy_version", "")).strip():
        raise CandidateValidationError("strategy_version must be non-empty")
    if row.get("candidate_status") != CANDIDATE_STATUS:
        raise CandidateValidationError(f"candidate_status must be {CANDIDATE_STATUS!r}")
    if row.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise CandidateValidationError(f"schema_version must be {CANDIDATE_SCHEMA_VERSION!r}")

    names = ("entry_price", "stop_loss", "take_profit_1", "take_profit_2", "take_profit_3")
    try:
        prices = {name: float(row[name]) for name in names}
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateValidationError("Candidate price fields must be numeric") from exc
    if any(value <= 0 for value in prices.values()):
        raise CandidateValidationError("Entry, stop, and take-profit prices must be positive")
    entry = prices["entry_price"]
    stop = prices["stop_loss"]
    tp1, tp2, tp3 = (prices[f"take_profit_{index}"] for index in (1, 2, 3))
    valid_geometry = (
        stop < entry < tp1 <= tp2 <= tp3
        if direction == "long"
        else stop > entry > tp1 >= tp2 >= tp3
    )
    if not valid_geometry:
        raise CandidateValidationError(f"Invalid {direction} TP/SL geometry")
    risk = abs(entry - stop)
    if abs(float(row.get("risk_distance", risk)) - risk) > 1e-9:
        raise CandidateValidationError("risk_distance disagrees with entry and stop")
    for index, target in enumerate((tp1, tp2, tp3), start=1):
        expected_rr = abs(target - entry) / risk
        if abs(float(row.get(f"risk_reward_tp{index}", expected_rr)) - expected_rr) > 1e-9:
            raise CandidateValidationError(f"risk_reward_tp{index} is inconsistent")
    source_time = _as_utc(row.get("source_candle_timestamp"), "source_candle_timestamp")
    candidate_time = _as_utc(row.get("candidate_timestamp"), "candidate_timestamp")
    if candidate_time < source_time:
        raise CandidateValidationError("candidate_timestamp precedes its source candle")
    if not str(row.get("candidate_id", "")).strip():
        raise CandidateValidationError("candidate_id must be non-empty")


def validate_candidates(candidates: Iterable[CandidateRecord]) -> tuple[int, int]:
    """Validate all rows and return (exact duplicates, duplicate IDs)."""
    rows = []
    for candidate in candidates:
        validate_candidate(candidate)
        rows.append(candidate.to_dict())
    if not rows:
        return 0, 0
    import pandas as pd

    frame = pd.DataFrame(rows)
    exact = int(frame.duplicated(keep="first").sum())
    duplicate_ids = frame[frame.duplicated("candidate_id", keep=False)]
    if not duplicate_ids.empty:
        conflicts = duplicate_ids.drop(columns=["created_at"], errors="ignore").groupby(
            "candidate_id", dropna=False
        ).nunique(dropna=False).max(axis=1)
        conflict_ids = conflicts[conflicts > 1].index.tolist()
        if conflict_ids:
            raise CandidateValidationError(
                f"Conflicting candidates share deterministic IDs: {conflict_ids[:10]!r}"
            )
        raise CandidateValidationError("Duplicate candidate IDs detected")
    return exact, 0
