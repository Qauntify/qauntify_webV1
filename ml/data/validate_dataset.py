"""Reusable validation for historical multi-timeframe XAUUSD candles."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    import pandas as pd


CANONICAL_COLUMNS = (
    "timestamp", "symbol", "timeframe", "open", "high", "low", "close",
    "volume", "source",
)
KEY_COLUMNS = ("symbol", "timeframe", "timestamp")
PRICE_COLUMNS = ("open", "high", "low", "close")
REQUIRED_SOURCE_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D1": 24 * 60 * 60,
    "W1": 7 * 24 * 60 * 60,
    "MN1": None,
}

_COLUMN_ALIASES = {
    "date": "timestamp",
    "datetime": "timestamp",
    "date_time": "timestamp",
    "timestamp": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "vol": "volume",
    "tickvol": "volume",
    "tick_volume": "volume",
    "symbol": "symbol",
    "timeframe": "timeframe",
}

_TIMEFRAME_ALIASES = {
    "1M": "M1", "M1": "M1", "1MIN": "M1",
    "5M": "M5", "M5": "M5", "5MIN": "M5",
    "15M": "M15", "M15": "M15", "15MIN": "M15",
    "30M": "M30", "M30": "M30", "30MIN": "M30",
    "1H": "H1", "H1": "H1", "60M": "H1",
    "4H": "H4", "H4": "H4",
    "1D": "D1", "D1": "D1", "DAILY": "D1",
    "1W": "W1", "W1": "W1", "WEEKLY": "W1",
    "1MONTH": "MN1", "1MO": "MN1", "MN": "MN1", "MN1": "MN1",
}


class DatasetValidationError(ValueError):
    """Dataset schema or market data violates a fail-safe validation rule."""


@dataclass(frozen=True)
class TimeContinuityReport:
    expected_interval_seconds: int | None
    compared_intervals: int
    exact_intervals: int
    gaps: int
    expected_closure_gaps: int
    unexpected_gaps: int
    backward_timestamps: int
    maximum_gap_seconds: float | None
    estimated_missing_intervals: int | None


@dataclass(frozen=True)
class ValidationReport:
    symbol: str
    timeframe: str
    source: str
    source_rows: int
    fully_empty_rows: int
    columns: tuple[str, ...]
    dtypes: dict[str, str]
    unexpected_columns: tuple[str, ...]
    missing_values: dict[str, int]
    invalid_rows: int
    invalid_timestamp_rows: int
    invalid_numeric_rows: int
    invalid_ohlc_rows: int
    non_positive_price_rows: int
    negative_volume_rows: int
    zero_volume_rows: int
    exact_duplicate_rows: int
    duplicate_candle_keys: int
    conflicting_duplicate_keys: int
    timestamp_start: str | None
    timestamp_end: str | None
    chronological_in_source: bool
    memory_bytes: int
    continuity: TimeContinuityReport
    invalid_row_samples: tuple[dict, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationOutcome:
    normalized: "pd.DataFrame"
    invalid_mask: "pd.Series"
    exact_duplicate_mask: "pd.Series"
    conflicting_keys: "pd.DataFrame"
    report: ValidationReport


def _normalize_column_name(name: object) -> str:
    normalized = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    return _COLUMN_ALIASES.get(normalized, normalized)


def normalize_timeframe(value: object) -> str:
    """Normalize only explicitly supported timeframe spellings."""
    key = str(value).strip().upper().replace("_", "")
    try:
        return _TIMEFRAME_ALIASES[key]
    except KeyError as exc:
        raise DatasetValidationError(f"Unknown timeframe value: {value!r}") from exc


def normalize_source_schema(frame: "pd.DataFrame") -> tuple["pd.DataFrame", tuple[str, ...]]:
    """Normalize column names while reporting, not silently retaining, extras."""
    renamed = frame.rename(columns={name: _normalize_column_name(name) for name in frame.columns})
    duplicates = renamed.columns[renamed.columns.duplicated()].tolist()
    if duplicates:
        raise DatasetValidationError(
            f"Source columns collapse to duplicate names: {duplicates!r}"
        )
    missing = tuple(name for name in REQUIRED_SOURCE_COLUMNS if name not in renamed.columns)
    if missing:
        raise DatasetValidationError(f"Missing required source columns: {missing!r}")
    allowed = set(REQUIRED_SOURCE_COLUMNS) | {"symbol", "timeframe"}
    unexpected = tuple(name for name in renamed.columns if name not in allowed)
    return renamed, unexpected


def _is_expected_market_closure(previous, current) -> bool:
    """Classify common weekend closures without claiming every gap is harmless."""
    return previous.weekday() >= 4 or current.weekday() in (0, 6)


def _continuity(frame: "pd.DataFrame", timeframe: str) -> TimeContinuityReport:
    import pandas as pd

    expected = TIMEFRAME_SECONDS[timeframe]
    source_order = frame["timestamp"].dropna()
    backward = int((source_order.diff().dt.total_seconds() < 0).sum())
    ordered = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    ordered = ordered.drop_duplicates(subset=list(KEY_COLUMNS), keep="first")
    differences = ordered["timestamp"].diff().dt.total_seconds().dropna()

    if expected is None:
        return TimeContinuityReport(
            expected_interval_seconds=None,
            compared_intervals=len(differences),
            exact_intervals=0,
            gaps=0,
            expected_closure_gaps=0,
            unexpected_gaps=0,
            backward_timestamps=backward,
            maximum_gap_seconds=(float(differences.max()) if not differences.empty else None),
            estimated_missing_intervals=None,
        )

    gaps = differences[differences > expected]
    expected_closures = 0
    for index in gaps.index:
        position = ordered.index.get_loc(index)
        previous = ordered.iloc[position - 1]["timestamp"]
        current = ordered.iloc[position]["timestamp"]
        if _is_expected_market_closure(previous, current):
            expected_closures += 1
    estimated_missing = int(sum(max(int(delta // expected) - 1, 0) for delta in gaps))
    return TimeContinuityReport(
        expected_interval_seconds=expected,
        compared_intervals=len(differences),
        exact_intervals=int((differences == expected).sum()),
        gaps=len(gaps),
        expected_closure_gaps=expected_closures,
        unexpected_gaps=len(gaps) - expected_closures,
        backward_timestamps=backward,
        maximum_gap_seconds=(float(gaps.max()) if not gaps.empty else None),
        estimated_missing_intervals=estimated_missing,
    )


def validate_dataset(
    source_frame: "pd.DataFrame",
    *,
    symbol: str,
    timeframe: str,
    source_name: str,
) -> ValidationOutcome:
    """Normalize and inspect one trusted source-file/timeframe without cleaning it."""
    import numpy as np
    import pandas as pd

    canonical_timeframe = normalize_timeframe(timeframe)
    source_rows = len(source_frame)
    fully_empty = source_frame.isna().all(axis=1)
    working = source_frame.loc[~fully_empty].copy()
    normalized, unexpected = normalize_source_schema(working)

    if "symbol" in normalized:
        source_symbols = normalized["symbol"].dropna().astype(str).str.upper().unique()
        if any(value != symbol for value in source_symbols):
            raise DatasetValidationError(
                f"Source symbol values disagree with configured symbol {symbol!r}: "
                f"{source_symbols.tolist()!r}"
            )
    if "timeframe" in normalized:
        source_timeframes = {
            normalize_timeframe(value) for value in normalized["timeframe"].dropna().unique()
        }
        if source_timeframes != {canonical_timeframe}:
            raise DatasetValidationError(
                f"Source timeframe values disagree with filename mapping: "
                f"{source_timeframes!r} != {canonical_timeframe!r}"
            )

    result = pd.DataFrame(index=normalized.index)
    result["timestamp"] = pd.to_datetime(
        normalized["timestamp"], errors="coerce", utc=True,
    ).astype("datetime64[ns, UTC]")
    result["symbol"] = symbol
    result["timeframe"] = canonical_timeframe

    invalid_numeric = pd.Series(False, index=result.index)
    for column in (*PRICE_COLUMNS, "volume"):
        values = pd.to_numeric(normalized[column], errors="coerce")
        invalid_numeric |= values.isna() | ~np.isfinite(values)
        result[column] = values
    result["source"] = source_name

    invalid_timestamp = result["timestamp"].isna()
    non_positive = (result.loc[:, PRICE_COLUMNS] <= 0).any(axis=1)
    invalid_ohlc = (
        (result["high"] < result["open"])
        | (result["high"] < result["close"])
        | (result["high"] < result["low"])
        | (result["low"] > result["open"])
        | (result["low"] > result["close"])
    )
    negative_volume = result["volume"] < 0
    invalid_mask = (
        invalid_timestamp | invalid_numeric | non_positive | invalid_ohlc | negative_volume
    )

    exact_duplicate_mask = result.duplicated(keep="first")
    all_duplicate_key_mask = result.duplicated(subset=list(KEY_COLUMNS), keep=False)
    duplicate_key_count = len(
        result.loc[all_duplicate_key_mask, KEY_COLUMNS].drop_duplicates()
    )
    deduplicated = result.loc[~exact_duplicate_mask]
    duplicate_keys = deduplicated.duplicated(subset=list(KEY_COLUMNS), keep=False)
    conflicting = deduplicated.loc[duplicate_keys].sort_values(list(KEY_COLUMNS))
    conflicting_key_count = len(conflicting.loc[:, KEY_COLUMNS].drop_duplicates())

    valid_timestamps = result["timestamp"].dropna()
    samples = result.loc[invalid_mask].head(20).copy()
    if "timestamp" in samples:
        samples["timestamp"] = samples["timestamp"].astype(str)

    report = ValidationReport(
        symbol=symbol,
        timeframe=canonical_timeframe,
        source=source_name,
        source_rows=source_rows,
        fully_empty_rows=int(fully_empty.sum()),
        columns=tuple(str(column) for column in source_frame.columns),
        dtypes={str(name): str(dtype) for name, dtype in source_frame.dtypes.items()},
        unexpected_columns=unexpected,
        missing_values={
            str(name): int(value) for name, value in source_frame.isna().sum().items()
        },
        invalid_rows=int(invalid_mask.sum()),
        invalid_timestamp_rows=int(invalid_timestamp.sum()),
        invalid_numeric_rows=int(invalid_numeric.sum()),
        invalid_ohlc_rows=int(invalid_ohlc.sum()),
        non_positive_price_rows=int(non_positive.sum()),
        negative_volume_rows=int(negative_volume.sum()),
        zero_volume_rows=int((result["volume"] == 0).sum()),
        exact_duplicate_rows=int(exact_duplicate_mask.sum()),
        duplicate_candle_keys=duplicate_key_count,
        conflicting_duplicate_keys=conflicting_key_count,
        timestamp_start=(valid_timestamps.min().isoformat() if not valid_timestamps.empty else None),
        timestamp_end=(valid_timestamps.max().isoformat() if not valid_timestamps.empty else None),
        chronological_in_source=_continuity(result, canonical_timeframe).backward_timestamps == 0,
        memory_bytes=int(source_frame.memory_usage(index=True, deep=True).sum()),
        continuity=_continuity(result, canonical_timeframe),
        invalid_row_samples=tuple(samples.to_dict(orient="records")),
    )
    return ValidationOutcome(
        normalized=result,
        invalid_mask=invalid_mask,
        exact_duplicate_mask=exact_duplicate_mask,
        conflicting_keys=conflicting,
        report=report,
    )
