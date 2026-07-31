"""The single definition of what one trade was worth.

Everything that reports performance — the calibration report, the gate A/B,
the public track record — has to agree on this. Before this module there were
three separate answers to "what is a full winner worth?" (+3R, +3R and +2R,
depending on which file you read), and the most optimistic of them was the one
on the public page.

There is exactly one model, and it is the trade this engine actually publishes:

  * Position enters in full, then books an equal third at each of TP1/TP2/TP3.
  * The stop does NOT move. The Telegram message carries one SL and never asks
    the follower to trail it, and `outcome_tracker` settles every trade against
    that same `stop_loss` for its whole life.
  * So an unbooked remainder still standing when the stop is hit loses 1R of
    its share.

Under it a trade that runs all the way to TP3 returns (1 + 2 + 3) / 3 = +2R,
not +3R; a trade that banks TP1 and then reverses into the stop returns
0.33 - 0.67 = -0.33R; and a stop before any target is a full -1R.

HISTORY, because this was wrong and the error was expensive. This module used
to score the remainder at breakeven (0R) once TP1 was banked, while
`backtest.simulate_scaled` and the live tracker both walked a FIXED stop. That
pairing is not any real trade: it credited the trade for surviving a pullback
to entry (fixed stop) AND for losing nothing when the stop finally hit
(breakeven). Measured over 8.87 years of verified history, the gap between the
hybrid and an honest fixed stop was roughly 0.24R PER TRADE — enough to turn
several losing strategies into apparent winners. If the engine ever does start
telling followers to trail to breakeven, change `outcome_tracker` first and
this second; never only this.

Costs are subtracted separately (see `cost_r`) so a gross and a net number can
both be quoted, and so the pre-registered gate A/B can stay on the gross
metric it was registered with.
"""
from signals.market_client import canonical_symbol

# ---------------------------------------------------------------------------
# Gross R
# ---------------------------------------------------------------------------


def scaled_r(direction, entry, stop, tps, reached, stopped):
    """Realized R for a 1/len-at-each-target scale-out under a FIXED stop.

    - Each reached target books its slice at that target's R.
    - If the stop is then hit, the UNBOOKED remainder loses 1R of its share —
      the published stop never moves, so there is nothing to protect it.
    - Nothing reached + stopped → full -1R (the same case, with no slices
      booked).
    - Expiry with the stop untouched leaves the remainder at 0R: the trade was
      closed out flat, not stopped.
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
    if stopped:
        return booked - (1.0 - reached * portion)
    return booked


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

# Round-trip cost for a strategy that is filled as MAKER — a resting limit that
# adds liquidity rather than crossing the spread. Roughly 0.04% on crypto
# against the 0.20% taker figure above. This is not a discount to hand out
# freely: it applies only to a detector that genuinely rests an order (see
# signals/strategies/sr_limit), and it still assumes the order was filled,
# which candles cannot verify.
MAKER_BPS = 4.0


def cost_bps(symbol: str) -> float:
    return COST_BPS.get(canonical_symbol(symbol), DEFAULT_COST_BPS)


def cost_r(symbol: str, entry: float, stop: float, *, bps: float | None = None) -> float:
    """Round-trip cost expressed in R for one trade.

    Cost is a fraction of PRICE while R is a fraction of the stop distance, so
    the same venue is far more expensive on a tight stop than a wide one. That
    ratio is exactly why the 15m and 1h S/R variants measured so differently.

    `bps` overrides the symbol's default tier. COST_BPS assumes a TAKER fill,
    because every market-entry detector in this engine enters at a bar close. A
    resting-limit strategy earns the maker tier instead, and charging it taker
    fees would measure a strategy nobody would run — see MAKER_BPS.
    """
    if entry is None or stop is None:
        return 0.0
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    rate = cost_bps(symbol) if bps is None else bps
    return (rate / 10_000.0) * abs(entry) / risk


def net_r(row: dict) -> float | None:
    """Realized R for one closed signal AFTER costs, or None if unscoreable.

    This is the number to quote publicly.
    """
    gross = gross_r(row)
    if gross is None:
        return None
    return gross - cost_r(row.get("symbol", ""), row["entry"], row["stop_loss"])
