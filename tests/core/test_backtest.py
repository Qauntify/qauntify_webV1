"""Unit tests for the rules-only backtester's fill simulation + stats."""
from signals.backtest import realized_r, simulate_trade, summarize
from signals.models import Candle


def _c(high, low):
    """Candle where only high/low matter for fill checks."""
    return Candle(open_time=0, open=(high + low) / 2, high=high, low=low,
                  close=(high + low) / 2, volume=1.0)


def test_long_win_when_tp_hit_before_sl():
    # entry 100, SL 98, TP 104. Bars drift up; bar 3 tags 104.
    future = [_c(101, 99.5), _c(102, 100), _c(104.5, 101)]
    assert simulate_trade("long", 100, 98, 104, future) == ("win", 3)


def test_long_loss_when_sl_hit_before_tp():
    future = [_c(101, 99.5), _c(101, 97.5), _c(104.5, 101)]
    assert simulate_trade("long", 100, 98, 104, future) == ("loss", 2)


def test_long_straddle_bar_counts_as_loss():
    """A single bar hitting both SL and TP is scored SL (conservative)."""
    future = [_c(105, 97)]  # spans 97..105 → both 98 and 104 touched
    assert simulate_trade("long", 100, 98, 104, future) == ("loss", 1)


def test_short_win_when_tp_hit_before_sl():
    # short entry 100, SL 102, TP 96. Bar 2 tags 96 low.
    future = [_c(101, 99), _c(100.5, 95.5)]
    assert simulate_trade("short", 100, 102, 96, future) == ("win", 2)


def test_short_loss_when_sl_hit_before_tp():
    future = [_c(102.5, 99)]  # high 102.5 >= SL 102
    assert simulate_trade("short", 100, 102, 96, future) == ("loss", 1)


def test_open_when_neither_level_hit():
    future = [_c(101, 99), _c(100.5, 99.5)]
    assert simulate_trade("long", 100, 98, 104, future) == ("open", 2)


def test_realized_r_win_is_reward_over_risk():
    # risk = 2 (100->98), reward = 4 (100->104) → +2R
    assert realized_r("long", 100, 98, 104, "win") == 2.0


def test_realized_r_loss_is_minus_one():
    assert realized_r("long", 100, 98, 104, "loss") == -1.0


def test_realized_r_open_is_zero():
    assert realized_r("long", 100, 98, 104, "open") == 0.0


def test_summarize_computes_winrate_and_expectancy():
    rs = [2.0, 2.0, -1.0, -1.0]  # 2 wins @+2R, 2 losses @-1R
    stats = summarize(rs)
    assert stats["trades"] == 4
    assert stats["wins"] == 2
    assert stats["win_rate"] == 0.5
    assert stats["expectancy_r"] == 0.5  # (2+2-1-1)/4


def test_summarize_empty_is_safe():
    stats = summarize([])
    assert stats["trades"] == 0
    assert stats["win_rate"] == 0.0
    assert stats["expectancy_r"] == 0.0
