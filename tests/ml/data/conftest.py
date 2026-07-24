from pathlib import Path

import pandas as pd
import pytest

from ml.data.load_dataset import DatasetConfig


@pytest.fixture
def valid_source_frame():
    return pd.DataFrame({
        "Date": [
            "2024.01.02 00:05",
            "2024.01.02 00:00",
            "2024.01.02 00:10",
        ],
        "Open": [2001.0, 2000.0, 2002.0],
        "High": [2002.0, 2001.0, 2003.0],
        "Low": [2000.0, 1999.0, 2001.0],
        "Close": [2001.5, 2000.5, 2002.5],
        "Volume": [12, 10, 0],
    })


@pytest.fixture
def dataset_config(tmp_path):
    project = tmp_path / "repo"
    return DatasetConfig(
        dataset_name="fixture/xauusd",
        revision="fixture-revision",
        symbol="XAUUSD",
        output_root=project / "ml/data/processed/cleaned_candles",
        report_root=project / "ml/data/reports",
        cache_root=project / "ml/data/raw/cache",
        partition_columns=("symbol", "timeframe", "year"),
        compression="zstd",
        remove_exact_duplicates=True,
        fail_on_invalid_ohlc=True,
        fail_on_unknown_timeframe=True,
        source_timeframes={"XAU_5m_data.jsonl": "M5"},
    )
