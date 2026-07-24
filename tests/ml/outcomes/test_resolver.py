from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from ml.outcomes.config import OutcomeConfig
from ml.outcomes.resolver import CandleIndex, resolve_candidate


START = pd.Timestamp("2024-01-01T00:05:00Z")
MANIFEST = {"candidate_dataset_id": "candidates:test", "dataset_id": "candles:test",
            "checksum": "abc", "source_commit": "deadbeef"}


@pytest.fixture
def config(tmp_path: Path) -> OutcomeConfig:
    return OutcomeConfig(
        version="outcome_v1", candidates_root=tmp_path, candidate_manifest_path=tmp_path / "c.json",
        candles_root=tmp_path, candle_manifest_path=tmp_path / "d.json",
        outcomes_root=tmp_path / "out", reports_root=tmp_path / "reports",
        take_profit_fractions=(1 / 3, 1 / 3, 1 / 3),
        expiry_days={"M5": 1}, lower_timeframes={"M5": "M1"},
        require_complete_lower_candle_coverage=True,
        estimated_round_trip_cost_r=0.05,
        partition_columns=("strategy_name", "timeframe", "outcome_class", "year"),
        compression="zstd",
    )


def candidate(direction="long"):
    if direction == "long":
        entry, stop, targets = 100.0, 98.0, (102.0, 104.0, 106.0)
    else:
        entry, stop, targets = 100.0, 102.0, (98.0, 96.0, 94.0)
    return {
        "candidate_id": "candidate-1", "strategy_name": "test", "timeframe": "M5",
        "direction": direction, "candidate_timestamp": START, "entry_price": entry,
        "stop_loss": stop, "take_profit_1": targets[0], "take_profit_2": targets[1],
        "take_profit_3": targets[2],
    }


def candles(timeframe, rows):
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["symbol"] = "XAUUSD"
    frame["timeframe"] = timeframe
    return CandleIndex.from_frame(frame, timeframe)


def primary(rows):
    return candles("M5", [(START + pd.Timedelta(minutes=5 * i), *row) for i, row in enumerate(rows)])


def lower(rows):
    return candles("M1", [(START + pd.Timedelta(minutes=i), *row) for i, row in enumerate(rows)])


def resolve(config, primary_index, lower_index, item=None):
    return resolve_candidate(
        item or candidate(), primary=primary_index, lower=lower_index, config=config,
        candidate_manifest=MANIFEST,
        candle_manifest={"dataset_id": "candles:test", "checksum": "xyz"},
    )


def test_tp3_and_realized_r(config):
    result = resolve(config, primary([(100, 107, 99, 106)]), lower([]))
    assert result.outcome_class == "tp3_hit"
    assert (result.tp1_hit, result.tp2_hit, result.tp3_hit) == (True, True, True)
    assert result.gross_realized_r == pytest.approx(2.0)
    assert result.net_realized_r == pytest.approx(1.95)
    assert result.holding_seconds == 300
    assert result.mfe_r == pytest.approx(3.5)
    assert result.mae_r == pytest.approx(0.5)


def test_short_stop(config):
    result = resolve(config, primary([(100, 103, 99, 102)]), lower([]), candidate("short"))
    assert result.outcome_class == "sl_before_tp1"
    assert result.sl_hit and not result.tp1_hit
    assert result.gross_realized_r == pytest.approx(-1)


def test_lower_timeframe_orders_tp1_before_stop(config):
    parent = primary([(100, 103, 97, 98)])
    minutes = lower([
        (100, 102.5, 99, 102),
        (102, 102, 97, 98),
        (98, 99, 98, 99),
        (99, 100, 99, 100),
        (100, 101, 100, 101),
    ])
    result = resolve(config, parent, minutes)
    assert result.outcome_class == "tp1_then_sl"
    assert result.gross_realized_r == pytest.approx(-1 / 3)
    assert result.lower_timeframe_resolutions == 1
    assert result.conservative_fallbacks == 0


def test_incomplete_lower_data_falls_back_to_stop_first(config):
    result = resolve(config, primary([(100, 103, 97, 101)]), lower([
        (100, 102.5, 99, 102),
    ]))
    assert result.outcome_class == "sl_before_tp1"
    assert result.ambiguous_parent_candles == 1
    assert result.lower_timeframe_resolutions == 0
    assert result.conservative_fallbacks == 1


def test_same_lower_candle_tie_is_conservative(config):
    result = resolve(config, primary([(100, 103, 97, 101)]), lower([
        (100, 103, 97, 101), (101, 101, 100, 101), (101, 101, 100, 101),
        (101, 101, 100, 101), (101, 101, 100, 101),
    ]))
    assert result.outcome_class == "sl_before_tp1"
    assert result.conservative_fallbacks == 1


def test_expiry_marks_remaining_position_to_market(config):
    short_config = replace(config, expiry_days={"M5": 1})
    rows = [(100, 101, 99, 101)] * 288
    result = resolve(short_config, primary(rows), lower([]))
    assert result.outcome_class == "expired"
    assert result.expired
    assert result.gross_realized_r == pytest.approx(0.5)
    assert result.holding_seconds == 86400


def test_right_censored_has_no_realized_r(config):
    result = resolve(config, primary([(100, 101, 99, 100.5)]), lower([]))
    assert result.outcome_class == "right_censored"
    assert result.right_censored
    assert result.gross_realized_r is None
    assert result.net_realized_r is None


def test_candles_after_expiry_cannot_change_result(config):
    baseline = [(100, 101, 99, 100)] * 288
    first = resolve(config, primary(baseline), lower([]))
    second = resolve(config, primary(baseline + [(100, 110, 90, 100)]), lower([]))
    assert first.to_dict() == second.to_dict()
