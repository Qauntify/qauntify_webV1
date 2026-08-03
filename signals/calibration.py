"""Aggregates closed-signal outcomes into win-rate / expectancy stats,
grouped by strategy, symbol, timeframe, and confidence bucket.

Closes the loop between outcome_tracker's recorded results (tp_hit/sl_hit/
expired) and the parameters that produced them, so strategy or threshold
changes can be checked against real history instead of guessed.

R comes from signals.r_model — the scale-out model, net of costs — so these
numbers mean the same thing as the ones on the public track record.
"""
from signals.r_model import cost_r, gross_r, is_win, net_r


def _strategy_of(row: dict) -> str:
    indicators = row.get("indicators") or {}
    return indicators.get("strategy", "ema_cross")


def _confidence_bucket(confidence) -> str:
    if confidence is None:
        return "unknown"
    lo = (int(confidence) // 10) * 10
    return f"{lo}-{lo + 9}"


def _r_multiple(row: dict) -> float:
    """Realized R-multiple for one closed signal, net of costs.

    Thin wrapper over signals.r_model.net_r that maps the unscoreable case
    (missing levels) to 0.0, since a grouped average has nowhere to put None.
    """
    r = net_r(row)
    return 0.0 if r is None else r


def _bucket_stats(rows: list) -> dict:
    """Win/loss counts and average R for one group of closed signals.

    A win is any trade that banked TP1 (or better), even if price later hit
    the original stop. Avg R still uses the scale-out / breakeven-trail model
    so a high win rate can still show a weak expectancy when costs matter.
    """
    scored = [(row, _r_multiple(row)) for row in rows]
    wins = sum(1 for row, _ in scored if is_win(row))
    losses = sum(1 for row, _ in scored if not is_win(row) and row["status"] == "sl_hit")
    breakeven = len(rows) - wins - losses
    expired = sum(1 for row in rows if row["status"] == "expired")
    decided = wins + losses
    return {
        "count": len(rows),
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "expired": expired,
        "win_rate": wins / decided if decided else None,
        "avg_r": (sum(r for _, r in scored) / len(scored)) if scored else None,
        "avg_gross_r": (
            sum((gross_r(row) or 0.0) for row in rows) / len(rows)
            if rows else None
        ),
        "avg_cost_r": (
            sum(cost_r(row.get("symbol", ""), row["entry"], row["stop_loss"])
                for row in rows) / len(rows)
            if rows else None
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
