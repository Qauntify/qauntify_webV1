"""Chronological, closed-candle historical strategy replay."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ml.data.load_dataset import PROJECT_ROOT
from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.replay.candidate_builder import build_candidate
from ml.replay.candidate_schema import CandidateRecord, CandidateValidationError, validate_candidates
from ml.replay.strategy_adapter import (
    SUPPORTED_STRATEGIES,
    calculate_causal_indicators,
    evaluate_strategy,
    PrefixView,
    strategy_version,
)
from signals.backtest import htf_trend_series
from signals.models import Candle


class ReplayConfigurationError(ValueError):
    """Replay configuration or source dataset is missing or unsafe."""


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    timeframe: str
    confluence_timeframe: str | None
    minimum_history: int


@dataclass(frozen=True)
class ReplayConfig:
    version: str
    cleaned_dataset_root: Path
    manifest_path: Path
    candidates_root: Path
    reports_root: Path
    symbols: tuple[str, ...]
    strategies: tuple[StrategyConfig, ...]
    closed_candles_only: bool
    fail_on_invalid_candidate: bool
    fail_on_duplicate_candidate_id: bool
    partition_columns: tuple[str, ...]
    compression: str


@dataclass(frozen=True)
class ReplayStats:
    candles_processed: int
    strategy_evaluations: int
    skipped_strategy_evaluations: int
    insufficient_history_occurrences: int
    invalid_candidate_count: int
    duplicate_candidate_count: int


@dataclass(frozen=True)
class ReplayResult:
    candidates: tuple[CandidateRecord, ...]
    stats: ReplayStats


def _repo_path(value: object, field: str) -> Path:
    path = Path(str(value))
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ReplayConfigurationError(f"{field} must remain inside the repository") from exc
    return resolved


def load_replay_config(path: Path) -> ReplayConfig:
    import yaml

    config_path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    raw = yaml.safe_load(config_path.read_text("utf-8"))
    strategies = tuple(StrategyConfig(
        name=str(item["name"]),
        timeframe=str(item["timeframe"]).upper(),
        confluence_timeframe=(
            str(item["confluence_timeframe"]).upper()
            if item.get("confluence_timeframe") else None
        ),
        minimum_history=int(item.get("minimum_history", 60)),
    ) for item in raw["strategies"])
    for strategy in strategies:
        if strategy.name not in SUPPORTED_STRATEGIES:
            raise ReplayConfigurationError(f"Unsupported strategy: {strategy.name!r}")
        if strategy.timeframe not in TIMEFRAME_SECONDS:
            raise ReplayConfigurationError(f"Unsupported timeframe: {strategy.timeframe!r}")
        if TIMEFRAME_SECONDS[strategy.timeframe] is None:
            raise ReplayConfigurationError("Monthly replay timing is not supported")
        if strategy.confluence_timeframe not in TIMEFRAME_SECONDS and strategy.confluence_timeframe is not None:
            raise ReplayConfigurationError(
                f"Unsupported confluence timeframe: {strategy.confluence_timeframe!r}"
            )
        if (strategy.confluence_timeframe is not None
                and TIMEFRAME_SECONDS[strategy.confluence_timeframe] is None):
            raise ReplayConfigurationError("Monthly confluence timing is not supported")
        if strategy.minimum_history < 2:
            raise ReplayConfigurationError("minimum_history must be at least 2")
    if raw.get("closed_candles_only") is not True:
        raise ReplayConfigurationError("closed_candles_only must be true")
    if raw.get("fail_on_invalid_candidate") is not True:
        raise ReplayConfigurationError("fail_on_invalid_candidate must be true")
    if raw.get("fail_on_duplicate_candidate_id") is not True:
        raise ReplayConfigurationError("fail_on_duplicate_candidate_id must be true")
    partitions = tuple(raw.get("partition_columns", ()))
    if partitions != ("symbol", "timeframe", "strategy_name", "year"):
        raise ReplayConfigurationError("Unexpected candidate partition columns")
    compression = str(raw.get("compression", "zstd")).lower()
    if compression not in {"zstd", "snappy"}:
        raise ReplayConfigurationError("compression must be zstd or snappy")
    symbols = tuple(str(value).upper() for value in raw["symbols"])
    if not symbols:
        raise ReplayConfigurationError("At least one symbol is required")
    if not strategies:
        raise ReplayConfigurationError("At least one strategy is required")
    return ReplayConfig(
        version=str(raw["version"]),
        cleaned_dataset_root=_repo_path(raw["input"]["cleaned_dataset_root"], "input root"),
        manifest_path=_repo_path(raw["input"]["manifest_path"], "manifest"),
        candidates_root=_repo_path(raw["output"]["candidates_root"], "candidate output"),
        reports_root=_repo_path(raw["output"]["reports_root"], "report output"),
        symbols=symbols,
        strategies=strategies,
        closed_candles_only=True,
        fail_on_invalid_candidate=bool(raw.get("fail_on_invalid_candidate", True)),
        fail_on_duplicate_candidate_id=bool(raw.get("fail_on_duplicate_candidate_id", True)),
        partition_columns=partitions,
        compression=compression,
    )


def validate_source_manifest(config: ReplayConfig) -> dict:
    if not config.manifest_path.is_file():
        raise ReplayConfigurationError(f"Dataset manifest is missing: {config.manifest_path}")
    manifest = json.loads(config.manifest_path.read_text("utf-8"))
    required = {"dataset_name", "checksum", "symbol", "timeframes", "canonical_columns"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ReplayConfigurationError(f"Dataset manifest fields are missing: {missing!r}")
    if not manifest["checksum"]:
        raise ReplayConfigurationError("Dataset manifest checksum is empty")
    required_columns = {"timestamp", "symbol", "timeframe", "open", "high", "low", "close"}
    if not required_columns.issubset(manifest["canonical_columns"]):
        raise ReplayConfigurationError("Dataset manifest lacks required candle columns")
    requested = {strategy.timeframe for strategy in config.strategies}
    requested.update(
        strategy.confluence_timeframe for strategy in config.strategies
        if strategy.confluence_timeframe
    )
    unsupported = sorted(requested - set(manifest["timeframes"]))
    if unsupported:
        raise ReplayConfigurationError(f"Requested timeframes are absent from manifest: {unsupported!r}")
    if set(config.symbols) != {str(manifest["symbol"]).upper()}:
        raise ReplayConfigurationError("Configured symbols disagree with the dataset manifest")
    manifest.setdefault("dataset_id", f"sha256:{manifest['checksum']}")
    return manifest


def load_candles(
    config: ReplayConfig,
    *,
    symbol: str,
    timeframe: str,
    start=None,
    end=None,
    limit: int | None = None,
):
    """Read one Hive partition with Arrow filters and validate candle ordering."""
    import pandas as pd
    import pyarrow.dataset as ds

    partition = config.cleaned_dataset_root / f"symbol={symbol}" / f"timeframe={timeframe}"
    if not partition.is_dir():
        raise ReplayConfigurationError(f"Requested candle partition is missing: {partition}")
    dataset = ds.dataset(
        config.cleaned_dataset_root,
        format="parquet",
        partitioning="hive",
        exclude_invalid_files=True,
    )
    expression = (ds.field("symbol") == symbol) & (ds.field("timeframe") == timeframe)
    if start is not None:
        start_time = pd.Timestamp(start)
        start_time = start_time.tz_localize("UTC") if start_time.tz is None else start_time.tz_convert("UTC")
        expression &= ds.field("timestamp") >= start_time.to_pydatetime()
    if end is not None:
        end_time = pd.Timestamp(end)
        end_time = end_time.tz_localize("UTC") if end_time.tz is None else end_time.tz_convert("UTC")
        expression &= ds.field("timestamp") <= end_time.to_pydatetime()
    required = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "source"]
    missing = sorted(set(required) - set(dataset.schema.names))
    if missing:
        raise ReplayConfigurationError(f"Required candle columns are missing: {missing!r}")
    frame = dataset.to_table(filter=expression, columns=required).to_pandas()
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame.duplicated(["symbol", "timeframe", "timestamp"]).any():
        raise ReplayConfigurationError("Duplicate candle keys remain in cleaned data")
    # Arrow makes no ordering guarantee across Hive fragments (for example,
    # year partitions), even though each cleaned fragment is chronological.
    # Establish the replay's required global order before applying a row cap.
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if limit is not None:
        frame = frame.head(limit).reset_index(drop=True)
    return frame


def frame_to_candles(frame) -> list[Candle]:
    return [Candle(
        open_time=int(row.timestamp.timestamp() * 1000),
        open=float(row.open), high=float(row.high), low=float(row.low),
        close=float(row.close), volume=float(row.volume),
    ) for row in frame.itertuples(index=False)]


def replay_candles(
    frame,
    *,
    strategy: StrategyConfig,
    manifest: Mapping,
    replay_config_version: str,
    htf_frame=None,
) -> ReplayResult:
    """Replay one strategy; every detector call receives only history through i."""
    if frame.empty:
        return ReplayResult((), ReplayStats(0, 0, 0, 0, 0, 0))
    if not frame["timestamp"].is_monotonic_increasing:
        raise ReplayConfigurationError("Candle timestamps are not ordered")
    if frame.duplicated(["symbol", "timeframe", "timestamp"]).any():
        raise ReplayConfigurationError("Duplicate candle keys remain in replay input")
    candles = frame_to_candles(frame)
    indicators = calculate_causal_indicators(candles)
    trends = [None] * len(candles)
    if strategy.confluence_timeframe:
        if htf_frame is None or htf_frame.empty:
            return ReplayResult((), ReplayStats(len(candles), 0, len(candles), 0, 0, 0))
        htf_candles = frame_to_candles(htf_frame)
        minutes = TIMEFRAME_SECONDS[strategy.confluence_timeframe] // 60
        trends = htf_trend_series(candles, htf_candles, minutes)

    candidates: list[CandidateRecord] = []
    invalid = evaluations = insufficient = 0
    duration = TIMEFRAME_SECONDS[strategy.timeframe]
    if duration is None:
        raise ReplayConfigurationError("Monthly candidate close time is unsupported")
    for index in range(len(candles)):
        if index + 1 < strategy.minimum_history:
            insufficient += 1
            continue
        evaluations += 1
        setup = evaluate_strategy(
            strategy.name,
            str(frame["symbol"].iat[0]),
            PrefixView(candles, index + 1),
            indicators,
            htf_trend=trends[index],
        )
        if setup is None:
            continue
        source_time = frame["timestamp"].iat[index]
        import pandas as pd
        decision_time = source_time + pd.Timedelta(seconds=duration)
        try:
            candidates.append(build_candidate(
                setup,
                candidate_timestamp=decision_time.isoformat(),
                source_candle_timestamp=source_time.isoformat(),
                timeframe=strategy.timeframe,
                strategy_name=strategy.name,
                strategy_version=strategy_version(strategy.name),
                dataset_id=str(manifest["dataset_id"]),
                dataset_checksum=str(manifest["checksum"]),
                replay_config_version=replay_config_version,
                source_commit=manifest.get("source_commit"),
            ))
        except (CandidateValidationError, ValueError):
            invalid += 1
            raise
    exact, duplicate_ids = validate_candidates(candidates)
    if exact or duplicate_ids:
        raise CandidateValidationError(
            f"Replay produced {exact} exact duplicates and {duplicate_ids} duplicate IDs"
        )
    return ReplayResult(tuple(candidates), ReplayStats(
        candles_processed=len(candles),
        strategy_evaluations=evaluations,
        skipped_strategy_evaluations=0,
        insufficient_history_occurrences=insufficient,
        invalid_candidate_count=invalid,
        duplicate_candidate_count=duplicate_ids,
    ))
