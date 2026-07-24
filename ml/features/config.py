"""Strict configuration for the offline candidate feature pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "ml" / "configs" / "feature_v1.yaml"
PARTITION_COLUMNS = ("strategy_name", "timeframe", "year")


class FeatureConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureConfig:
    version: str
    candidates_root: Path
    candidate_manifest_path: Path
    candles_root: Path
    candle_manifest_path: Path
    features_root: Path
    reports_root: Path
    volatility_lookback: int
    range_lookback: int
    structure_lookback: int
    fvg_lookback: int
    partition_columns: tuple[str, ...]
    compression: str


def _repo_path(value, field):
    path = Path(str(value))
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise FeatureConfigurationError(f"{field} must remain inside the repository") from exc
    return resolved


def load_feature_config(path: Path = DEFAULT_CONFIG_PATH) -> FeatureConfig:
    import yaml
    config_path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    raw = yaml.safe_load(config_path.read_text("utf-8"))
    if raw.get("version") != "feature_v1":
        raise FeatureConfigurationError("Only feature_v1 is supported")
    causal = raw.get("causality", {})
    if causal != {
        "boundary": "source_candle_close", "include_source_candle": True,
        "forbid_candles_at_or_after_candidate_timestamp": True,
    }:
        raise FeatureConfigurationError("feature_v1 causal boundary cannot be relaxed")
    partitions = tuple(raw.get("partition_columns", ()))
    if partitions != PARTITION_COLUMNS:
        raise FeatureConfigurationError("Unexpected feature partition columns")
    lookbacks = {key: int(value) for key, value in raw["lookbacks"].items()}
    if set(lookbacks) != {"volatility", "range", "structure", "fvg"}:
        raise FeatureConfigurationError("Unexpected lookback configuration")
    if any(value < 2 for value in lookbacks.values()):
        raise FeatureConfigurationError("Feature lookbacks must be at least two")
    if raw.get("fail_on_missing_candidate") is not True or raw.get("fail_on_duplicate_candidate_id") is not True:
        raise FeatureConfigurationError("Strict candidate coverage is required")
    compression = str(raw.get("compression", "zstd")).lower()
    if compression not in {"zstd", "snappy"}:
        raise FeatureConfigurationError("Unsupported compression")
    return FeatureConfig(
        version="feature_v1",
        candidates_root=_repo_path(raw["input"]["candidates_root"], "candidate root"),
        candidate_manifest_path=_repo_path(raw["input"]["candidate_manifest_path"], "candidate manifest"),
        candles_root=_repo_path(raw["input"]["candles_root"], "candle root"),
        candle_manifest_path=_repo_path(raw["input"]["candle_manifest_path"], "candle manifest"),
        features_root=_repo_path(raw["output"]["features_root"], "feature root"),
        reports_root=_repo_path(raw["output"]["reports_root"], "report root"),
        volatility_lookback=lookbacks["volatility"], range_lookback=lookbacks["range"],
        structure_lookback=lookbacks["structure"], fvg_lookback=lookbacks["fvg"],
        partition_columns=partitions, compression=compression,
    )

