"""BBMA Re-entry — the setup the manual calls the safest entry.

Rules follow docs/strategy_doc (BBMA-STRATEGY1, the 79-page manual, plus the
Brocamkh summary). Page references below are to the manual.

The sequence the manual describes is: a DIRECTION signal fires, price pulls
back into the MA5/MA10 zone without closing through it, and entry is taken on
the NEXT candle.

  * Arming signal (p35: "applicable after cs direction AND momentum") — either
    - CSM, a candle closing OUTSIDE the top/low band (p38), or
    - CSAK, a "strong direction candle" closing through MA5/MA10 AND Mid BB
      (p31). The Brocamkh summary defines CSAK by the Mid BB break; the manual
      splits it into "early" (past MA5/10 only) and "strong" (past Mid BB too).
      Requiring the strong form satisfies both readings.

    An earlier version of this detector armed on CSM only, which silently
    discarded the entire CSAK branch — most of the setups the manual describes.

  * Pullback (p33) — "candle close can not get past a 5-/A10". The close must
    hold the zone FLOOR, which for a buy is MA10-Low. An earlier version tested
    MA10-HIGH, a level above the floor, and so rejected valid re-entries.

  * Entry (p33, p36) — "wait a second candle … if the first candle prick and
    close body, not beyond a 5-/10 and mid bb, entry in the second candle".
    The pullback bar arms; the next bar confirms and is the entry.

  * Target (Brocamkh summary p4, manual p24/p40) — "TP at Ma5/10 in TF1: buy
    TP at Ma5/10 High, sell at Ma5/10 Low". The first target is mandatory and
    structural, and it applies to the system, not only to Extreme. Measured
    over 8.87 years, targeting the MA pair rather than the band lifts the TP1
    hit rate from ~43% to ~75% and the pooled result from -53R to +531R —
    the manual's level is the one that works. TP2/TP3 extend one and two R
    beyond it so the engine keeps its three-level ladder.

Deliberately NOT gated on EMA50 or Mid-BB slope. Both appear in the manual only
as strength qualifiers ("trends will be stronger if…", p38), never as
requirements, and a previous version made them mandatory.
"""
from signals.models import CandidateSetup
from signals.strategies.bbma.stack import (
    MIN_CANDLES,
    STOP_ATR_BUFFER,
    bbma_stack,
    risk_ok,
    stack_ready,
    structural_targets,
)

# How far back the arming CSAK/CSM signal may sit.
SIGNAL_LOOKBACK = 10
# The mandatory MA target sits close to price, so like Extreme it is normally
# inside 1R. Requiring 1R here discards the setups that actually pay.
REENTRY_MIN_R = 0.0


def _indicators(side, stack, atr_value, adx14, htf_trend, trigger):
    out = {
        "strategy": "bbma_reentry",
        "side": side,
        "trigger": trigger,          # "csm" or "csak"
        "bb_upper": stack["upper"][-1],
        "bb_mid": stack["mid"][-1],
        "bb_lower": stack["lower"][-1],
        "ma5h": stack["ma5h"][-1],
        "ma5l": stack["ma5l"][-1],
        "ma10h": stack["ma10h"][-1],
        "ma10l": stack["ma10l"][-1],
        "ema50": stack["ema50"][-1],
        "atr": atr_value,
    }
    if adx14 is not None and adx14[-1] is not None:
        out["adx"] = adx14[-1]
    if htf_trend is not None:
        out["htf_trend"] = htf_trend
    return out


def _arming_signal(candles, stack, window, up):
    """Return "csm", "csak", or None for the most recent qualifying signal.

    CSM is momentum (close beyond the band); CSAK is a strong direction candle
    (close through the MA5/MA10 zone and Mid BB). Either arms a re-entry.
    """
    found = None
    for i in window:
        band = stack["upper"][i] if up else stack["lower"][i]
        mid = stack["mid"][i]
        ma5 = stack["ma5h"][i] if up else stack["ma5l"][i]
        ma10 = stack["ma10h"][i] if up else stack["ma10l"][i]
        if band is None or mid is None or ma5 is None or ma10 is None:
            continue
        close = candles[i].close
        if (close > band) if up else (close < band):
            found = "csm"
        elif ((close > ma5 and close > ma10 and close > mid) if up
              else (close < ma5 and close < ma10 and close < mid)):
            found = found or "csak"
    return found


def detect_setup(symbol, candles, atr14, adx14=None, htf_trend=None):
    """Return a CandidateSetup on a confirmed BBMA Re-entry, else None.

    `htf_trend` IS gated here — unlike Extreme, this is a with-trend trade, so
    a long against a "down" higher timeframe is refused.
    """
    # One extra bar over MIN_CANDLES: the setup spans a pullback bar and the
    # confirming bar after it.
    if len(candles) < MIN_CANDLES + 1 or atr14[-1] is None:
        return None
    atr_value = atr14[-1]
    if atr_value <= 0:
        return None

    stack = bbma_stack(candles)
    if not stack_ready(stack):
        return None

    n = len(candles)
    pull, bar = candles[-2], candles[-1]
    # The arming signal must precede the pullback bar.
    window = range(max(0, n - 2 - SIGNAL_LOOKBACK), n - 2)

    ma5l_p, ma10l_p, mid_p = (stack["ma5l"][-2], stack["ma10l"][-2],
                              stack["mid"][-2])
    ma5h_p, ma10h_p = stack["ma5h"][-2], stack["ma10h"][-2]
    ma10l, ma10h, mid = stack["ma10l"][-1], stack["ma10h"][-1], stack["mid"][-1]
    upper, lower = stack["upper"][-1], stack["lower"][-1]
    if None in (ma5l_p, ma10l_p, mid_p, ma5h_p, ma10h_p):
        return None

    # --- long ---------------------------------------------------------------
    trigger = _arming_signal(candles, stack, window, up=True)
    if (trigger and htf_trend != "down"
            and pull.low <= ma5l_p              # pulled back into the MA zone
            and pull.close > ma10l_p            # held the zone floor
            and pull.close > mid_p              # and Mid BB
            and bar.close > pull.close          # second candle confirms
            and bar.close > ma10l and bar.close > mid):
        entry = bar.close
        stop = min(pull.low, bar.low, ma10l) - STOP_ATR_BUFFER * atr_value
        if stop < entry and risk_ok(entry, stop, atr_value):
            tps = structural_targets(entry, stop, "long",
                                     max(stack["ma5h"][-1], ma10h),
                                     min_r=REENTRY_MIN_R)
            if tps:
                return CandidateSetup(
                    symbol, "long", entry, stop, tps[0],
                    _indicators("support", stack, atr_value, adx14, htf_trend,
                                trigger),
                    take_profit_2=tps[1], take_profit_3=tps[2],
                )

    # --- short --------------------------------------------------------------
    trigger = _arming_signal(candles, stack, window, up=False)
    if (trigger and htf_trend != "up"
            and pull.high >= ma5h_p
            and pull.close < ma10h_p
            and pull.close < mid_p
            and bar.close < pull.close
            and bar.close < ma10h and bar.close < mid):
        entry = bar.close
        stop = max(pull.high, bar.high, ma10h) + STOP_ATR_BUFFER * atr_value
        if stop > entry and risk_ok(entry, stop, atr_value):
            tps = structural_targets(entry, stop, "short",
                                     min(stack["ma5l"][-1], ma10l),
                                     min_r=REENTRY_MIN_R)
            if tps:
                return CandidateSetup(
                    symbol, "short", entry, stop, tps[0],
                    _indicators("resistance", stack, atr_value, adx14,
                                htf_trend, trigger),
                    take_profit_2=tps[1], take_profit_3=tps[2],
                )

    return None
