from pathlib import Path
from types import SimpleNamespace

import pytest

from ml.features.calculator import calculate_feature_row
from ml.features.config import FeatureConfig
from ml.features.schema import ALL_COLUMNS, validate_feature
from ml.replay.strategy_adapter import calculate_causal_indicators
from signals.models import Candle


def config(tmp_path):
    return FeatureConfig("feature_v1", tmp_path, tmp_path / "c.json", tmp_path, tmp_path / "d.json",
                         tmp_path / "out", tmp_path / "reports", 20, 20, 120, 20,
                         ("strategy_name", "timeframe", "year"), "zstd")


def candle(index, close=None):
    price = 100 + index * 0.1 if close is None else close
    return Candle(1_704_067_200_000 + index * 300_000, price - .05, price + .3, price - .3, price, 10 + index)


def candidate(candles):
    last = candles[-1]
    return {"candidate_id": "id-1", "candidate_timestamp": "2024-01-01T05:00:00+00:00",
            "source_candle_timestamp": "2024-01-01T04:55:00+00:00", "symbol": "XAUUSD",
            "strategy_name": "ict_fvg", "timeframe": "M5", "direction": "long",
            "entry_price": last.close, "stop_loss": last.close - 1,
            "take_profit_1": last.close + .5, "take_profit_2": last.close + 1,
            "take_profit_3": last.close + 1.5}


def calculate(monkeypatch, tmp_path, candles, index):
    item = candidate(candles[:index + 1])
    setup = SimpleNamespace(direction="long", entry=item["entry_price"], stop_loss=item["stop_loss"],
                            indicators={"structure": "bullish_choch_fvg", "fvg_bottom": 103.0,
                                        "fvg_top": 103.2, "sweep_low": 102.0, "choch_level": 103.5})
    monkeypatch.setattr("ml.features.calculator.evaluate_strategy", lambda *args, **kwargs: setup)
    return calculate_feature_row(item, candles=candles, indicators=calculate_causal_indicators(candles),
                                 index=index, htf_trend="up", config=config(tmp_path),
                                 candidate_manifest={"candidate_dataset_id": "cid", "checksum": "cc", "source_commit": "git"},
                                 candle_manifest={"dataset_id": "did", "checksum": "dc"})


def test_feature_row_has_fixed_valid_schema(monkeypatch, tmp_path):
    row = calculate(monkeypatch, tmp_path, [candle(i) for i in range(60)], 59)
    validate_feature(row)
    assert set(row) == set(ALL_COLUMNS)
    assert row["ema9"] is not None and row["atr14"] is not None and row["rsi14"] is not None
    assert row["strategy_fvg_width_atr"] > 0
    assert not any(name in row for name in ("outcome", "label", "realized_r"))


def test_appending_and_mutating_future_candles_cannot_change_features(monkeypatch, tmp_path):
    history = [candle(i) for i in range(60)]
    baseline = calculate(monkeypatch, tmp_path, history, 59)
    future = history + [candle(60, 10000), candle(61, 1)]
    rerun = calculate(monkeypatch, tmp_path, future, 59)
    assert baseline == rerun


def test_detector_parity_is_required(monkeypatch, tmp_path):
    candles = [candle(i) for i in range(60)]
    monkeypatch.setattr("ml.features.calculator.evaluate_strategy", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="parity failed"):
        calculate_feature_row(candidate(candles), candles=candles, indicators=calculate_causal_indicators(candles),
                              index=59, htf_trend=None, config=config(tmp_path),
                              candidate_manifest={"candidate_dataset_id": "cid", "checksum": "cc"},
                              candle_manifest={"dataset_id": "did", "checksum": "dc"})
