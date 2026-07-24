import pandas as pd
import pytest

from ml.replay.replay_engine import StrategyConfig
from signals.models import CandidateSetup


@pytest.fixture
def candle_frame():
    timestamps = pd.date_range("2024-01-02", periods=80, freq="5min", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "open": [2000.0 + index * 0.1 for index in range(80)],
        "high": [2001.0 + index * 0.1 for index in range(80)],
        "low": [1999.0 + index * 0.1 for index in range(80)],
        "close": [2000.5 + index * 0.1 for index in range(80)],
        "volume": 10.0,
        "source": "fixture.parquet",
    })


@pytest.fixture
def strategy_config():
    return StrategyConfig("ict_fvg", "M5", None, 10)


@pytest.fixture
def source_manifest():
    return {
        "dataset_id": "dataset-fixture",
        "checksum": "abc123",
        "source_commit": "commit-fixture",
    }


@pytest.fixture
def long_setup():
    return CandidateSetup(
        "XAUUSD", "long", 2000.0, 1998.0, 2002.0,
        {"strategy": "ict_fvg", "structure": "bullish_choch_fvg"},
        take_profit_2=2004.0, take_profit_3=2006.0,
    )


@pytest.fixture
def short_setup():
    return CandidateSetup(
        "XAUUSD", "short", 2000.0, 2002.0, 1998.0,
        {"strategy": "ict_fvg", "structure": "bearish_choch_fvg"},
        take_profit_2=1996.0, take_profit_3=1994.0,
    )

