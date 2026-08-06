"""Taught BBMA (Oma Ally) — MTF bias + cycle entries.

Unlike the older standalone detectors, this follows the web-consensus SOP:

* H4 bias from Mid BB + EMA50 (both must agree; neutral = no trade)
* Primary: H1 re-entry after CSAK/CSM into MA5/10 + Mid BB zone
* Secondary: Extreme (MA5 outside BB) → MHV (touch band, close inside) → confirm

Stack: BB 20/2, LWMA5/10 H/L, EMA50 (same as stack.py).
"""
from __future__ import annotations

from signals.models import CandidateSetup
from signals.strategies.bbma.extreme import EXTREME_LOOKBACK
from signals.strategies.bbma.reentry import SIGNAL_LOOKBACK, _arming_signal
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
    structural_targets,
)

REENTRY_MIN_R = 0.0
EXTREME_MIN_R = 0.0
# How many H1 bars after an Extreme escape to look for MHV + confirm.
MHV_LOOKBACK = 8


def htf_bias_mid_ema50(h4_candles) -> str | None:
    """Return 'up', 'down', or None when Mid BB and EMA50 disagree / cold."""
    if len(h4_candles) < MIN_CANDLES:
        return None
    stack = bbma_stack(h4_candles)
    if not stack_ready(stack):
        return None
    close = h4_candles[-1].close
    mid = stack["mid"][-1]
    ema50 = stack["ema50"][-1]
    if close > mid and close > ema50:
        return "up"
    if close < mid and close < ema50:
        return "down"
    return None


def _ind(strategy, side, stack, atr_value, htf_bias, **extra):
    out = {
        "strategy": strategy,
        "side": side,
        "doctrine": "taught_mtf",
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "ma10h": stack["ma10h"][-1],
        "ma10l": stack["ma10l"][-1],
        "ema50": stack["ema50"][-1],
        "atr": atr_value,
        "htf_bias": htf_bias,
        **extra,
    }
    return out


def detect_reentry(symbol, h1_candles, atr14, htf_bias: str | None):
    """H1 re-entry with taught H4 Mid+EMA50 bias (must match direction)."""
    if htf_bias not in ("up", "down"):
        return None
    if len(h1_candles) < MIN_CANDLES + 1 or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(h1_candles)
    if not stack_ready(stack):
        return None

    n = len(h1_candles)
    pull, bar = h1_candles[-2], h1_candles[-1]
    window = range(max(0, n - 2 - SIGNAL_LOOKBACK), n - 2)

    ma5l_p, ma10l_p, mid_p = (
        stack["ma5l"][-2], stack["ma10l"][-2], stack["mid"][-2],
    )
    ma5h_p, ma10h_p = stack["ma5h"][-2], stack["ma10h"][-2]
    ma10l, ma10h, mid = stack["ma10l"][-1], stack["ma10h"][-1], stack["mid"][-1]
    if None in (ma5l_p, ma10l_p, mid_p, ma5h_p, ma10h_p, ma10l, ma10h, mid):
        return None

    if htf_bias == "up":
        trigger = _arming_signal(h1_candles, stack, window, up=True)
        if not (
            trigger
            and pull.low <= ma5l_p
            and pull.close > ma10l_p
            and pull.close > mid_p
            and bar.close > pull.close
            and bar.close > ma10l
            and bar.close > mid
        ):
            return None
        entry = bar.close
        stop = min(pull.low, bar.low, ma10l) - STOP_ATR_BUFFER * atr_value
        if not (stop < entry and risk_ok(entry, stop, atr_value)):
            return None
        tps = structural_targets(
            entry, stop, "long",
            max(stack["ma5h"][-1], ma10h),
            min_r=REENTRY_MIN_R,
        )
        if not tps:
            return None
        return CandidateSetup(
            symbol, "long", entry, stop, tps[0],
            _ind("bbma_reentry", "support", stack, atr_value, htf_bias,
                 trigger=trigger, source="taught"),
            take_profit_2=tps[1], take_profit_3=tps[2],
        )

    trigger = _arming_signal(h1_candles, stack, window, up=False)
    if not (
        trigger
        and pull.high >= ma5h_p
        and pull.close < ma10h_p
        and pull.close < mid_p
        and bar.close < pull.close
        and bar.close < ma10h
        and bar.close < mid
    ):
        return None
    entry = bar.close
    stop = max(pull.high, bar.high, ma10h) + STOP_ATR_BUFFER * atr_value
    if not (stop > entry and risk_ok(entry, stop, atr_value)):
        return None
    tps = structural_targets(
        entry, stop, "short",
        min(stack["ma5l"][-1], ma10l),
        min_r=REENTRY_MIN_R,
    )
    if not tps:
        return None
    return CandidateSetup(
        symbol, "short", entry, stop, tps[0],
        _ind("bbma_reentry", "resistance", stack, atr_value, htf_bias,
             trigger=trigger, source="taught"),
        take_profit_2=tps[1], take_profit_3=tps[2],
    )


def _escaped(ma_series, band_series, window, above: bool) -> bool:
    for i in window:
        ma, band = ma_series[i], band_series[i]
        if ma is None or band is None:
            continue
        if (ma > band) if above else (ma < band):
            return True
    return False


def _mhv_index(candles, stack, start: int, end: int, sell: bool) -> int | None:
    """Newest MHV bar in [start, end]: wick to outer BB, close back inside."""
    for i in range(end, start - 1, -1):
        upper, lower, mid = stack["upper"][i], stack["lower"][i], stack["mid"][i]
        if None in (upper, lower, mid):
            continue
        bar = candles[i]
        if sell:
            # Exhaustion at top: touch/pierce upper, close inside below it.
            if bar.high >= upper and bar.close < upper:
                return i
        else:
            if bar.low <= lower and bar.close > lower:
                return i
    return None


def detect_extreme_mhv(symbol, h1_candles, atr14, htf_bias: str | None):
    """Extreme → MHV → confirm. Counter-trend scalp; soft H4 filter only.

    Allows trades against neutral HTF; blocks only when HTF strongly agrees
    with the spike (no fading a strong H4 trend into the Extreme).
    """
    if len(h1_candles) < MIN_CANDLES or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(h1_candles)
    if not stack_ready(stack):
        return None

    n = len(h1_candles)
    bar = h1_candles[-1]
    escape_window = range(max(0, n - EXTREME_LOOKBACK), n)
    mhv_start = max(0, n - MHV_LOOKBACK - 1)

    # --- short Extreme (fade a high spike) --------------------------------
    if htf_bias != "up":  # don't fade into a strong H4 uptrend
        if _escaped(stack["ma5h"], stack["upper"], escape_window, above=True):
            mhv_i = _mhv_index(h1_candles, stack, mhv_start, n - 2, sell=True)
            ma5h = stack["ma5h"][-1]
            if (
                mhv_i is not None
                and ma5h is not None
                and bar.close < bar.open
                and bar.high >= ma5h
                and bar.close < ma5h
            ):
                entry = bar.close
                spike_high = max(c.high for c in h1_candles[mhv_i:n])
                stop = spike_high + STOP_ATR_BUFFER * atr_value
                if stop > entry and risk_ok(entry, stop, atr_value):
                    tps = structural_targets(
                        entry, stop, "short",
                        max(stack["ma5l"][-1], stack["ma10l"][-1]),
                        min_r=EXTREME_MIN_R,
                    )
                    if tps:
                        return CandidateSetup(
                            symbol, "short", entry, stop, tps[0],
                            _ind("bbma_extreme", "resistance", stack, atr_value,
                                 htf_bias, mhv_bar=mhv_i, source="taught"),
                            take_profit_2=tps[1], take_profit_3=tps[2],
                        )

    # --- long Extreme (fade a low spike) ----------------------------------
    if htf_bias != "down":
        if _escaped(stack["ma5l"], stack["lower"], escape_window, above=False):
            mhv_i = _mhv_index(h1_candles, stack, mhv_start, n - 2, sell=False)
            ma5l = stack["ma5l"][-1]
            if (
                mhv_i is not None
                and ma5l is not None
                and bar.close > bar.open
                and bar.low <= ma5l
                and bar.close > ma5l
            ):
                entry = bar.close
                spike_low = min(c.low for c in h1_candles[mhv_i:n])
                stop = spike_low - STOP_ATR_BUFFER * atr_value
                if stop < entry and risk_ok(entry, stop, atr_value):
                    tps = structural_targets(
                        entry, stop, "long",
                        min(stack["ma5h"][-1], stack["ma10h"][-1]),
                        min_r=EXTREME_MIN_R,
                    )
                    if tps:
                        return CandidateSetup(
                            symbol, "long", entry, stop, tps[0],
                            _ind("bbma_extreme", "support", stack, atr_value,
                                 htf_bias, mhv_bar=mhv_i, source="taught"),
                            take_profit_2=tps[1], take_profit_3=tps[2],
                        )

    return None


def detect_setup(symbol, h1_candles, atr14, h4_candles):
    """Prefer taught re-entry; fall back to Extreme+MHV."""
    bias = htf_bias_mid_ema50(h4_candles)
    setup = detect_reentry(symbol, h1_candles, atr14, bias)
    if setup is not None:
        return setup
    return detect_extreme_mhv(symbol, h1_candles, atr14, bias)
