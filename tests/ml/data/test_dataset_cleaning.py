from dataclasses import replace

import pandas as pd
import pytest

from ml.data.clean_dataset import clean_dataset
from ml.data.validate_dataset import CANONICAL_COLUMNS, DatasetValidationError


def test_cleaning_sorts_normalizes_and_removes_exact_duplicates(
    valid_source_frame, dataset_config,
):
    source = pd.concat(
        [valid_source_frame, valid_source_frame.iloc[[0]]],
        ignore_index=True,
    )

    cleaned = clean_dataset(
        source,
        config=dataset_config,
        timeframe="M5",
        source_name="XAU_5m_data.jsonl",
    )

    assert tuple(cleaned.candles.columns) == CANONICAL_COLUMNS
    assert len(cleaned.candles) == 3
    assert cleaned.report.exact_duplicate_rows == 1
    assert cleaned.candles["timestamp"].is_monotonic_increasing
    assert set(cleaned.candles["symbol"]) == {"XAUUSD"}
    assert set(cleaned.candles["timeframe"]) == {"M5"}


def test_conflicting_duplicate_candles_always_fail(valid_source_frame, dataset_config):
    conflict = valid_source_frame.iloc[[0]].copy()
    conflict.loc[:, "Close"] = 2001.75
    source = pd.concat([valid_source_frame, conflict], ignore_index=True)

    with pytest.raises(DatasetValidationError, match="conflicting"):
        clean_dataset(
            source,
            config=dataset_config,
            timeframe="M5",
            source_name="XAU_5m_data.jsonl",
        )


def test_invalid_rows_fail_by_default_and_can_be_reported_then_excluded(
    valid_source_frame, dataset_config,
):
    valid_source_frame.loc[0, "High"] = 1990.0

    with pytest.raises(DatasetValidationError, match="invalid market rows"):
        clean_dataset(
            valid_source_frame,
            config=dataset_config,
            timeframe="M5",
            source_name="XAU_5m_data.jsonl",
        )

    reporting_config = replace(dataset_config, fail_on_invalid_ohlc=False)
    cleaned = clean_dataset(
        valid_source_frame,
        config=reporting_config,
        timeframe="M5",
        source_name="XAU_5m_data.jsonl",
    )
    assert len(cleaned.invalid_rows) == 1
    assert len(cleaned.candles) == 2


def test_source_timeframe_disagreement_fails(valid_source_frame, dataset_config):
    valid_source_frame["timeframe"] = "H1"

    with pytest.raises(DatasetValidationError, match="disagree"):
        clean_dataset(
            valid_source_frame,
            config=dataset_config,
            timeframe="M5",
            source_name="XAU_5m_data.jsonl",
        )
