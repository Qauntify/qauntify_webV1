import pandas as pd
import pytest

from ml.data.validate_dataset import (
    DatasetValidationError,
    normalize_timeframe,
    validate_dataset,
)


def _validate(frame, timeframe="M5"):
    return validate_dataset(
        frame,
        symbol="XAUUSD",
        timeframe=timeframe,
        source_name="XAU_5m_data.jsonl",
    )


def test_valid_rows_parse_as_utc_and_report_source_order(valid_source_frame):
    outcome = _validate(valid_source_frame)

    assert outcome.report.invalid_rows == 0
    assert outcome.report.zero_volume_rows == 1
    assert outcome.report.chronological_in_source is False
    assert outcome.report.continuity.expected_interval_seconds == 300
    assert outcome.report.continuity.gaps == 0
    assert str(outcome.normalized["timestamp"].dtype) == "datetime64[ns, UTC]"


@pytest.mark.parametrize(
    ("column", "value", "report_field"),
    [
        ("High", 1990.0, "invalid_ohlc_rows"),
        ("Low", 2010.0, "invalid_ohlc_rows"),
        ("Open", 0.0, "non_positive_price_rows"),
        ("Volume", -1.0, "negative_volume_rows"),
    ],
)
def test_invalid_market_values_are_reported(
    valid_source_frame, column, value, report_field,
):
    valid_source_frame.loc[0, column] = value

    outcome = _validate(valid_source_frame)

    assert outcome.report.invalid_rows == 1
    assert getattr(outcome.report, report_field) == 1
    assert len(outcome.report.invalid_row_samples) == 1


def test_exact_and_conflicting_duplicates_are_separate(valid_source_frame):
    exact = valid_source_frame.iloc[[0]].copy()
    conflict = valid_source_frame.iloc[[1]].copy()
    conflict.loc[:, "Close"] = 2000.75
    combined = pd.concat([valid_source_frame, exact, conflict], ignore_index=True)

    outcome = _validate(combined)

    assert outcome.report.exact_duplicate_rows == 1
    assert outcome.report.duplicate_candle_keys == 2
    assert outcome.report.conflicting_duplicate_keys == 1
    assert len(outcome.conflicting_keys) == 2


def test_gap_detection_does_not_create_candles(valid_source_frame):
    valid_source_frame.loc[2, "Date"] = "2024.01.02 00:20"

    outcome = _validate(valid_source_frame)

    assert outcome.report.continuity.gaps == 1
    assert outcome.report.continuity.estimated_missing_intervals == 2
    assert len(outcome.normalized) == len(valid_source_frame)


@pytest.mark.parametrize("value", [None, "M2", "unknown"])
def test_unknown_or_missing_timeframe_fails(value):
    with pytest.raises(DatasetValidationError, match="Unknown timeframe"):
        normalize_timeframe(value)


def test_timeframe_normalization_is_explicit():
    assert normalize_timeframe("1m") == "M1"
    assert normalize_timeframe("15min") == "M15"
    assert normalize_timeframe("1Month") == "MN1"
