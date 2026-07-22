"""Unit tests for the rules-only backtester's fill simulation + stats."""
from signals.backtest import (
    htf_trend_series,
    realized_r,
    scaled_r,
    simulate_scaled,
    simulate_trade,
    summarize,
)
from signals.models import Candle


def _c(high, low):
    """Candle where only high/low matter for fill checks."""
    return Candle(open_time=0, open=(high + low) / 2, high=high, low=low,
                  close=(high + low) / 2, volume=1.0)


def _tc(t, close):
    """Timed candle for HTF-alignment tests (open_time in ms, given close)."""
    return Candle(open_time=t, open=close, high=close + 1, low=close - 1,
                  close=close, volume=1.0)


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


# --- scale-out (multi-TP + breakeven) model -------------------------------
# entry 100, stop 98 (risk 2), tps at 1R/2R/3R = 102/104/106.
TPS = [102.0, 104.0, 106.0]


def test_scaled_reaches_tp3_before_stop():
    future = [_c(102.5, 100), _c(104.5, 101), _c(106.5, 103)]
    assert simulate_scaled("long", 100, 98, TPS, future) == (3, False, 3)


def test_scaled_reaches_tp2_then_stopped():
    future = [_c(104.5, 100), _c(101, 97.5)]  # tp1+tp2 on bar 1, stop on bar 2
    assert simulate_scaled("long", 100, 98, TPS, future) == (2, True, 2)


def test_scaled_stop_first_reaches_nothing():
    future = [_c(101, 97.5)]
    assert simulate_scaled("long", 100, 98, TPS, future) == (0, True, 1)


def test_scaled_straddle_is_stop_no_tp_counted():
    future = [_c(107, 97)]  # spans stop 98 and all TPs; stop wins → nothing reached
    assert simulate_scaled("long", 100, 98, TPS, future) == (0, True, 1)


def test_scaled_expires_at_tp1():
    future = [_c(102.5, 100), _c(101.5, 100.5)]  # tp1 then chop, no stop/tp2
    assert simulate_scaled("long", 100, 98, TPS, future) == (1, False, 2)


def test_scaled_short_reaches_tp3():
    # short entry 100, stop 102, tps 98/96/94
    future = [_c(100, 93.5)]
    assert simulate_scaled("short", 100, 102, [98.0, 96.0, 94.0], future) == (3, False, 1)


def test_scaled_r_full_tp3_is_two_r():
    # thirds of 1R+2R+3R = (1+2+3)/3 = 2.0R
    assert scaled_r("long", 100, 98, TPS, reached=3, stopped=False) == 2.0


def test_scaled_r_tp2_then_breakeven_stop():
    # 1/3*1R + 1/3*2R + 1/3 at breakeven(0) = 1.0R
    assert scaled_r("long", 100, 98, TPS, reached=2, stopped=True) == 1.0


def test_scaled_r_full_loss_when_nothing_reached():
    assert scaled_r("long", 100, 98, TPS, reached=0, stopped=True) == -1.0


def test_scaled_r_tp1_then_expire_books_first_third():
    assert abs(scaled_r("long", 100, 98, TPS, reached=1, stopped=False) - (1.0 / 3.0)) < 1e-9


# --- higher-timeframe trend alignment -------------------------------------
def test_htf_trend_series_uses_last_closed_htf_bar():
    hour = 60 * 60 * 1000
    htf_min = 240  # 4h
    step = htf_min * 60 * 1000
    # 30 rising then flat: EMA9 > EMA21 (uptrend) once warm.
    htf = [_tc(i * step, 100 + i) for i in range(30)]
    # A primary bar just after the 29th htf bar closes should read "up".
    primary_time = 29 * step + step + hour  # after htf[29] has closed
    primary = [_tc(primary_time, 200)]
    trends = htf_trend_series(primary, htf, htf_min)
    assert trends == ["up"]


def test_htf_trend_series_none_before_any_htf_close():
    step = 240 * 60 * 1000
    htf = [_tc(i * step, 100 + i) for i in range(30)]
    primary = [_tc(0, 100)]  # before the first htf bar has even closed
    assert htf_trend_series(primary, htf, 240) == [None]
