import pytest

from signals import r_model
from signals.calibration import (
    _bucket_stats,
    _confidence_bucket,
    _r_multiple,
    _strategy_of,
    calibration_report,
    summarize_by,
)


TP1_AT = "2026-07-01T01:00:00+00:00"
TP2_AT = "2026-07-01T02:00:00+00:00"

# A 1R stop on a 100-price symbol at 20 bps round-trip costs 0.10R. Tests that
# are about the R MODEL rather than the cost model use a zero-cost symbol so
# the two concerns stay separately readable.
FREE = "TESTUSD"


def _row(**overrides):
    row = {
        "symbol": "BTCUSDT", "timeframe": "1h", "direction": "long",
        "entry": 100.0, "stop_loss": 98.0, "take_profit": 102.0,
        "take_profit_2": 104.0, "take_profit_3": 106.0,
        "confidence": 80, "status": "tp_hit", "indicators": {},
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def _free_row(**overrides):
    """A row on a symbol with costs stubbed to zero (see monkeypatch below)."""
    return _row(symbol=FREE, **overrides)


@pytest.fixture(autouse=True)
def _zero_cost_test_symbol(monkeypatch):
    monkeypatch.setitem(r_model.COST_BPS, FREE, 0.0)


def test_r_multiple_full_run_to_tp3_is_two_r_not_three():
    # A third booked at 1R, 2R and 3R averages +2R. Crediting the full +3R
    # assumes the entire position rode to the last target, which is not the
    # trade the engine publishes.
    assert _r_multiple(_free_row(status="tp3_hit")) == pytest.approx(2.0)


def test_r_multiple_sl_before_any_target_is_minus_one():
    assert _r_multiple(_free_row(status="sl_hit")) == pytest.approx(-1.0)


def test_r_multiple_sl_after_tp1_books_the_first_third():
    # TP1 banked, stop moved to breakeven, remainder exits flat.
    assert _r_multiple(_free_row(status="sl_hit", tp1_hit_at=TP1_AT)) \
        == pytest.approx(1 / 3)


def test_r_multiple_sl_after_tp2_books_the_first_two_thirds():
    assert _r_multiple(_free_row(
        status="sl_hit", tp1_hit_at=TP1_AT, tp2_hit_at=TP2_AT,
    )) == pytest.approx(1.0)


def test_r_multiple_expired_after_tp1_keeps_what_it_banked():
    # Expiry is not a reset: a third was genuinely booked at TP1.
    assert _r_multiple(_free_row(status="expired", tp1_hit_at=TP1_AT)) \
        == pytest.approx(1 / 3)


def test_r_multiple_untouched_expiry_is_zero():
    assert _r_multiple(_free_row(status="expired")) == pytest.approx(0.0)


def test_r_multiple_legacy_single_target_row():
    # Old rows have only take_profit; one target means one 100% slice.
    row = _free_row(status="tp_hit", take_profit=104.0,
                    take_profit_2=None, take_profit_3=None)
    assert _r_multiple(row) == pytest.approx(2.0)


def test_r_multiple_short_direction_uses_absolute_distances():
    row = _free_row(status="tp3_hit", direction="short", entry=100.0,
                    stop_loss=102.0, take_profit=98.0,
                    take_profit_2=96.0, take_profit_3=94.0)
    assert _r_multiple(row) == pytest.approx(2.0)


def test_r_multiple_is_net_of_costs():
    # 20 bps round-trip on a 100-price entry with a 2-point stop = 0.10R.
    gross = _r_multiple(_free_row(status="tp3_hit"))
    net = _r_multiple(_row(symbol="BTCUSD", status="tp3_hit"))
    assert gross - net == pytest.approx(0.10)


def test_cost_scales_inversely_with_stop_distance():
    # The same venue is far more expensive on a tight stop — this is why the
    # 15m and 1h S/R variants measured so differently.
    wide = r_model.cost_r("BTCUSD", 100.0, 98.0)
    tight = r_model.cost_r("BTCUSD", 100.0, 99.0)
    assert tight == pytest.approx(2 * wide)


def test_bucket_stats_counts_wins_by_result_not_status():
    rows = [_free_row(status="tp3_hit"), _free_row(status="tp3_hit"),
            _free_row(status="sl_hit"), _free_row(status="expired")]
    stats = _bucket_stats(rows)
    assert stats["count"] == 4
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["breakeven"] == 1  # untouched expiry is neither
    assert stats["expired"] == 1
    assert stats["win_rate"] == 2 / 3


def test_bucket_stats_counts_partial_sl_as_win():
    rows = [
        _free_row(status="sl_hit", tp1_hit_at=TP1_AT),
        _free_row(status="sl_hit"),
    ]
    stats = _bucket_stats(rows)
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate"] == 0.5


def test_bucket_stats_costs_can_turn_a_banked_tp1_into_a_loss():
    # TP1-then-reverse books +0.333R gross. On a symbol whose round-trip cost
    # exceeds that, the trade is a loser — and must be counted as one.
    # 0.5-point stop → 20 bps of a 100 price costs 0.4R.
    row = _row(symbol="BTCUSD", status="sl_hit", tp1_hit_at=TP1_AT,
               entry=100.0, stop_loss=99.5,
               take_profit=100.5, take_profit_2=101.0, take_profit_3=101.5)
    stats = _bucket_stats([row])
    assert stats["avg_gross_r"] == pytest.approx(1 / 3)
    assert stats["avg_r"] < 0
    assert stats["losses"] == 1


def test_bucket_stats_win_rate_none_when_no_decided_outcomes():
    assert _bucket_stats([_free_row(status="expired")])["win_rate"] is None


def test_bucket_stats_empty_rows():
    assert _bucket_stats([]) == {
        "count": 0, "wins": 0, "losses": 0, "breakeven": 0, "expired": 0,
        "win_rate": None, "avg_r": None, "avg_gross_r": None,
        "avg_cost_r": None,
    }


def test_confidence_bucket_groups_by_ten():
    assert _confidence_bucket(82) == "80-89"
    assert _confidence_bucket(80) == "80-89"
    assert _confidence_bucket(79) == "70-79"
    assert _confidence_bucket(None) == "unknown"


def test_strategy_of_defaults_to_ema_cross():
    assert _strategy_of(_row(indicators={})) == "ema_cross"
    assert _strategy_of(_row(indicators={"strategy": "ict_smc"})) == "ict_smc"


def test_summarize_by_groups_rows():
    rows = [
        _row(symbol="BTCUSDT", status="tp_hit"),
        _row(symbol="BTCUSDT", status="sl_hit"),
        _row(symbol="ETHUSDT", status="tp_hit"),
    ]
    grouped = summarize_by(rows, lambda r: r["symbol"])
    assert grouped["BTCUSDT"]["count"] == 2
    assert grouped["ETHUSDT"]["count"] == 1


def test_calibration_report_has_all_groupings():
    rows = [
        _row(symbol="BTCUSDT", timeframe="1h", confidence=85,
            status="tp_hit", indicators={}),
        _row(symbol="ETHUSDT", timeframe="15m", confidence=60,
            status="sl_hit", indicators={"strategy": "ict_smc"}),
    ]
    report = calibration_report(rows)
    assert report["overall"]["count"] == 2
    assert set(report["by_strategy"]) == {"ema_cross", "ict_smc"}
    assert set(report["by_symbol"]) == {"BTCUSDT", "ETHUSDT"}
    assert set(report["by_timeframe"]) == {"1h", "15m"}
    assert set(report["by_confidence"]) == {"80-89", "60-69"}


def test_calibration_report_empty_rows():
    report = calibration_report([])
    assert report["overall"]["count"] == 0
    assert report["by_strategy"] == {}
