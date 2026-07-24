"""Manifest-aware orchestration for causal historical feature generation."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
import pyarrow.dataset as ds

from ml.data.export_dataset import _dataset_checksum
from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.features.calculator import calculate_feature_row
from ml.features.config import FeatureConfig, FeatureConfigurationError
from ml.features.schema import validate_features
from ml.replay.replay_engine import frame_to_candles, load_replay_config
from ml.replay.strategy_adapter import calculate_causal_indicators
from ml.replay.replay_export import _checksum
from signals.backtest import htf_trend_series


@dataclass(frozen=True)
class FeatureResult:
    features: tuple[dict, ...]
    candidate_manifest: dict
    candle_manifest: dict
    candidates_processed: int


def validate_manifests(config: FeatureConfig):
    if not config.candidate_manifest_path.is_file() or not config.candle_manifest_path.is_file():
        raise FeatureConfigurationError("Candidate or candle manifest is missing")
    candidate = json.loads(config.candidate_manifest_path.read_text("utf-8"))
    candle = json.loads(config.candle_manifest_path.read_text("utf-8"))
    candidate_files = tuple(sorted(config.candidates_root.rglob("*.parquet")))
    candle_files = tuple(sorted(config.candles_root.rglob("*.parquet")))
    if len(candidate_files) != int(candidate["file_count"]) or _checksum(config.candidates_root, candidate_files) != candidate["checksum"]:
        raise FeatureConfigurationError("Candidate dataset disagrees with its manifest")
    if len(candle_files) != int(candle["file_count"]) or _dataset_checksum(config.candles_root, candle_files) != candle["checksum"]:
        raise FeatureConfigurationError("Candle dataset disagrees with its manifest")
    if candidate["source_dataset_id"] != candle["dataset_id"] or candidate["source_dataset_checksum"] != candle["checksum"]:
        raise FeatureConfigurationError("Candidate/candle provenance mismatch")
    return candidate, candle


def _dataset(root):
    return ds.dataset(root, format="parquet", partitioning="hive", exclude_invalid_files=True)


def load_candidates(config, *, strategy=None, timeframe=None, start=None, end=None, limit=None):
    dataset = _dataset(config.candidates_root)
    expression = ds.field("symbol") == "XAUUSD"
    if strategy: expression &= ds.field("strategy_name") == strategy
    if timeframe: expression &= ds.field("timeframe") == timeframe
    frame = dataset.to_table(filter=expression).to_pandas()
    frame["candidate_timestamp"] = pd.to_datetime(frame["candidate_timestamp"], utc=True)
    frame["source_candle_timestamp"] = pd.to_datetime(frame["source_candle_timestamp"], utc=True)
    if start is not None: frame = frame[frame.candidate_timestamp >= pd.to_datetime(start, utc=True)]
    if end is not None: frame = frame[frame.candidate_timestamp <= pd.to_datetime(end, utc=True)]
    frame = frame.sort_values(["timeframe", "source_candle_timestamp", "candidate_id"], kind="mergesort")
    if frame.candidate_id.duplicated().any():
        raise FeatureConfigurationError("Duplicate candidate IDs remain")
    if limit is not None: frame = frame.head(limit)
    return frame.reset_index(drop=True)


def load_candles(config, timeframe):
    dataset = _dataset(config.candles_root)
    expression = (ds.field("symbol") == "XAUUSD") & (ds.field("timeframe") == timeframe)
    columns = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"]
    frame = dataset.to_table(filter=expression, columns=columns).to_pandas()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if frame.timestamp.duplicated().any():
        raise FeatureConfigurationError(f"Duplicate {timeframe} candle timestamps")
    return frame


def generate_features(config: FeatureConfig, *, strategy=None, timeframe=None, start=None, end=None, limit=None):
    candidate_manifest, candle_manifest = validate_manifests(config)
    candidates = load_candidates(config, strategy=strategy, timeframe=timeframe, start=start, end=end, limit=limit)
    replay = load_replay_config(config.candidates_root.parents[2] / "configs" / "strategy_replay_v1.yaml")
    strategy_configs = {item.name: item for item in replay.strategies}
    rows = []
    for primary_timeframe, group in candidates.groupby("timeframe", sort=True):
        frame = load_candles(config, primary_timeframe)
        candles = frame_to_candles(frame)
        indicators = calculate_causal_indicators(candles)
        positions = {int(timestamp.value): index for index, timestamp in enumerate(frame.timestamp)}
        trends_by_strategy = {}
        for strategy_name in group.strategy_name.unique():
            strategy_config = strategy_configs[strategy_name]
            if strategy_config.timeframe != primary_timeframe:
                raise FeatureConfigurationError("Replay strategy/timeframe drift")
            if strategy_config.confluence_timeframe:
                htf_frame = load_candles(config, strategy_config.confluence_timeframe)
                trends_by_strategy[strategy_name] = htf_trend_series(
                    candles, frame_to_candles(htf_frame),
                    TIMEFRAME_SECONDS[strategy_config.confluence_timeframe] // 60,
                )
            else:
                trends_by_strategy[strategy_name] = [None] * len(candles)
        for candidate in group.to_dict("records"):
            source_ns = int(pd.Timestamp(candidate["source_candle_timestamp"]).value)
            if source_ns not in positions:
                raise FeatureConfigurationError(f"Candidate source candle is absent: {candidate['candidate_id']}")
            index = positions[source_ns]
            # The source candle closes exactly at the decision timestamp.
            duration = pd.Timedelta(pd.Timestamp(candidate["candidate_timestamp"]) - pd.Timestamp(candidate["source_candle_timestamp"]))
            if duration <= pd.Timedelta(0) or frame.timestamp.iat[index] + duration != candidate["candidate_timestamp"]:
                raise FeatureConfigurationError(f"Invalid causal boundary: {candidate['candidate_id']}")
            rows.append(calculate_feature_row(
                candidate, candles=candles, indicators=indicators, index=index,
                htf_trend=trends_by_strategy[candidate["strategy_name"]][index], config=config,
                candidate_manifest=candidate_manifest, candle_manifest=candle_manifest,
            ))
    validate_features(rows)
    return FeatureResult(tuple(rows), candidate_manifest, candle_manifest, len(candidates))
