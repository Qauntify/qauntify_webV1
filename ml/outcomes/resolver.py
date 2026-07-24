"""Causal outcome resolution for historical strategy candidates."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.outcomes.config import OutcomeConfig
from ml.outcomes.schema import OutcomeRecord, validate_outcome


@dataclass(frozen=True)
class CandleIndex:
    timeframe: str
    timestamps_ns: np.ndarray
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray

    @classmethod
    def from_frame(cls, frame, timeframe: str) -> "CandleIndex":
        ordered = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        timestamps = pd.to_datetime(ordered["timestamp"], utc=True)
        if ordered.duplicated(["symbol", "timeframe", "timestamp"]).any():
            raise ValueError(f"Duplicate candle keys in {timeframe}")
        return cls(
            timeframe=timeframe,
            # Pandas may retain an input's microsecond Arrow resolution. Force
            # nanoseconds so search bounds use the same unit as Timestamp.value.
            timestamps_ns=timestamps.to_numpy(dtype="datetime64[ns]").astype("int64"),
            opens=ordered["open"].to_numpy(dtype="float64"),
            highs=ordered["high"].to_numpy(dtype="float64"),
            lows=ordered["low"].to_numpy(dtype="float64"),
            closes=ordered["close"].to_numpy(dtype="float64"),
        )

    @property
    def duration_ns(self) -> int:
        return int(TIMEFRAME_SECONDS[self.timeframe] * 1_000_000_000)

    @property
    def data_end_ns(self) -> int:
        if not len(self.timestamps_ns):
            return 0
        return int(self.timestamps_ns[-1] + self.duration_ns)

    def bounds(self, start_ns: int, end_ns: int) -> tuple[int, int]:
        return (
            int(np.searchsorted(self.timestamps_ns, start_ns, side="left")),
            int(np.searchsorted(self.timestamps_ns, end_ns, side="left")),
        )


def _iso(timestamp_ns: int) -> str:
    return pd.Timestamp(timestamp_ns, tz="UTC").isoformat()


def _candidate_value(candidate, name: str):
    return candidate[name] if isinstance(candidate, dict) else getattr(candidate, name)


def _level_hits(direction: str, high: float, low: float, stop: float,
                targets: tuple[float, float, float], hit_count: int) -> tuple[bool, list[int]]:
    stop_hit = low <= stop if direction == "long" else high >= stop
    target_hits = []
    for index in range(hit_count, 3):
        touched = high >= targets[index] if direction == "long" else low <= targets[index]
        if not touched:
            break
        target_hits.append(index)
    return stop_hit, target_hits


def _complete_lower_slice(lower: CandleIndex, start_ns: int, end_ns: int):
    left, right = lower.bounds(start_ns, end_ns)
    actual = lower.timestamps_ns[left:right]
    expected = np.arange(start_ns, end_ns, lower.duration_ns, dtype="int64")
    return left, right, len(actual) == len(expected) and np.array_equal(actual, expected)


def resolve_candidate(
    candidate,
    *,
    primary: CandleIndex,
    lower: CandleIndex,
    config: OutcomeConfig,
    candidate_manifest: dict,
    candle_manifest: dict,
) -> OutcomeRecord:
    """Resolve one market-on-close candidate using only subsequent candles."""
    candidate_id = str(_candidate_value(candidate, "candidate_id"))
    direction = str(_candidate_value(candidate, "direction"))
    timeframe = str(_candidate_value(candidate, "timeframe"))
    entry = float(_candidate_value(candidate, "entry_price"))
    stop = float(_candidate_value(candidate, "stop_loss"))
    targets = tuple(float(_candidate_value(candidate, f"take_profit_{i}")) for i in (1, 2, 3))
    entry_time = pd.Timestamp(_candidate_value(candidate, "candidate_timestamp"))
    entry_time = entry_time.tz_localize("UTC") if entry_time.tz is None else entry_time.tz_convert("UTC")
    entry_ns = int(entry_time.value)
    expiry = entry_time + pd.Timedelta(days=config.expiry_days[timeframe])
    expiry_ns = int(expiry.value)
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError(f"Candidate {candidate_id} has zero risk")

    left, right = primary.bounds(entry_ns, expiry_ns)
    hit_times: list[int | None] = [None, None, None]
    hit_count = 0
    gross_booked = 0.0
    remaining = 1.0
    sl_time = None
    exit_price = None
    resolution_ns = None
    outcome_class = None
    mfe_r = mae_r = 0.0
    ambiguous = lower_resolutions = conservative = 0
    last_close = None
    last_close_ns = None

    def update_excursion(high: float, low: float) -> None:
        nonlocal mfe_r, mae_r
        if direction == "long":
            mfe_r = max(mfe_r, (high - entry) / risk)
            mae_r = max(mae_r, (entry - low) / risk)
        else:
            mfe_r = max(mfe_r, (entry - low) / risk)
            mae_r = max(mae_r, (high - entry) / risk)
        mfe_r = max(mfe_r, 0.0)
        mae_r = max(mae_r, 0.0)

    def book_targets(indices: list[int], event_ns: int) -> bool:
        nonlocal hit_count, gross_booked, remaining, resolution_ns, exit_price, outcome_class
        for index in indices:
            if index != hit_count:
                break
            fraction = config.take_profit_fractions[index]
            target_r = abs(targets[index] - entry) / risk
            gross_booked += fraction * target_r
            remaining -= fraction
            hit_times[index] = event_ns
            hit_count += 1
            if hit_count == 3:
                remaining = 0.0
                resolution_ns = event_ns
                exit_price = targets[2]
                outcome_class = "tp3_hit"
                return True
        return False

    def stop_trade(event_ns: int) -> None:
        nonlocal gross_booked, remaining, sl_time, resolution_ns, exit_price, outcome_class
        gross_booked -= remaining
        remaining = 0.0
        sl_time = event_ns
        resolution_ns = event_ns
        exit_price = stop
        outcome_class = ("sl_before_tp1", "tp1_then_sl", "tp2_then_sl")[hit_count]

    for index in range(left, right):
        parent_start = int(primary.timestamps_ns[index])
        parent_end = parent_start + primary.duration_ns
        high, low = float(primary.highs[index]), float(primary.lows[index])
        stop_hit, target_hits = _level_hits(direction, high, low, stop, targets, hit_count)
        if stop_hit and target_hits:
            ambiguous += 1
            lower_left, lower_right, complete = _complete_lower_slice(
                lower, parent_start, parent_end,
            )
            resolved_in_lower = False
            if complete:
                lower_resolutions += 1
                for lower_index in range(lower_left, lower_right):
                    lower_high = float(lower.highs[lower_index])
                    lower_low = float(lower.lows[lower_index])
                    update_excursion(lower_high, lower_low)
                    lower_end = int(lower.timestamps_ns[lower_index] + lower.duration_ns)
                    lower_stop, lower_targets = _level_hits(
                        direction, lower_high, lower_low, stop, targets, hit_count,
                    )
                    if lower_stop and lower_targets:
                        conservative += 1
                        stop_trade(lower_end)
                        resolved_in_lower = True
                        break
                    if lower_stop:
                        stop_trade(lower_end)
                        resolved_in_lower = True
                        break
                    if lower_targets:
                        resolved_in_lower = True
                        if book_targets(lower_targets, lower_end):
                            break
                if outcome_class is not None:
                    break
            if not complete or not resolved_in_lower:
                conservative += 1
                update_excursion(high, low)
                stop_trade(parent_end)
                break
        else:
            update_excursion(high, low)
            if stop_hit:
                stop_trade(parent_end)
                break
            if target_hits and book_targets(target_hits, parent_end):
                break
        last_close = float(primary.closes[index])
        last_close_ns = parent_end

    right_censored = False
    expired = False
    if outcome_class is None:
        if primary.data_end_ns < expiry_ns or last_close is None:
            outcome_class = "right_censored"
            right_censored = True
            resolution_ns = last_close_ns or min(primary.data_end_ns, expiry_ns)
            exit_price = None
        else:
            outcome_class = "expired"
            expired = True
            resolution_ns = expiry_ns
            exit_price = last_close
            signed_r = (
                (last_close - entry) / risk
                if direction == "long" else (entry - last_close) / risk
            )
            gross_booked += remaining * signed_r
            remaining = 0.0

    gross_r = None if right_censored else float(gross_booked)
    net_r = None if gross_r is None else gross_r - config.estimated_round_trip_cost_r
    record = OutcomeRecord(
        candidate_id=candidate_id,
        strategy_name=str(_candidate_value(candidate, "strategy_name")),
        timeframe=timeframe,
        direction=direction,
        outcome_policy_version=config.version,
        outcome_class=outcome_class,
        entry_triggered=True,
        entry_triggered_at=entry_time.isoformat(),
        entry_price=entry,
        tp1_hit=hit_count >= 1,
        tp1_hit_at=_iso(hit_times[0]) if hit_times[0] else None,
        tp2_hit=hit_count >= 2,
        tp2_hit_at=_iso(hit_times[1]) if hit_times[1] else None,
        tp3_hit=hit_count >= 3,
        tp3_hit_at=_iso(hit_times[2]) if hit_times[2] else None,
        sl_hit=sl_time is not None,
        sl_hit_at=_iso(sl_time) if sl_time else None,
        expired=expired,
        expiry_at=expiry.isoformat(),
        right_censored=right_censored,
        resolution_timestamp=_iso(resolution_ns),
        exit_price=exit_price,
        holding_seconds=max((resolution_ns - entry_ns) / 1_000_000_000, 0.0),
        mfe_r=float(mfe_r),
        mae_r=float(mae_r),
        gross_realized_r=gross_r,
        net_realized_r=net_r,
        execution_cost_r=config.estimated_round_trip_cost_r,
        ambiguous_parent_candles=ambiguous,
        lower_timeframe_resolutions=lower_resolutions,
        conservative_fallbacks=conservative,
        candidate_dataset_id=candidate_manifest["candidate_dataset_id"],
        candidate_dataset_checksum=candidate_manifest["checksum"],
        source_dataset_id=candle_manifest["dataset_id"],
        source_dataset_checksum=candle_manifest["checksum"],
        source_commit=candidate_manifest.get("source_commit"),
        created_at=_iso(resolution_ns),
    )
    validate_outcome(record)
    return record
