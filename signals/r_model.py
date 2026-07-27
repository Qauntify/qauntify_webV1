"""The single definition of what one trade was worth.

Everything that reports performance — the calibration report, the gate A/B,
the public track record — has to agree on this. Before this module there were
three separate answers to "what is a full winner worth?" (+3R, +3R and +2R,
depending on which file you read), and the most optimistic of them was the one
on the public page.

There is exactly one model, and it is the one a follower can actually execute:

  * Position enters in full, then books an equal third at each of TP1/TP2/TP3.
  * Once TP1 is banked the stop moves to breakeven, so the remainder exits at
    0R rather than -1R if price reverses.
  * Stopped out before TP1 is the only full -1R loss.

Under it a trade that runs all the way to TP3 returns (1 + 2 + 3) / 3 = +2R,
not +3R, and a trade that tags TP1 then reverses returns +0.33R, not -1R.

Costs are subtracted separately (see `cost_r`) so a gross and a net number can
both be quoted, and so the pre-registered gate A/B can stay on the gross
metric it was registered with.
"""
from signals.market_client import canonical_symbol

# ---------------------------------------------------------------------------
# Gross R
# ---------------------------------------------------------------------------


def scaled_r(direction, entry, stop, tps, reached, stopped):
    """Realized R for a 1/len-at-each-target scale-out with the stop trailed to
    breakeven once the first target is booked.

    - Nothing reached + stopped → full -1R.
    - Each reached target books its slice at that target's R.
    - The unbooked remainder exits at breakeven (0R) on a later stop or expiry.
    """
    risk = abs(entry - stop)
    if risk == 0 or not tps:
        return 0.0

    def r_of(price):
        return (price - entry) / risk if direction == "long" else (entry - price) / risk

    portion = 1.0 / len(tps)
    booked = sum(portion * r_of(tps[k]) for k in range(reached))
    if reached >= len(tps):
        return booked
    if reached == 0 and stopped:
        return -1.0
    return booked  # remainder trails out at breakeven → contributes 0R


def targets_of(row: dict) -> list:
    """TP1/TP2/TP3 prices present on a stored row, in order."""
    tps = [row.get("take_profit"), row.get("take_profit_2"),
           row.get("take_profit_3")]
    return [t for t in tps if t is not None]


def levels_reached(row: dict, target_count: int) -> int:
    """How many targets the trade banked.

    Read from the tp*_hit_at timestamps, not from the final status: a trade
    that banked TP1 and then reversed ends as 'sl_hit', and scoring it from the
    status alone would call every partial win a full loss.
    """
    reached = sum(1 for k in ("tp1_hit_at", "tp2_hit_at", "tp3_hit_at")
                  if row.get(k))
    if row.get("status") in ("tp3_hit", "tp_hit"):
        reached = target_count
    return min(reached, target_count)


def gross_r(row: dict) -> float | None:
    """Realized R for one closed signal BEFORE costs, or None if unscoreable."""
    entry, stop = row.get("entry"), row.get("stop_loss")
    if entry is None or stop is None or entry == stop:
        return None
    tps = targets_of(row)
    if not tps:
        return None
    return scaled_r(row["direction"], entry, stop, tps,
                    levels_reached(row, len(tps)),
                    row.get("status") == "sl_hit")


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

# Round-trip transaction cost — spread plus commission — in basis points of
# notional, per symbol. One round trip covers the whole position: entering in
# full and exiting in thirds still adds up to 1x notional out, so scaling out
# does not multiply the cost.
#
# Crypto reuses the taker figure already assumed in the sr_limit detector
# (0.20% round-trip). Gold and FX are conservative retail all-in estimates:
# XAUUSD ~$0.60 on a $3,300 price, GBPUSD ~1 pip.
#
# TUNE THESE to your actual venue and fee tier — they are the single biggest
# lever on the net track record, because at these stop distances cost is a
# large fraction of 1R, not a rounding error.
COST_BPS = {
    "BTCUSD": 20.0,
    "ETHUSD": 20.0,
    "XAUUSD": 2.0,
    "GBPUSD": 1.5,
}
# Unknown symbols take the most expensive assumption rather than a free ride.
DEFAULT_COST_BPS = 20.0


def cost_bps(symbol: str) -> float:
    return COST_BPS.get(canonical_symbol(symbol), DEFAULT_COST_BPS)


def cost_r(symbol: str, entry: float, stop: float) -> float:
    """Round-trip cost expressed in R for one trade.

    Cost is a fraction of PRICE while R is a fraction of the stop distance, so
    the same venue is far more expensive on a tight stop than a wide one. That
    ratio is exactly why the 15m and 1h S/R variants measured so differently.
    """
    if entry is None or stop is None:
        return 0.0
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return (cost_bps(symbol) / 10_000.0) * abs(entry) / risk


def net_r(row: dict) -> float | None:
    """Realized R for one closed signal AFTER costs, or None if unscoreable.

    This is the number to quote publicly.
    """
    gross = gross_r(row)
    if gross is None:
        return None
    return gross - cost_r(row.get("symbol", ""), row["entry"], row["stop_loss"])
