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

# Fewer bars → fatter candles; 1280×720-ish at higher DPI for phone clarity.
RENDER_BARS = 40
# Widen when Liquidity / CHoCH / FVG sit left of a blind 40-bar trim.
RENDER_BARS_MAX = 80
FIG_SIZE = (12.8, 7.2)
FIG_DPI = 150
_BG = "#000000"
_GRID = "#1a1a1a"
_MUTED = "#64748b"
_TEXT = "#e2e8f0"

ROLE_LINE = {
    "choch": "#a78bfa", "liquidity": "#f59e0b", "entry": "#f8fafc",
    "stop": "#f87171", "target": "#4ade80", "trail": "#f59e0b",
    "ema-fast": "#38bdf8", "ema-slow": "#f59e0b", "lwma": "#a78bfa",
    "win": "#4ade80", "loss": "#f87171",
    "bb-band": "#64748b", "bb-mid": "#94a3b8",
    "ma5": "#f472b6", "ma10": "#fbbf24", "ema50": "#a3e635",
}
ROLE_FILL = {
    "fvg": "#14b8a6", "sr": "#38bdf8",
    # cloud_mss: discount = buy zone (green), premium = sell zone (red)
    "premium": "#ef4444", "discount": "#22c55e",
    "win": "#4ade80", "loss": "#f87171",
}
# Primary trade levels get thicker lines + roomier labels.
_PRIMARY_ROLES = frozenset({"entry", "stop", "target"})
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


def _label_box(ax, x, y, text, color, fontsize=10):
    """Right-edge label with a dark pill so it stays readable over candles."""
    ax.text(
        x, y, f" {text} ",
        color=color, fontsize=fontsize, fontweight="bold", va="center",
        ha="left", zorder=7,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "#0a0a0a",
            "edgecolor": color,
            "linewidth": 0.8,
            "alpha": 0.92,
        },
    )


def _draw(ax, plan, x_of, last_x):
    right = last_x + 0.5
    label_x = right + 0.35
    for a in plan:
        kind = a["kind"]
        if kind == "zone":
            x0 = x_of.get(a["start_time"], 0) - 0.5
            if a.get("end_time") is not None and a["end_time"] in x_of:
                x1 = x_of[a["end_time"]] + 0.5
            elif a.get("end_time") is not None:
                x1 = min(right, x0 + 3.5)
            else:
                x1 = right
            if x1 <= x0:
                x1 = right
            low = min(a["price_bottom"], a["price_top"])
            high = max(a["price_bottom"], a["price_top"])
            color = ROLE_FILL.get(a["role"], "#38bdf8")
            ax.add_patch(Rectangle(
                (x0, low), x1 - x0, high - low,
                facecolor=color, alpha=0.28, edgecolor=color,
                linewidth=1.4, linestyle="--", zorder=1,
            ))
            ax.text(
                x0 + 0.35, high, a["label"], color=color, fontsize=10,
                fontweight="bold", va="bottom", zorder=6,
            )
        elif kind == "level":
            x0 = x_of.get(a["start_time"], 0) if a.get("start_time") else 0
            role = a["role"]
            color = ROLE_LINE.get(role, "#94a3b8")
            primary = role in _PRIMARY_ROLES
            ax.plot(
                [x0, right], [a["price"], a["price"]], color=color,
                linewidth=2.0 if primary else 1.35,
                linestyle=_DASH.get(a.get("style", "solid"), "-"),
                zorder=3, solid_capstyle="round",
            )
            _label_box(
                ax, label_x, a["price"], a["label"], color,
                fontsize=10 if primary else 9,
            )
        elif kind == "marker":
            x = x_of.get(a["time"])
            if x is None:
                continue
            color = ROLE_LINE.get(a["role"], "#e2e8f0")
            ax.scatter(
                [x], [a["price"]], s=90, color=color, edgecolors=_BG,
                linewidths=1.6, zorder=5,
            )
            label = (f"{a['order']}. " if a.get("order") else "") + a["label"]
            ax.annotate(
                label, (x, a["price"]), textcoords="offset points",
                xytext=(0, 14), ha="center", color=color, fontsize=9,
                fontweight="bold", zorder=6,
            )
        elif kind == "band":
            xs, ups, los = [], [], []
            for p in a["points"]:
                xi = x_of.get(p["time"])
                if xi is None or p["upper"] is None or p["lower"] is None:
                    continue
                xs.append(xi)
                ups.append(p["upper"])
                los.append(p["lower"])
            if xs:
                color = ROLE_FILL.get(a["role"], "#38bdf8")
                ax.fill_between(
                    xs, los, ups, color=color, alpha=0.22, zorder=1, linewidth=0,
                )
                ax.plot(xs, ups, color=color, linewidth=1.2, alpha=0.85, zorder=2)
                ax.plot(xs, los, color=color, linewidth=1.2, alpha=0.85, zorder=2)
                ax.text(
                    xs[0] + 0.35, max(ups[0], los[0]), a["label"], color=color,
                    fontsize=10, fontweight="bold", va="bottom", zorder=6,
                )
        elif kind == "series":
            xs, ys = [], []
            for p in a["points"]:
                xi = x_of.get(p["time"])
                if xi is not None and p["value"] is not None:
                    xs.append(xi)
                    ys.append(p["value"])
            if xs:
                ax.plot(
                    xs, ys, color=ROLE_LINE.get(a["role"], "#38bdf8"),
                    linewidth=1.35, zorder=2,
                )


def _price_bounds(candles, plan, pad_frac=0.10):
    """(low, high) y-limits covering candles + every drawn price level."""
    lo = min(c.low for c in candles)
    hi = max(c.high for c in candles)
    for a in plan:
        if a["kind"] in ("level", "marker"):
            lo = min(lo, a["price"])
            hi = max(hi, a["price"])
        elif a["kind"] == "zone":
            lo = min(lo, a["price_bottom"], a["price_top"])
            hi = max(hi, a["price_bottom"], a["price_top"])
        elif a["kind"] == "band":
            values = [v for p in a["points"]
                      for v in (p["upper"], p["lower"]) if v is not None]
            if values:
                lo = min(lo, min(values))
                hi = max(hi, max(values))
    pad = (hi - lo) * pad_frac or 1.0
    return lo - pad, hi + pad


def _base_plot(candles):
    """Build the styled candlestick figure. Returns (fig, ax, x_of, last_x)."""
    df = _frame(candles)
    x_of = {c.open_time: i for i, c in enumerate(candles)}
    # Strong contrast — reads clearly on phones / Telegram.
    mc = mpf.make_marketcolors(
        up="#22c55e", down="#ef4444",
        wick={"up": "#4ade80", "down": "#f87171"},
        edge={"up": "#22c55e", "down": "#ef4444"},
        volume="in",
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor=_BG,
        figcolor=_BG,
        edgecolor=_GRID,
        gridcolor=_GRID,
        gridstyle=":",
        y_on_right=True,
        rc={
            "axes.labelcolor": _MUTED,
            "xtick.color": _MUTED,
            "ytick.color": _MUTED,
            "axes.edgecolor": _GRID,
            "figure.facecolor": _BG,
            "savefig.facecolor": _BG,
        },
    )
    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        figsize=FIG_SIZE,
        returnfig=True,
        volume=False,
        xrotation=0,
        datetime_format="%H:%M",
        tight_layout=False,
        update_width_config={
            "candle_linewidth": 1.35,
            "candle_width": 0.78,
        },
    )
    ax = axes[0]
    ax.set_facecolor(_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
        spine.set_linewidth(0.8)
    ax.tick_params(colors=_MUTED, labelsize=9)
    ax.grid(True, color=_GRID, linestyle=":", linewidth=0.7, alpha=0.9)
    # Room on the right for level pills.
    ax.set_xlim(-0.6, len(candles) + 3.2)
    return fig, ax, x_of, len(candles) - 1


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=FIG_DPI, facecolor=_BG,
        bbox_inches="tight", pad_inches=0.18,
    )
    plt.close(fig)
    return buf.getvalue()


def _plan_times(plan) -> list:
    """open_time values referenced by structure / trade annotations."""
    times = []
    for a in plan or []:
        for key in ("time", "start_time", "end_time"):
            t = a.get(key)
            if t is not None:
                times.append(t)
    return times


def view_for_plan(candles, plan, *, min_bars=RENDER_BARS,
                  max_bars=RENDER_BARS_MAX):
    """Candles shown on the setup chart so structure markers stay on-screen.

    Starts a couple of bars before the earliest plan timestamp (sweep / FVG /
    CHoCH), through the latest candle. Floors at `min_bars` when structure is
    tight; caps at `max_bars` so candles stay readable on phone.
    """
    if not candles:
        return []
    times = _plan_times(plan)
    if not times:
        return candles[-min_bars:]
    earliest = min(times)
    start_i = 0
    for i, c in enumerate(candles):
        if c.open_time >= earliest:
            start_i = max(0, i - 2)
            break
    view = candles[start_i:]
    if len(view) < min_bars:
        view = candles[-min_bars:] if len(candles) >= min_bars else list(candles)
    if len(view) > max_bars:
        view = view[-max_bars:]
    return view


def _setup_title(signal) -> str:
    ind = signal.indicators or {}
    title = (
        f"{signal.symbol}  ·  {signal.timeframe}  ·  "
        f"{signal.direction.upper()}  ·  {signal.confidence}%"
    )
    structure = ind.get("structure")
    if structure:
        title = f"{title}  ·  {structure}"
    return title


def render_chart(candles, plan, signal, title=None) -> bytes:
    """Render setup candles + annotations to PNG bytes.

    The view auto-fits to structure timestamps in `plan` (Liquidity / CHoCH /
    FVG) so markers are not clipped off the left by a blind last-N trim.

    Pass MORE than the view length when the plan draws indicator series: the
    builder computes them over everything given, and only the fitted window is
    displayed. Passing exactly the view would recompute every indicator from a
    cold start inside it, showing warm-up artefacts instead of the values the
    detector actually saw.

    `title` overrides the default headline for callers with no confidence score
    to show, such as a backtest replay.
    """
    view = view_for_plan(candles, plan)
    fig, ax, x_of, last_x = _base_plot(view)
    _draw(ax, plan, x_of, last_x)
    ax.set_ylim(*_price_bounds(view, plan))
    ax.set_title(
        title or _setup_title(signal),
        color=_TEXT, fontsize=15, fontweight="bold", loc="left", pad=12,
    )
    return _to_png(fig)


OUTCOME_MAX_BARS = 100


def _outcome_title(signal_row, outcome) -> str:
    entry = float(signal_row["entry"])
    stop = float(signal_row["stop_loss"])
    direction = signal_row["direction"]
    full_win = outcome in ("tp3_hit", "tp_hit")
    partial_win = (
        outcome in ("tp1_hit", "tp2_hit")
        or (outcome == "sl_hit" and bool(signal_row.get("tp1_hit_at")))
    )
    win = full_win or partial_win
    if full_win:
        exit_price = float(signal_row.get("take_profit_3") or signal_row.get("take_profit"))
        tag = "✓ TP3 HIT"
    elif outcome == "tp2_hit" or (
        partial_win and signal_row.get("tp2_hit_at") and outcome != "tp1_hit"
    ):
        exit_price = float(
            signal_row.get("take_profit_2")
            or signal_row.get("take_profit_1")
            or signal_row.get("take_profit")
            or entry
        )
        tag = "✓ TP2 WIN"
    elif partial_win:
        exit_price = float(
            signal_row.get("take_profit_1")
            or signal_row.get("take_profit")
            or entry
        )
        tag = "✓ TP1 WIN"
    else:
        exit_price = stop
        tag = "✗ SL HIT"
    risk = abs(entry - stop) or 1e-9
    r = abs(exit_price - entry) / risk * (1 if win else -1)
    move = (exit_price - entry) / entry * 100 * (1 if direction == "long" else -1)
    return (f"{signal_row['symbol']}  ·  {signal_row.get('timeframe', '')}  ·  "
            f"{direction.upper()}  ·  {tag}  ·  {r:+.1f}R ({move:+.2f}%)")


def render_outcome_chart(candles, plan, signal_row, entry_time, outcome,
                        title=None, max_bars=None) -> bytes:
    """Render an outcome (result) chart: price path + fills + HIT/STOP flag.

    `title` overrides the default headline. _outcome_title reads every
    non-win as a stop, which is wrong for a trade that simply expired — a
    backtest replay needs to say so rather than label it "SL HIT".

    `max_bars` widens the window past OUTCOME_MAX_BARS. The default trims to
    the most recent bars, which on a long-running trade drops the entry and its
    early fills off the left edge — leaving a chart whose title claims targets
    it does not show. Callers that know the trade's full length should pass it.
    """
    view = candles[-(max_bars or OUTCOME_MAX_BARS):]
    fig, ax, x_of, last_x = _base_plot(view)
    entry_x = x_of.get(entry_time)
    if entry_x is not None:
        ax.axvspan(-0.5, entry_x - 0.5, color="#94a3b8", alpha=0.05, zorder=0)
        ax.axvline(
            entry_x, color="#64748b", linestyle=(0, (2, 3)),
            linewidth=1.1, zorder=1,
        )
    _draw(ax, plan, x_of, last_x)
    ax.set_ylim(*_price_bounds(view, plan))
    ax.set_title(
        title or _outcome_title(signal_row, outcome),
        color=_TEXT, fontsize=15, fontweight="bold", loc="left", pad=12,
    )
    return _to_png(fig)
