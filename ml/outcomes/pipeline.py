"""Manifest-aware orchestration for historical outcome resolution."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from ml.data.export_dataset import _dataset_checksum
from ml.outcomes.config import OutcomeConfig, OutcomeConfigurationError
from ml.outcomes.resolver import CandleIndex, resolve_candidate
from ml.outcomes.schema import OutcomeRecord, validate_outcomes
from ml.replay.replay_export import _checksum as candidate_checksum


@dataclass(frozen=True)
class ResolutionResult:
    outcomes: tuple[OutcomeRecord, ...]
    candidate_manifest: dict
    candle_manifest: dict
    candidates_processed: int


def _utc_timestamp(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")


def load_and_validate_manifests(config: OutcomeConfig) -> tuple[dict, dict]:
    if not config.candidate_manifest_path.is_file():
        raise OutcomeConfigurationError("Candidate manifest is missing")
    if not config.candle_manifest_path.is_file():
        raise OutcomeConfigurationError("Candle manifest is missing")
    candidate_manifest = json.loads(config.candidate_manifest_path.read_text("utf-8"))
    candle_manifest = json.loads(config.candle_manifest_path.read_text("utf-8"))
    candidate_required = {
        "candidate_dataset_id", "checksum", "candidate_count", "file_count",
        "source_dataset_id", "source_dataset_checksum",
    }
    candle_required = {"dataset_id", "checksum", "file_count", "timeframes"}
    if missing := sorted(candidate_required - set(candidate_manifest)):
        raise OutcomeConfigurationError(f"Candidate manifest fields missing: {missing!r}")
    if missing := sorted(candle_required - set(candle_manifest)):
        raise OutcomeConfigurationError(f"Candle manifest fields missing: {missing!r}")
    if candidate_manifest["source_dataset_id"] != candle_manifest["dataset_id"]:
        raise OutcomeConfigurationError("Candidate and candle dataset IDs disagree")
    if candidate_manifest["source_dataset_checksum"] != candle_manifest["checksum"]:
        raise OutcomeConfigurationError("Candidate and candle checksums disagree")
    candidate_files = tuple(sorted(config.candidates_root.rglob("*.parquet")))
    candle_files = tuple(sorted(config.candles_root.rglob("*.parquet")))
    if len(candidate_files) != int(candidate_manifest["file_count"]):
        raise OutcomeConfigurationError("Candidate manifest file count mismatch")
    if len(candle_files) != int(candle_manifest["file_count"]):
        raise OutcomeConfigurationError("Candle manifest file count mismatch")
    if candidate_checksum(config.candidates_root, candidate_files) != candidate_manifest["checksum"]:
        raise OutcomeConfigurationError("Candidate dataset checksum mismatch")
    if _dataset_checksum(config.candles_root, candle_files) != candle_manifest["checksum"]:
        raise OutcomeConfigurationError("Candle dataset checksum mismatch")
    required_timeframes = set(config.expiry_days) | set(config.lower_timeframes.values())
    if missing := sorted(required_timeframes - set(candle_manifest["timeframes"])):
        raise OutcomeConfigurationError(f"Required candle timeframes missing: {missing!r}")
    return candidate_manifest, candle_manifest


def load_candidates(config: OutcomeConfig, *, strategy=None, timeframe=None,
                    start=None, end=None, limit=None):
    dataset = ds.dataset(
        config.candidates_root, format="parquet", partitioning="hive",
        exclude_invalid_files=True,
    )
    expression = ds.field("symbol") == "XAUUSD"
    if strategy:
        expression &= ds.field("strategy_name") == strategy
    if timeframe:
        expression &= ds.field("timeframe") == timeframe
    frame = dataset.to_table(filter=expression).to_pandas()
    frame["candidate_timestamp"] = pd.to_datetime(frame["candidate_timestamp"], utc=True)
    if start is not None:
        frame = frame[frame.candidate_timestamp >= _utc_timestamp(start)]
    if end is not None:
        frame = frame[frame.candidate_timestamp <= _utc_timestamp(end)]
    frame = frame.sort_values(["timeframe", "candidate_timestamp", "candidate_id"])
    if frame.candidate_id.duplicated().any():
        raise OutcomeConfigurationError("Duplicate candidate IDs remain")
    if limit is not None:
        frame = frame.head(limit)
    return frame.reset_index(drop=True)


def load_candle_frame(config: OutcomeConfig, timeframe: str, *, start, end):
    dataset = ds.dataset(
        config.candles_root, format="parquet", partitioning="hive",
        exclude_invalid_files=True,
    )
    start_time = _utc_timestamp(start)
    end_time = _utc_timestamp(end)
    expression = (
        (ds.field("symbol") == "XAUUSD")
        & (ds.field("timeframe") == timeframe)
        & (ds.field("timestamp") >= start_time.to_pydatetime())
        & (ds.field("timestamp") < end_time.to_pydatetime())
    )
    columns = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close"]
    frame = dataset.to_table(filter=expression, columns=columns).to_pandas()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def resolve_outcomes(config: OutcomeConfig, *, strategy=None, timeframe=None,
                     start=None, end=None, limit=None) -> ResolutionResult:
    candidate_manifest, candle_manifest = load_and_validate_manifests(config)
    candidates = load_candidates(
        config, strategy=strategy, timeframe=timeframe,
        start=start, end=end, limit=limit,
    )
    outcomes: list[OutcomeRecord] = []
    for primary_timeframe, group in candidates.groupby("timeframe", sort=True):
        if primary_timeframe not in config.expiry_days:
            raise OutcomeConfigurationError(f"No outcome policy for {primary_timeframe}")
        lower_timeframe = config.lower_timeframes[primary_timeframe]
        candle_start = group.candidate_timestamp.min()
        candle_end = (
            group.candidate_timestamp.max()
            + pd.Timedelta(days=config.expiry_days[primary_timeframe])
            + pd.Timedelta(seconds=TIMEFRAME_PADDING_SECONDS[primary_timeframe])
        )
        primary_frame = load_candle_frame(
            config, primary_timeframe, start=candle_start, end=candle_end,
        )
        lower_frame = load_candle_frame(
            config, lower_timeframe, start=candle_start, end=candle_end,
        )
        primary_index = CandleIndex.from_frame(primary_frame, primary_timeframe)
        lower_index = CandleIndex.from_frame(lower_frame, lower_timeframe)
        for candidate in group.to_dict("records"):
            outcomes.append(resolve_candidate(
                candidate,
                primary=primary_index,
                lower=lower_index,
                config=config,
                candidate_manifest=candidate_manifest,
                candle_manifest=candle_manifest,
            ))
    validate_outcomes(outcomes)
    return ResolutionResult(
        outcomes=tuple(outcomes),
        candidate_manifest=candidate_manifest,
        candle_manifest=candle_manifest,
        candidates_processed=len(candidates),
    )


TIMEFRAME_PADDING_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}
