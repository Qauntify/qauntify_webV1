"""Safe deterministic cleaning for validated historical candles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ml.data.load_dataset import DatasetConfig
from ml.data.validate_dataset import (
    CANONICAL_COLUMNS,
    DatasetValidationError,
    ValidationReport,
    validate_dataset,
)

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class CleanedDataset:
    candles: "pd.DataFrame"
    invalid_rows: "pd.DataFrame"
    report: ValidationReport


def clean_dataset(
    source_frame: "pd.DataFrame",
    *,
    config: DatasetConfig,
    timeframe: str,
    source_name: str,
) -> CleanedDataset:
    """Apply only configured, deterministic transformations and fail safely."""
    outcome = validate_dataset(
        source_frame,
        symbol=config.symbol,
        timeframe=timeframe,
        source_name=source_name,
    )
    report = outcome.report
    invalid_rows = outcome.normalized.loc[outcome.invalid_mask].copy()

    if report.conflicting_duplicate_keys:
        raise DatasetValidationError(
            f"{source_name} contains {report.conflicting_duplicate_keys} conflicting "
            "duplicate candle keys"
        )
    if report.exact_duplicate_rows and not config.remove_exact_duplicates:
        raise DatasetValidationError(
            f"{source_name} contains exact duplicates and removal is disabled"
        )
    if config.fail_on_invalid_ohlc and outcome.invalid_mask.any():
        raise DatasetValidationError(
            f"{source_name} contains {int(outcome.invalid_mask.sum())} invalid market rows"
        )

    clean = outcome.normalized.loc[~outcome.invalid_mask].copy()
    if config.remove_exact_duplicates:
        clean = clean.loc[~clean.duplicated(keep="first")]
    clean = clean.sort_values(["symbol", "timeframe", "timestamp"], kind="mergesort")
    clean = clean.reset_index(drop=True)
    clean = clean.loc[:, CANONICAL_COLUMNS]
    for column in ("open", "high", "low", "close", "volume"):
        clean[column] = clean[column].astype("float64")
    return CleanedDataset(candles=clean, invalid_rows=invalid_rows, report=report)
