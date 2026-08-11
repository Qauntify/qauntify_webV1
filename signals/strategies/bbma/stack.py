"""The BBMA indicator stack — the five lines every BBMA setup is read against.

Settings are the canonical MT4 ones from the Oma Ally material: Bollinger Bands
20/2 on close, MA5 and MA10 as LINEAR WEIGHTED averages applied separately to
highs and lows, and EMA50 on close.

The moving averages being linear weighted is not incidental. The whole system
is taught and charted on LWMA, so `lwma` is the correct primitive here and
substituting `ema` or a simple average would move every level the rules test
against.
"""
from signals.analysis.indicators import bollinger, ema, lwma
from signals.models import take_profits_from_risk

BB_PERIOD = 20
BB_DEV = 2.0
MA_FAST = 5
MA_SLOW = 10
EMA_TREND = 50

# EMA50 warm-up plus headroom for the detectors' lookback windows.
MIN_CANDLES = 60
# Stops sit this many ATRs beyond the structural level — obvious levels get
# wick-hunted, so resting exactly on one is a donation.
STOP_ATR_BUFFER = 0.5
# Reject setups whose stop is farther than this many ATRs from entry.
MAX_STOP_ATR = 2.5


def bbma_stack(candles):
    """Return the eight aligned BBMA series for `candles` as a dict.

    Keys: upper, mid, lower, ma5h, ma5l, ma10h, ma10l, ema50. Every value is a
    list aligned 1:1 with `candles`, None-padded through its own warm-up.
    """
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    upper, mid, lower = bollinger(closes, BB_PERIOD, BB_DEV)
    return {
        "upper": upper,
        "mid": mid,
        "lower": lower,
        "ma5h": lwma(highs, MA_FAST),
        "ma5l": lwma(lows, MA_FAST),
        "ma10h": lwma(highs, MA_SLOW),
        "ma10l": lwma(lows, MA_SLOW),
        "ema50": ema(closes, EMA_TREND),
    }


def stack_ready(stack):
    """True when every series carries a value on the latest bar."""
    return all(series[-1] is not None for series in stack.values())


# BBMA marks the first target "mandatory" (manual p24). A mandatory target
# sitting nearer than the stop is a sub-1R trade, so the setup is skipped
# rather than taken at negative expectancy by construction.
MIN_STRUCTURAL_R = 1.0


def structural_targets(entry, stop, direction, target, min_r=MIN_STRUCTURAL_R):
    """TP1 at a structural BBMA level, TP2/TP3 one and two R beyond it.

    Returns None when `target` is nearer than `min_r`, or on the wrong side of
    entry. Keeping TP2/TP3 in R preserves the three-level ladder the outcome
    tracker, r_model and the track-record page all assume, while the level the
    manual actually names drives the first exit.

    `min_r` is per-setup because the manual's two setups have different shapes.
    Re-entry targets the band, comfortably beyond 1R. Extreme targets the
    opposite MA5/10 while stopping beyond the whole spike, so its mandatory
    target is nearly always INSIDE 1R — the manual says as much, calling for
    profit to be taken early because direction is not yet confirmed. Applying a
    1R floor there does not filter Extreme, it deletes it.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    reach = (target - entry) if direction == "long" else (entry - target)
    r1 = reach / risk
    if r1 <= 0 or r1 < min_r:
        return None
    return take_profits_from_risk(entry, stop, direction,
                                  r1=r1, r2=r1 + 1.0, r3=r1 + 2.0)


def risk_ok(entry, stop, atr_value):
    """True when the stop is within MAX_STOP_ATR of entry.

    Side is NOT checked here — each detector asserts its own direction, the
    same split sr_zone uses.
    """
    if atr_value <= 0:
        return False
    return abs(entry - stop) / atr_value <= MAX_STOP_ATR
