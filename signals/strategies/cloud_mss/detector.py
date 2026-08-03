"""Cloud + market structure shift.

The cloud is the band between a 1h Chandelier Exit and a 15m LWMA200 — the
shaded region in strategy_doc/TrendFollowingClaud.pine. It acts as a dynamic
support/resistance zone, and which side of price it sits on sets the bias:

  * PREMIUM  — cloud overhead, 1h Chandelier bearish. A rally into it is a sell.
  * DISCOUNT — cloud below, 1h Chandelier bullish. A drop into it is a buy.

Three ordered events make a setup: price wicks into the cloud and closes back
out (the rejection), then within a few bars closes through the pivot on the far
side of the pullback leg (the change of character), and that bar is the entry.

The Chandelier here uses `sma_atr`, MetaTrader's simple-average true range,
because the Pine does. `ce_lwma` uses the Wilder default and is untouched.
"""
from signals.indicators import chandelier_exit, lwma, sma_atr
from signals.models import CandidateSetup, take_profits_from_risk
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows

CE_ATR_PERIOD = 22
CE_MULTIPLIER = 4.5
CE_LOOKBACK = 22
MA_PERIOD = 200

# LWMA200 warm-up plus room for the structure window. _load_market_data fetches
# 260 and drops the forming bar, leaving 259 — comfortably above this. A test
# in tests/core/test_pipeline.py pins that relationship.
MIN_CANDLES = 230
# Chandelier needs max(period, lookback) + 1 bars before it emits a direction.
MIN_H1_CANDLES = max(CE_ATR_PERIOD, CE_LOOKBACK) + 2
# How many bars may sit between the cloud rejection and the structure break.
MAX_BARS_SINCE_TOUCH = 4
# Bars of 15m history scanned for the pivots that define the pullback leg.
STRUCTURE_WINDOW = 60
STOP_ATR_BUFFER = 0.5
# Reject setups whose stop is farther than this many ATRs from entry — same
# threshold as sr_zone and the BBMA detectors.
# 6.0, not the 2.5 that sr_zone and the BBMA detectors use. That is not a
# loosened guard, it is the only value consistent with where this strategy
# puts its stop. The cloud's far edge is a 1h Chandelier band sitting 4.5x the
# ONE-HOUR ATR from its extreme; expressed in the 15m ATR this divides by,
# that is 6-9 ATR before the pullback distance is added. Measured over 310,462
# real 15m bars the median setup needs 6.6 ATR, and a 2.5 cap rejected 99.4%
# of them - 35 setups in 8.87 years, which is silence, not selectivity.
#
# 6.0 was chosen from a measured sweep (4.0 / 6.0 / 8.0), not by taste: it is
# where trade count stops rising materially and net expectancy is least bad.
# It does NOT make the strategy profitable - see
# docs/cloud-mss-backtest-results.md.
MAX_STOP_ATR = 6.0


def _cloud(h1_candles, ma_value):
    """(trend, cloud_low, cloud_high) from the 1h Chandelier and the 15m MA.

    Returns None while the Chandelier is still warming up. This is the seam the
    rule tests monkeypatch — the only place 1h data enters the strategy.
    """
    highs = [c.high for c in h1_candles]
    lows = [c.low for c in h1_candles]
    closes = [c.close for c in h1_candles]
    long_stop, short_stop, direction = chandelier_exit(
        highs, lows, closes, period=CE_ATR_PERIOD, multiplier=CE_MULTIPLIER,
        lookback=CE_LOOKBACK, atr_fn=sma_atr,
    )
    trend = direction[-1]
    if trend is None:
        return None
    band = long_stop[-1] if trend == 1 else short_stop[-1]
    if band is None:
        return None
    return trend, min(band, ma_value), max(band, ma_value)


def _indicators(side, trend, cloud_low, cloud_high, ma_value, swing, atr_value,
                adx14, htf_trend):
    out = {
        "strategy": "cloud_mss",
        "side": side,
        "ce_trend": "up" if trend == 1 else "down",
        "cloud_low": cloud_low,
        "cloud_high": cloud_high,
        "ma200": ma_value,
        "choch_level": swing,
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _pivot_levels(candles, touch_index):
    """(swing_low, swing_high) from the bars strictly before the touch."""
    structure = candles[max(0, touch_index - STRUCTURE_WINDOW):touch_index]
    low_idx = pivot_lows(structure)
    high_idx = pivot_highs(structure)
    if not low_idx or not high_idx:
        return None, None
    return structure[low_idx[-1]].low, structure[high_idx[-1]].high


def _touch_indices(candles):
    """Candidate touch bars, most recent first."""
    n = len(candles)
    return range(n - 2, max(-1, n - 2 - MAX_BARS_SINCE_TOUCH), -1)


def detect_setup(symbol, candles, atr14, h1_candles=None, adx14=None,
                 htf_trend=None):
    """Return a CandidateSetup on a confirmed cloud rejection, else None."""
    if len(candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    if not h1_candles or len(h1_candles) < MIN_H1_CANDLES:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    ma = lwma([c.close for c in candles], MA_PERIOD)
    if ma[-1] is None:
        return None
    cloud = _cloud(h1_candles, ma[-1])
    if cloud is None:
        return None
    trend, cloud_low, cloud_high = cloud

    bar = candles[-1]
    n = len(candles)

    # --- premium: cloud overhead, sell the rally into it --------------------
    if trend == -1 and bar.close < cloud_low:
        for t in _touch_indices(candles):
            touch = candles[t]
            if not (touch.high >= cloud_low and touch.close < cloud_low):
                continue
            swing_low, swing_high = _pivot_levels(candles, t)
            if swing_low is None:
                continue
            between = candles[t + 1:n - 1]
            # A close back above the pre-touch swing high is the pullback
            # resolving as continuation — the setup is void, not pending.
            if any(c.close > swing_high for c in between):
                continue
            # If an earlier bar already broke the low, that bar was the CHoCH.
            if any(c.close < swing_low for c in between):
                continue
            if bar.close >= swing_low:
                continue
            stop = cloud_high + STOP_ATR_BUFFER * atr_value
            if stop <= bar.close:
                continue
            if abs(bar.close - stop) / atr_value > MAX_STOP_ATR:
                continue
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "short")
            return CandidateSetup(
                symbol, "short", bar.close, stop, tp1,
                _indicators("premium", trend, cloud_low, cloud_high, ma[-1],
                            swing_low, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    # --- discount: cloud below, buy the drop into it ------------------------
    if trend == 1 and bar.close > cloud_high:
        for t in _touch_indices(candles):
            touch = candles[t]
            if not (touch.low <= cloud_high and touch.close > cloud_high):
                continue
            swing_low, swing_high = _pivot_levels(candles, t)
            if swing_high is None:
                continue
            between = candles[t + 1:n - 1]
            if any(c.close < swing_low for c in between):
                continue
            if any(c.close > swing_high for c in between):
                continue
            if bar.close <= swing_high:
                continue
            stop = cloud_low - STOP_ATR_BUFFER * atr_value
            if stop >= bar.close:
                continue
            if abs(bar.close - stop) / atr_value > MAX_STOP_ATR:
                continue
            tp1, tp2, tp3 = take_profits_from_risk(bar.close, stop, "long")
            return CandidateSetup(
                symbol, "long", bar.close, stop, tp1,
                _indicators("discount", trend, cloud_low, cloud_high, ma[-1],
                            swing_high, atr_value, adx14, htf_trend),
                take_profit_2=tp2, take_profit_3=tp3,
            )

    return None
