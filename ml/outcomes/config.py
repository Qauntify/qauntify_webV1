"""Configuration loading for the offline outcome resolver."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ml.data.load_dataset import PROJECT_ROOT
from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.outcomes.schema import PARTITION_COLUMNS


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "ml" / "configs" / "outcome_v1.yaml"


class OutcomeConfigurationError(ValueError):
    """The versioned outcome configuration is missing or unsafe."""


@dataclass(frozen=True)
class OutcomeConfig:
    version: str
    candidates_root: Path
    candidate_manifest_path: Path
    candles_root: Path
    candle_manifest_path: Path
    outcomes_root: Path
    reports_root: Path
    take_profit_fractions: tuple[float, float, float]
    expiry_days: dict[str, int]
    lower_timeframes: dict[str, str]
    require_complete_lower_candle_coverage: bool
    estimated_round_trip_cost_r: float
    partition_columns: tuple[str, ...]
    compression: str


def _repo_path(value: object, field: str) -> Path:
    path = Path(str(value))
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise OutcomeConfigurationError(f"{field} must remain inside the repository") from exc
    return resolved


def load_outcome_config(path: Path = DEFAULT_CONFIG_PATH) -> OutcomeConfig:
    import yaml

    config_path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    raw = yaml.safe_load(config_path.read_text("utf-8"))
    if raw.get("version") != "outcome_v1":
        raise OutcomeConfigurationError("Only outcome_v1 is supported")
    if raw.get("entry", {}).get("policy") != "market_on_candidate_close":
        raise OutcomeConfigurationError("outcome_v1 requires market-on-close entry")
    if raw.get("position", {}).get("stop_policy") != "fixed_initial_stop":
        raise OutcomeConfigurationError("outcome_v1 requires a fixed initial stop")
    fractions = tuple(float(value) for value in raw["position"]["take_profit_fractions"])
    if len(fractions) != 3 or any(value <= 0 for value in fractions):
        raise OutcomeConfigurationError("Exactly three positive TP fractions are required")
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise OutcomeConfigurationError("TP fractions must sum to one")
    expiry_days = {str(key).upper(): int(value) for key, value in raw["expiry_days"].items()}
    lower = {
        str(key).upper(): str(value).upper()
        for key, value in raw["same_candle_resolution"]["lower_timeframes"].items()
    }
    if set(expiry_days) != set(lower):
        raise OutcomeConfigurationError("Expiry and lower-timeframe mappings must match")
    for timeframe, lower_timeframe in lower.items():
        if timeframe not in TIMEFRAME_SECONDS or lower_timeframe not in TIMEFRAME_SECONDS:
            raise OutcomeConfigurationError("Unknown timeframe in outcome policy")
        if TIMEFRAME_SECONDS[lower_timeframe] >= TIMEFRAME_SECONDS[timeframe]:
            raise OutcomeConfigurationError("Ambiguity timeframe must be lower than primary")
        if expiry_days[timeframe] <= 0:
            raise OutcomeConfigurationError("Expiry days must be positive")
    same_candle = raw["same_candle_resolution"]
    if same_candle.get("unresolved_policy") != "stop_first_conservative":
        raise OutcomeConfigurationError("outcome_v1 requires conservative unresolved ties")
    if same_candle.get("require_complete_lower_candle_coverage") is not True:
        raise OutcomeConfigurationError("outcome_v1 requires complete lower-candle coverage")
    if raw.get("fail_on_invalid_outcome") is not True:
        raise OutcomeConfigurationError("fail_on_invalid_outcome must be true")
    if raw.get("fail_on_duplicate_candidate_id") is not True:
        raise OutcomeConfigurationError("fail_on_duplicate_candidate_id must be true")
    partitions = tuple(raw.get("partition_columns", ()))
    if partitions != PARTITION_COLUMNS:
        raise OutcomeConfigurationError("Unexpected outcome partition columns")
    cost = float(raw["execution_cost"]["estimated_round_trip_cost_r"])
    if cost < 0:
        raise OutcomeConfigurationError("Execution cost cannot be negative")
    compression = str(raw.get("compression", "zstd")).lower()
    if compression not in {"zstd", "snappy"}:
        raise OutcomeConfigurationError("compression must be zstd or snappy")
    return OutcomeConfig(
        version="outcome_v1",
        candidates_root=_repo_path(raw["input"]["candidates_root"], "candidate root"),
        candidate_manifest_path=_repo_path(
            raw["input"]["candidate_manifest_path"], "candidate manifest",
        ),
        candles_root=_repo_path(raw["input"]["candles_root"], "candle root"),
        candle_manifest_path=_repo_path(
            raw["input"]["candle_manifest_path"], "candle manifest",
        ),
        outcomes_root=_repo_path(raw["output"]["outcomes_root"], "outcome root"),
        reports_root=_repo_path(raw["output"]["reports_root"], "report root"),
        take_profit_fractions=fractions,
        expiry_days=expiry_days,
        lower_timeframes=lower,
        require_complete_lower_candle_coverage=True,
        estimated_round_trip_cost_r=cost,
        partition_columns=partitions,
        compression=compression,
    )

