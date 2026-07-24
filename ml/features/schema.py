"""Fixed schema and fail-closed validation for feature_v1."""
from __future__ import annotations

import math


FEATURE_SCHEMA_VERSION = "feature_v1"
IDENTITY_COLUMNS = (
    "candidate_id", "candidate_timestamp", "source_candle_timestamp", "symbol",
    "strategy_name", "timeframe", "direction", "feature_policy_version",
)
NUMERIC_FEATURES = (
    "entry_price", "risk_distance", "risk_atr", "tp1_r", "tp2_r", "tp3_r",
    "close", "ema9", "ema21", "ema_gap_atr", "close_ema9_atr", "close_ema21_atr",
    "atr14", "atr_pct", "rsi14", "macd_hist", "macd_hist_atr", "adx14",
    "return_1", "return_5", "volatility_20", "range_20_atr", "range_position_20",
    "candle_range_atr", "body_atr", "upper_wick_atr", "lower_wick_atr",
    "hour_utc", "day_of_week", "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    "bull_fvg_width_atr", "bull_fvg_distance_atr", "bull_fvg_age",
    "bear_fvg_width_atr", "bear_fvg_distance_atr", "bear_fvg_age",
    "support_distance_atr", "support_width_atr", "support_touches",
    "resistance_distance_atr", "resistance_width_atr", "resistance_touches",
    "pivot_high_count", "pivot_low_count", "distance_recent_high_atr",
    "distance_recent_low_atr", "strategy_sweep_distance_atr",
    "strategy_choch_distance_atr", "strategy_fvg_width_atr",
    "strategy_zone_width_atr", "strategy_zone_distance_atr", "strategy_zone_touches",
)
BOOLEAN_FEATURES = (
    "trend_up", "trend_down", "session_asia", "session_london", "session_new_york",
    "session_overlap", "at_recent_high", "at_recent_low",
)
CATEGORICAL_FEATURES = ("trend_direction", "htf_trend", "strategy_structure", "strategy_zone_side")
PROVENANCE_COLUMNS = (
    "candidate_dataset_id", "candidate_dataset_checksum", "source_dataset_id",
    "source_dataset_checksum", "source_commit", "schema_version",
)
ALL_COLUMNS = IDENTITY_COLUMNS + NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES + PROVENANCE_COLUMNS


class FeatureValidationError(ValueError):
    pass


def validate_feature(row: dict) -> None:
    if set(row) != set(ALL_COLUMNS):
        raise FeatureValidationError(f"Feature columns disagree: missing={sorted(set(ALL_COLUMNS)-set(row))}, extra={sorted(set(row)-set(ALL_COLUMNS))}")
    if not str(row["candidate_id"]).strip():
        raise FeatureValidationError("candidate_id must be non-empty")
    if row["feature_policy_version"] != FEATURE_SCHEMA_VERSION or row["schema_version"] != FEATURE_SCHEMA_VERSION:
        raise FeatureValidationError("Feature policy/schema version mismatch")
    if row["direction"] not in {"long", "short"}:
        raise FeatureValidationError("Invalid direction")
    for name in NUMERIC_FEATURES:
        value = row[name]
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(float(value))):
            raise FeatureValidationError(f"{name} must be finite numeric or null")
    for name in BOOLEAN_FEATURES:
        if not isinstance(row[name], bool):
            raise FeatureValidationError(f"{name} must be boolean")
    import pandas as pd
    source = pd.Timestamp(row["source_candle_timestamp"])
    candidate = pd.Timestamp(row["candidate_timestamp"])
    if source.tz is None or candidate.tz is None or source >= candidate:
        raise FeatureValidationError("Source candle must precede candidate timestamp")


def validate_features(rows) -> None:
    ids = []
    for row in rows:
        validate_feature(row)
        ids.append(row["candidate_id"])
    if len(ids) != len(set(ids)):
        raise FeatureValidationError("Duplicate candidate IDs in feature dataset")
