"""Renders an annotated candlestick PNG for one signal using mplfinance.

mplfinance places candles at integer x-positions (0..n-1). Annotations carry
candle open_times, so we map each time to its x-index before drawing.
"""
import io
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")  # headless: safe in CI / GitHub Actions runners
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402

RENDER_BARS = 60
FIG_SIZE = (16, 9)
FIG_DPI = 100  # 16*100 x 9*100 = 1600x900
_BG = "#0b1220"

ROLE_LINE = {
    "choch": "#a78bfa", "liquidity": "#f59e0b", "entry": "#e2e8f0",
    "stop": "#fb7185", "target": "#34d399", "trail": "#f59e0b",
    "ema-fast": "#38bdf8", "ema-slow": "#f59e0b", "lwma": "#a78bfa",
    "win": "#34d399", "loss": "#fb7185",
}
ROLE_FILL = {"fvg": "#14b8a6", "sr": "#38bdf8", "premium": "#fb7185",
             "discount": "#2dd4bf", "win": "#34d399", "loss": "#fb7185"}
_DASH = {"solid": "-", "dashed": (0, (5, 4)), "dotted": (0, (1, 3))}


def _frame(candles):
    idx = pd.DatetimeIndex(
        [datetime.fromtimestamp(c.open_time / 1000, tz=timezone.utc) for c in candles]
    )
    return pd.DataFrame(
        {
            "Open": [c.open for c in candles],
            "High": [c.high for c in candles],
            "Low": [c.low for c in candles],
            "Close": [c.close for c in candles],
            "Volume": [c.volume for c in candles],
        },
        index=idx,
    )


def _draw(ax, plan, x_of, last_x):
    right = last_x + 0.5
    for a in plan:
        kind = a["kind"]
        if kind == "zone":
            x0 = x_of.get(a["start_time"], 0) - 0.5
            low = min(a["price_bottom"], a["price_top"])
            high = max(a["price_bottom"], a["price_top"])
            color = ROLE_FILL.get(a["role"], "#38bdf8")
            ax.add_patch(Rectangle((x0, low), right - x0, high - low,
                                   facecolor=color, alpha=0.15, edgecolor=color,
                                   linewidth=1, linestyle="--", zorder=1))
            ax.text(x0 + 0.4, high, a["label"], color=color, fontsize=9,
                    fontweight="bold", va="bottom", zorder=6)
        elif kind == "level":
            x0 = x_of.get(a["start_time"], 0) if a.get("start_time") else 0
            color = ROLE_LINE.get(a["role"], "#94a3b8")
            ax.plot([x0, right], [a["price"], a["price"]], color=color, linewidth=1.3,
                    linestyle=_DASH.get(a.get("style", "solid"), "-"), zorder=3)
            ax.text(right + 0.3, a["price"], a["label"], color=color, fontsize=8.5,
                    fontweight="bold", va="center", zorder=6)
        elif kind == "marker":
            x = x_of.get(a["time"])
            if x is None:
                continue
            color = ROLE_LINE.get(a["role"], "#e2e8f0")
            ax.scatter([x], [a["price"]], s=70, color=color, edgecolors=_BG,
                       linewidths=1.5, zorder=5)
            label = (f"{a['order']}. " if a.get("order") else "") + a["label"]
            ax.annotate(label, (x, a["price"]), textcoords="offset points",
                        xytext=(0, 13), ha="center", color=color, fontsize=9,
                        fontweight="bold", zorder=6)
        elif kind == "series":
            xs, ys = [], []
            for p in a["points"]:
                xi = x_of.get(p["time"])
                if xi is not None and p["value"] is not None:
                    xs.append(xi)
                    ys.append(p["value"])
            if xs:
                ax.plot(xs, ys, color=ROLE_LINE.get(a["role"], "#38bdf8"),
                        linewidth=1.2, zorder=2)


def _price_bounds(candles, plan, pad_frac=0.04):
    """(low, high) y-limits covering the candles AND every drawn price level.

    mplfinance auto-scales the y-axis to the candles only, so entry/SL/TP or
    zones that sit outside the candle range (a TP is usually above price) get
    clipped off the top or bottom. Widen the range so the whole trade is
    visible, with a little padding.
    """
    lo = min(c.low for c in candles)
    hi = max(c.high for c in candles)
    for a in plan:
        if a["kind"] in ("level", "marker"):
            lo = min(lo, a["price"])
            hi = max(hi, a["price"])
        elif a["kind"] == "zone":
            lo = min(lo, a["price_bottom"], a["price_top"])
            hi = max(hi, a["price_bottom"], a["price_top"])
    pad = (hi - lo) * pad_frac or 1.0
    return lo - pad, hi + pad


def _base_plot(candles):
    """Build the styled candlestick figure. Returns (fig, ax, x_of, last_x)
    where x_of maps a candle open_time to its integer x-position."""
    df = _frame(candles)
    x_of = {c.open_time: i for i, c in enumerate(candles)}
    mc = mpf.make_marketcolors(up="#2dd4bf", down="#fb7185",
                               wick="inherit", edge="inherit")
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds", marketcolors=mc,
        facecolor=_BG, figcolor=_BG, edgecolor="#1e293b", gridcolor="#1e293b",
        rc={"axes.labelcolor": "#94a3b8", "xtick.color": "#64748b",
            "ytick.color": "#64748b"},
    )
    fig, axes = mpf.plot(
        df, type="candle", style=style, figsize=FIG_SIZE, returnfig=True,
        volume=False, xrotation=0, datetime_format="%H:%M", tight_layout=True,
    )
    return fig, axes[0], x_of, len(candles) - 1


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=FIG_DPI, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_chart(candles, plan, signal) -> bytes:
    """Render the last RENDER_BARS candles + annotations to PNG bytes."""
    view = candles[-RENDER_BARS:]
    fig, ax, x_of, last_x = _base_plot(view)
    _draw(ax, plan, x_of, last_x)
    ax.set_ylim(*_price_bounds(view, plan))
    ax.set_title(
        f"{signal.symbol} · {signal.timeframe} · "
        f"{signal.direction.upper()} · {signal.confidence}%",
        color="#e2e8f0", fontsize=14, fontweight="bold", loc="left",
    )
    return _to_png(fig)


OUTCOME_MAX_BARS = 120


def _outcome_title(signal_row, outcome) -> str:
    entry = float(signal_row["entry"])
    stop = float(signal_row["stop_loss"])
    direction = signal_row["direction"]
    win = outcome in ("tp3_hit", "tp_hit")
    exit_price = (float(signal_row.get("take_profit_3") or signal_row.get("take_profit"))
                  if win else stop)
    risk = abs(entry - stop) or 1e-9
    r = abs(exit_price - entry) / risk * (1 if win else -1)
    move = (exit_price - entry) / entry * 100 * (1 if direction == "long" else -1)
    tag = "✓ TP3 HIT" if win else "✗ SL HIT"
    return (f"{signal_row['symbol']} · {signal_row.get('timeframe', '')} · "
            f"{direction.upper()} · {tag} · {r:+.1f}R ({move:+.2f}%)")


def render_outcome_chart(candles, plan, signal_row, entry_time, outcome) -> bytes:
    """Render an outcome (result) chart: price path + fills + HIT/STOP flag."""
    view = candles[-OUTCOME_MAX_BARS:]
    fig, ax, x_of, last_x = _base_plot(view)
    entry_x = x_of.get(entry_time)
    if entry_x is not None:
        ax.axvspan(-0.5, entry_x - 0.5, color="#94a3b8", alpha=0.06, zorder=0)
        ax.axvline(entry_x, color="#64748b", linestyle=(0, (2, 3)),
                   linewidth=1, zorder=1)
    _draw(ax, plan, x_of, last_x)
    ax.set_ylim(*_price_bounds(view, plan))
    ax.set_title(_outcome_title(signal_row, outcome), color="#e2e8f0",
                 fontsize=14, fontweight="bold", loc="left")
    return _to_png(fig)
