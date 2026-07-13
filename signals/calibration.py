"""Aggregates closed-signal outcomes into win-rate / expectancy stats,
grouped by strategy, symbol, timeframe, and confidence bucket.

Closes the loop between outcome_tracker's recorded results (tp_hit/sl_hit/
expired) and the parameters that produced them, so strategy or threshold
changes can be checked against real history instead of guessed.
"""


def _strategy_of(row: dict) -> str:
    indicators = row.get("indicators") or {}
    return indicators.get("strategy", "ema_cross")


def _confidence_bucket(confidence) -> str:
    if confidence is None:
        return "unknown"
    lo = (int(confidence) // 10) * 10
    return f"{lo}-{lo + 9}"


def _r_multiple(row: dict) -> float:
    """Realized R-multiple for one closed signal: +reward/risk on tp_hit,
    -1 on sl_hit, 0 (unknown/neutral) on expired — outcome_tracker records
    no exit price for expired signals, so their true P&L is unknown."""
    status = row["status"]
    if status == "sl_hit":
        return -1.0
    if status == "expired":
        return 0.0
    entry, stop, target = row["entry"], row["stop_loss"], row["take_profit"]
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    return abs(target - entry) / risk


def _bucket_stats(rows: list) -> dict:
    wins = sum(1 for r in rows if r["status"] == "tp_hit")
    losses = sum(1 for r in rows if r["status"] == "sl_hit")
    expired = sum(1 for r in rows if r["status"] == "expired")
    decided = wins + losses
    # Expired rows have unknown P&L — exclude them from avg_r so expiry
    # rate cannot dilute expectancy toward zero.
    decided_rows = [r for r in rows if r["status"] in ("tp_hit", "sl_hit")]
    return {
        "count": len(rows),
        "wins": wins,
        "losses": losses,
        "expired": expired,
        # Expired rows are neither a win nor a loss, so they're excluded
        # from the win-rate denominator rather than counted against it.
        "win_rate": wins / decided if decided else None,
        "avg_r": (
            sum(_r_multiple(r) for r in decided_rows) / len(decided_rows)
            if decided_rows else None
        ),
    }


def summarize_by(rows: list, key_fn) -> dict:
    """Group closed-signal rows by key_fn and compute stats per group."""
    groups: dict = {}
    for row in rows:
        groups.setdefault(key_fn(row), []).append(row)
    return {key: _bucket_stats(group_rows) for key, group_rows in groups.items()}


def calibration_report(rows: list) -> dict:
    """Full report: overall stats plus grouped by strategy, symbol,
    timeframe, and confidence bucket."""
    return {
        "overall": _bucket_stats(rows),
        "by_strategy": summarize_by(rows, _strategy_of),
        "by_symbol": summarize_by(rows, lambda r: r["symbol"]),
        "by_timeframe": summarize_by(rows, lambda r: r.get("timeframe") or "1h"),
        "by_confidence": summarize_by(
            rows, lambda r: _confidence_bucket(r.get("confidence"))),
    }
