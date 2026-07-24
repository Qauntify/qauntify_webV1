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
}
ROLE_FILL = {"fvg": "#14b8a6", "sr": "#38bdf8", "premium": "#fb7185", "discount": "#2dd4bf"}
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


def render_chart(candles, plan, signal) -> bytes:
    """Render the last RENDER_BARS candles + annotations to PNG bytes."""
    view = candles[-RENDER_BARS:]
    df = _frame(view)
    x_of = {c.open_time: i for i, c in enumerate(view)}
    last_x = len(view) - 1

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
    ax = axes[0]
    _draw(ax, plan, x_of, last_x)
    ax.set_title(
        f"{signal.symbol} · {signal.timeframe} · "
        f"{signal.direction.upper()} · {signal.confidence}%",
        color="#e2e8f0", fontsize=14, fontweight="bold", loc="left",
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=FIG_DPI, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
