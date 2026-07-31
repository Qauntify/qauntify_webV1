"""Unit tests for the rules-only backtester's fill simulation + stats."""
import pytest

from signals.backtest import (
    backtest_windowed,
    htf_trend_series,
    net_r_multiples,
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


# --- scale-out (multi-TP, fixed stop) model -------------------------------
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


def test_scaled_r_tp2_then_stopped_loses_the_last_third():
    """The stop never moves, so the unbooked third loses its full risk:
    1/3*1R + 1/3*2R - 1/3*1R = +0.667R."""
    assert scaled_r("long", 100, 98, TPS, reached=2, stopped=True) \
        == pytest.approx(2.0 / 3.0)


def test_scaled_r_full_loss_when_nothing_reached():
    assert scaled_r("long", 100, 98, TPS, reached=0, stopped=True) == -1.0


def test_scaled_r_tp1_then_stopped_is_a_net_loss():
    """Banking TP1 does not make a trade safe: 1/3*1R - 2/3*1R = -0.333R."""
    assert scaled_r("long", 100, 98, TPS, reached=1, stopped=True) \
        == pytest.approx(-1.0 / 3.0)


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


def test_net_r_subtracts_the_round_trip_cost():
    """BTCUSD is 20 bps of notional. Entry 100 with a stop 2 away means risk 2,
    so the cost in R is 0.0020 * 100 / 2 = 0.1R."""
    assert net_r_multiples("BTCUSD", [1.0], [100.0], [98.0]) == [0.9]


def test_cost_in_r_shrinks_as_the_stop_widens():
    """The same venue is far more expensive on a tight stop than a wide one —
    the reason a 0.5R scalp ladder needs its net number quoted."""
    tight = net_r_multiples("BTCUSD", [1.0], [100.0], [99.0])   # risk 1 → 0.2R
    wide = net_r_multiples("BTCUSD", [1.0], [100.0], [90.0])    # risk 10 → 0.02R
    assert tight[0] < wide[0]
    assert abs(tight[0] - 0.8) < 1e-9
    assert abs(wide[0] - 0.98) < 1e-9


def test_net_r_costs_a_loss_as_well_as_a_win():
    assert abs(net_r_multiples("BTCUSD", [-1.0], [100.0], [98.0])[0] + 1.1) < 1e-9


def test_net_r_is_empty_for_no_trades():
    assert net_r_multiples("BTCUSD", [], [], []) == []


# --- rolling-window replay -------------------------------------------------

def _wc(i, high, low, close=None):
    """Window candle: open_time matters for ordering, OHLC for fills."""
    c = close if close is not None else (high + low) / 2
    return Candle(open_time=i * 3_600_000, open=c, high=high, low=low,
                  close=c, volume=1.0)


def _never(*args, **kwargs):
    return None


def test_windowed_replay_finds_nothing_when_the_detector_never_fires():
    candles = [_wc(i, 101, 99) for i in range(300)]
    out = backtest_windowed(_never, "BTCUSD", candles, [1.0] * 300,
                            [None] * 300, window=200)
    assert out["gross"] == []
    assert out["net"] == []


def test_windowed_replay_only_shows_the_detector_its_window():
    """A detector must never see more history than the live scan would."""
    seen = []

    def _spy(symbol, candles, atr14, htf_trend=None):
        seen.append(len(candles))
        return None

    candles = [_wc(i, 101, 99) for i in range(400)]
    backtest_windowed(_spy, "BTCUSD", candles, [1.0] * 400, [None] * 400,
                      window=200)
    assert seen, "detector was never called"
    assert set(seen) == {200}


def test_windowed_replay_passes_the_aligned_htf_trend():
    """trends[i] must line up with the bar being evaluated, not the window."""
    from signals.models import CandidateSetup

    seen = []

    def _spy(symbol, candles, atr14, htf_trend=None):
        seen.append(htf_trend)
        return None

    n = 260
    candles = [_wc(i, 101, 99) for i in range(n)]
    trends = [f"t{i}" for i in range(n)]
    backtest_windowed(_spy, "BTCUSD", candles, [1.0] * n, trends, window=200)
    assert seen[0] == "t200"


def test_windowed_replay_scores_a_win_and_advances_past_it():
    from signals.models import CandidateSetup

    n = 260
    # Flat until the entry bar, then a rally that tags every target.
    candles = [_wc(i, 101, 99, 100) for i in range(n)]
    for i in range(201, n):
        candles[i] = _wc(i, 130, 99, 129)

    fired = []

    def _once(symbol, window, atr14, htf_trend=None):
        if fired:
            return None
        fired.append(True)
        return CandidateSetup("BTCUSD", "long", 100.0, 98.0, 102.0,
                              {}, take_profit_2=104.0, take_profit_3=106.0)

    out = backtest_windowed(_once, "BTCUSD", candles, [1.0] * n, [None] * n,
                            window=200)
    assert len(out["gross"]) == 1
    assert out["tp1_hits"] == 1
    assert out["tp3_hits"] == 1
    assert out["gross"][0] == 2.0          # (1R+2R+3R)/3 under the scale-out


def test_windowed_replay_charges_costs_to_the_net_series():
    from signals.models import CandidateSetup

    n = 260
    candles = [_wc(i, 101, 99, 100) for i in range(n)]
    for i in range(201, n):
        candles[i] = _wc(i, 130, 99, 129)

    fired = []

    def _once(symbol, window, atr14, htf_trend=None):
        if fired:
            return None
        fired.append(True)
        return CandidateSetup("BTCUSD", "long", 100.0, 98.0, 102.0,
                              {}, take_profit_2=104.0, take_profit_3=106.0)

    out = backtest_windowed(_once, "BTCUSD", candles, [1.0] * n, [None] * n,
                            window=200)
    assert out["net"][0] < out["gross"][0]


def test_windowed_replay_abandons_a_trade_past_max_hold():
    """Bounded hold mirrors live signal expiry and keeps the slice bounded."""
    from signals.models import CandidateSetup

    n = 400
    candles = [_wc(i, 100.5, 99.5, 100) for i in range(n)]  # never resolves

    def _always(symbol, window, atr14, htf_trend=None):
        return CandidateSetup("BTCUSD", "long", 100.0, 90.0, 110.0,
                              {}, take_profit_2=120.0, take_profit_3=130.0)

    out = backtest_windowed(_always, "BTCUSD", candles, [1.0] * n, [None] * n,
                            window=200, max_hold=10)
    # Unresolved trades book nothing and the replay still advances rather than
    # stalling on the same bar.
    assert len(out["gross"]) > 1
    assert out["tp1_hits"] == 0


def test_maker_tier_costs_less_than_the_default_taker_tier():
    """sr_limit rests an order rather than crossing the spread, so charging it
    the taker rate measures a strategy nobody would run."""
    from signals.r_model import MAKER_BPS

    taker = net_r_multiples("BTCUSD", [1.0], [100.0], [98.0])
    maker = net_r_multiples("BTCUSD", [1.0], [100.0], [98.0], bps=MAKER_BPS)
    assert maker[0] > taker[0]
    # 4 bps of 100 over a risk of 2 = 0.02R
    assert abs(maker[0] - 0.98) < 1e-9


def test_explicit_bps_of_zero_means_no_cost():
    assert net_r_multiples("BTCUSD", [1.0], [100.0], [98.0], bps=0.0) == [1.0]


# --- multi-timeframe replay -------------------------------------------------

def test_windowed_replay_passes_only_closed_htf_candles():
    """A 15m bar must never see a 1h candle that had not finished forming.
    Leaking the in-progress candle is lookahead, and it would flatter every
    multi-timeframe result in a way nothing downstream could detect."""
    hour = 3_600_000
    primary = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(400)]
    htf = [Candle(i * hour, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(20)]

    seen = []

    def spy(symbol, candles, atr14, htf_trend=None, h1_candles=None):
        seen.append((candles[-1].open_time,
                     h1_candles[-1].open_time if h1_candles else None))
        return None

    backtest_windowed(spy, "BTCUSD", primary, [2.0] * len(primary),
                      [None] * len(primary), window=200,
                      htf_candles=htf, htf_minutes=60)

    assert seen, "the detector was never called"
    for bar_time, htf_time in seen:
        assert htf_time is not None
        assert htf_time + hour <= bar_time, (
            f"htf candle at {htf_time} had not closed by {bar_time}")


def test_windowed_replay_without_htf_candles_omits_the_argument():
    """Single-timeframe detectors do not accept h1_candles. Passing it
    unconditionally would break every existing strategy."""
    primary = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(300)]
    calls = []

    def spy(symbol, candles, atr14, htf_trend=None):
        calls.append(1)
        return None

    backtest_windowed(spy, "BTCUSD", primary, [2.0] * len(primary),
                      [None] * len(primary), window=200)
    assert calls


def test_windowed_replay_skips_bars_with_no_closed_htf_candle():
    """Before the first HTF candle closes there is nothing causal to pass, so
    those bars produce no setup rather than an empty or future slice."""
    hour = 3_600_000
    # Every primary bar precedes the first HTF close.
    primary = [Candle(i * 900_000, 100.0, 101.0, 99.0, 100.0, 1.0)
               for i in range(300)]
    htf = [Candle(500 * hour, 100.0, 101.0, 99.0, 100.0, 1.0)]
    calls = []

    def spy(symbol, candles, atr14, htf_trend=None, h1_candles=None):
        calls.append(1)
        return None

    backtest_windowed(spy, "BTCUSD", primary, [2.0] * len(primary),
                      [None] * len(primary), window=200,
                      htf_candles=htf, htf_minutes=60)
    assert not calls
