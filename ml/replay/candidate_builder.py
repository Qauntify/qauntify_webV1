"""Build reproducible candidate records from production CandidateSetup objects."""
from __future__ import annotations

import hashlib
import json
from ml.replay.candidate_schema import CandidateRecord, validate_candidate


def _stable_float(value: float) -> str:
    return format(float(value), ".17g")


def deterministic_candidate_id(**fields: object) -> str:
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signal_reason(indicators: dict) -> str:
    return str(
        indicators.get("structure")
        or indicators.get("side")
        or indicators.get("strategy")
        or "rule_match"
    )


def build_candidate(
    setup,
    *,
    candidate_timestamp: str,
    source_candle_timestamp: str,
    timeframe: str,
    strategy_name: str,
    strategy_version: str,
    dataset_id: str,
    dataset_checksum: str,
    replay_config_version: str,
    source_commit: str | None,
) -> CandidateRecord:
    tp1, tp2, tp3 = (float(value) for value in setup.resolved_take_profits())
    entry = float(setup.entry)
    stop = float(setup.stop_loss)
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("Candidate risk distance must be positive")
    candidate_id = deterministic_candidate_id(
        dataset_id=dataset_id,
        symbol=setup.symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        candidate_timestamp=candidate_timestamp,
        direction=setup.direction,
        entry_price=_stable_float(entry),
        stop_loss=_stable_float(stop),
    )
    record = CandidateRecord(
        candidate_id=candidate_id,
        candidate_timestamp=candidate_timestamp,
        source_candle_timestamp=source_candle_timestamp,
        symbol=setup.symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        direction=setup.direction,
        entry_price=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        risk_distance=risk,
        risk_reward_tp1=abs(tp1 - entry) / risk,
        risk_reward_tp2=abs(tp2 - entry) / risk,
        risk_reward_tp3=abs(tp3 - entry) / risk,
        signal_reason=signal_reason(setup.indicators),
        candidate_status="generated",
        dataset_id=dataset_id,
        dataset_checksum=dataset_checksum,
        replay_config_version=replay_config_version,
        source_commit=source_commit,
        # Logical record time is the decision time, keeping replay deterministic.
        created_at=candidate_timestamp,
    )
    validate_candidate(record)
    return record
