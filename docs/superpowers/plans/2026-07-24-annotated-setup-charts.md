# Annotated Setup Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every confirmed signal produces a real annotated candlestick PNG (marking FVG, CHoCH, liquidity sweep, S/R zone, EMAs + entry/SL/TP) that is delivered on Telegram as a photo and shown on the web dashboard.

**Architecture:** A new `signals/chart/` package turns a signal + its candle window into a normalized list of drawable primitives (`plan.py`), renders them over candlesticks with mplfinance (`render.py`), uploads the PNG to Supabase Storage (`upload.py`), and attaches the URL + structured data to the signal before it is saved (`pipeline.py`). Each strategy contributes a small pure builder; the renderer is strategy-agnostic. Chart failures are swallowed so a signal is never lost.

**Tech Stack:** Python 3.12, mplfinance/matplotlib/pandas, Supabase Storage (REST), Telegram Bot API (`sendPhoto`), Next.js/React (web display).

---

## File Structure

**Create:**
- `signals/chart/__init__.py` — package marker.
- `signals/chart/annotations.py` — primitive constructors (`zone`, `level`, `marker`, `series`).
- `signals/chart/plan.py` — `build_chart_plan` dispatcher + per-strategy builders + `_trade_levels`.
- `signals/chart/render.py` — `render_chart(candles, plan, signal) -> bytes` (mplfinance).
- `signals/chart/upload.py` — `upload_chart(png, signal_id, ...) -> url`.
- `signals/chart/pipeline.py` — `attach_chart(signal, candles, ...) -> Signal` (non-fatal wrapper).
- `tests/chart/test_annotations.py`, `test_plan.py`, `test_render.py`, `test_upload.py`, `test_pipeline.py`.

**Modify:**
- `supabase/schema.sql` — add `chart_url`, `chart_data` columns + `signal-charts` bucket.
- `signals/models.py` — add `chart_url`, `chart_data` fields to `Signal`.
- `signals/strategies/ict_fvg/detector.py` — store event timestamps.
- `signals/strategies/ict_smc/detector.py` — store event timestamps.
- `signals/strategies/ema_cross/detector.py` — store cross timestamp.
- `signals/run.py:495` — call `attach_chart` before `save_signal`.
- `signals/telegram_client.py` — `format_caption`, `send_photo`, photo-or-fallback `send_alert`.
- `web/src/lib/signals.ts` — `chartUrl` on `Signal`/`SignalRow` + `parseRow`.
- `web/src/components/dashboard/SignalsGrid.tsx` — render the chart image.
- `requirements.txt` — add `mplfinance`.

---

## Task 1: DB columns + Storage bucket

**Files:**
- Modify: `supabase/schema.sql` (append at end)

- [ ] **Step 1: Append the migration SQL**

Add to the end of `supabase/schema.sql`:

```sql
-- Annotated setup charts: PNG URL + structured annotation/candle data.
alter table public.signals add column if not exists chart_url text;
alter table public.signals add column if not exists chart_data jsonb;

-- Public bucket for rendered signal charts. Objects are uploaded with the
-- service key (bypasses RLS) and read via the public object path.
insert into storage.buckets (id, name, public)
values ('signal-charts', 'signal-charts', true)
on conflict (id) do nothing;
```

- [ ] **Step 2: Apply it to Supabase**

Run the appended SQL in the Supabase SQL editor (or `psql`) against the project database. Verify: `select column_name from information_schema.columns where table_name='signals' and column_name in ('chart_url','chart_data');` returns both rows, and the `signal-charts` bucket appears under Storage.

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(chart): add chart_url/chart_data columns + signal-charts bucket"
```

---

## Task 2: Annotation primitives

**Files:**
- Create: `signals/chart/__init__.py`
- Create: `signals/chart/annotations.py`
- Test: `tests/chart/test_annotations.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/__init__.py` (empty) and `tests/chart/test_annotations.py`:

```python
from signals.chart.annotations import zone, level, marker, series


def test_zone_orders_prices_and_tags_kind():
    z = zone(101.0, 100.0, 1234, "Fair Value Gap", "fvg")
    assert z["kind"] == "zone"
    assert z["price_top"] == 101.0 and z["price_bottom"] == 100.0
    assert z["start_time"] == 1234 and z["role"] == "fvg"


def test_level_defaults_to_solid_full_width():
    lv = level(100.5, "Entry", "entry")
    assert lv == {"kind": "level", "price": 100.5, "label": "Entry",
                  "role": "entry", "style": "solid", "start_time": None}


def test_marker_carries_order():
    m = marker(42, 99.0, "Liquidity sweep", "liquidity", 1)
    assert m["kind"] == "marker" and m["time"] == 42 and m["order"] == 1


def test_series_holds_points():
    s = series([{"time": 1, "value": 100.0}], "EMA9", "ema-fast")
    assert s["kind"] == "series" and s["points"][0]["value"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chart/test_annotations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/__init__.py` (empty file).

Create `signals/chart/annotations.py`:

```python
"""Normalized drawable primitives shared by every strategy's chart plan.

Each primitive is a plain JSON-serializable dict so the whole plan can be
stored in the signal's `chart_data` column and re-rendered later.
`role` is a semantic tag (e.g. "fvg", "liquidity", "entry") that the renderer
maps to a brand color — builders never choose colors.
"""


def zone(price_top, price_bottom, start_time, label, role):
    """A shaded box (FVG, S/R zone). start_time=None means full chart width."""
    return {
        "kind": "zone",
        "price_top": price_top,
        "price_bottom": price_bottom,
        "start_time": start_time,
        "label": label,
        "role": role,
    }


def level(price, label, role, style="solid", start_time=None):
    """A horizontal line (CHoCH, swept level, entry/SL/TP)."""
    return {
        "kind": "level",
        "price": price,
        "label": label,
        "role": role,
        "style": style,
        "start_time": start_time,
    }


def marker(time, price, label, role, order=None):
    """A labeled dot on a specific candle (sweep, CHoCH confirmation, retest)."""
    return {
        "kind": "marker",
        "time": time,
        "price": price,
        "label": label,
        "role": role,
        "order": order,
    }


def series(points, label, role):
    """A line over the candles (EMA, LWMA). points: [{time, value}, ...]."""
    return {"kind": "series", "points": points, "label": label, "role": role}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chart/test_annotations.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add signals/chart/__init__.py signals/chart/annotations.py tests/chart/__init__.py tests/chart/test_annotations.py
git commit -m "feat(chart): add normalized annotation primitives"
```

---

## Task 3: ict_fvg detector — store event timestamps

**Files:**
- Modify: `signals/strategies/ict_fvg/detector.py` (both `indicators` dicts)
- Test: `tests/strategies/test_ict_fvg_detector.py`

The detector computes `sweep_i`, `choch_i`, `fvg_i`, `retest_i` in `window` but discards them. Store their candle `open_time`s so markers land on the right bars.

- [ ] **Step 1: Write the failing test**

Append to `tests/strategies/test_ict_fvg_detector.py`:

```python
def test_detect_ict_fvg_stores_event_timestamps():
    candles = _bullish_ict_fvg_series()
    atr14 = [4.0] * len(candles)
    setup = detect_setup("BTCUSDT", candles, atr14)
    assert setup is not None
    ind = setup.indicators
    for key in ("sweep_time", "choch_time", "fvg_start_time", "retest_time"):
        assert key in ind, f"missing {key}"
        assert isinstance(ind[key], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategies/test_ict_fvg_detector.py::test_detect_ict_fvg_stores_event_timestamps -v`
Expected: FAIL with `assert 'sweep_time' in ind` → KeyError-style AssertionError.

- [ ] **Step 3: Add the timestamps in both branches**

In `_long_candidate`, extend the `indicators` dict (currently ending at the `tp_r` key, around line 154) to also include:

```python
                "sweep_time": window[sweep_i].open_time,
                "choch_time": window[choch_i].open_time,
                "fvg_start_time": window[max(fvg_i - 2, 0)].open_time,
                "retest_time": window[retest_i].open_time,
```

In `_short_candidate`, add the identical four lines to its `indicators` dict (same variable names — `sweep_i`, `choch_i`, `fvg_i`, `retest_i` are all in scope there too).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategies/test_ict_fvg_detector.py -v`
Expected: PASS (all existing tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/ict_fvg/detector.py tests/strategies/test_ict_fvg_detector.py
git commit -m "feat(chart): expose ict_fvg event timestamps for chart markers"
```

---

## Task 4: Chart plan builder (dispatcher + ict_fvg)

**Files:**
- Create: `signals/chart/plan.py`
- Test: `tests/chart/test_plan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_plan.py`:

```python
from signals.chart.plan import build_chart_plan
from signals.models import Signal


def _signal(indicators, direction="long"):
    return Signal(
        id="s1", symbol="XAUUSD", timeframe="5m", direction=direction,
        entry=2006.8, stop_loss=2001.8, take_profit=2009.3,
        take_profit_2=2011.8, take_profit_3=2014.3, confidence=72,
        rationale="r", indicators=indicators, news_headlines=[], created_at="t",
    )


def _kinds(plan, role):
    return [a for a in plan if a["role"] == role]


def test_plan_always_appends_trade_levels():
    plan = build_chart_plan([], _signal({"strategy": "sr_zone",
                                          "side": "support",
                                          "zone_low": 2000.0, "zone_high": 2003.0,
                                          "touches": 3}))
    assert _kinds(plan, "entry") and _kinds(plan, "stop")
    assert len(_kinds(plan, "target")) == 3  # TP1/TP2/TP3


def test_ict_fvg_plan_has_fvg_zone_and_markers():
    ind = {
        "strategy": "ict_fvg", "fvg_top": 2007.0, "fvg_bottom": 2005.7,
        "fvg_start_time": 190, "choch_level": 2008.0, "choch_time": 200,
        "sweep_level": 2004.5, "sweep_low": 2002.3, "sweep_time": 170,
        "retest_time": 230,
    }
    plan = build_chart_plan([], _signal(ind))
    fvg = _kinds(plan, "fvg")
    assert len(fvg) == 1 and fvg[0]["kind"] == "zone"
    markers = [a for a in plan if a["kind"] == "marker"]
    assert {m["order"] for m in markers} == {1, 2, 3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chart/test_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.plan'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/plan.py`:

```python
"""Turns a signal + candle window into a strategy-agnostic list of primitives.

Each strategy builder emits only its *structure* elements; entry/SL/TP levels
are appended by the dispatcher so every plan has them (DRY).
"""
from signals.chart.annotations import level, marker, series, zone
from signals.indicators import ema, lwma


def _trade_levels(signal):
    out = [
        level(signal.entry, "Entry", "entry"),
        level(signal.stop_loss, "SL", "stop", style="dashed"),
        level(signal.take_profit, "TP1", "target", style="dashed"),
    ]
    if signal.take_profit_2 is not None:
        out.append(level(signal.take_profit_2, "TP2", "target", style="dashed"))
    if signal.take_profit_3 is not None:
        out.append(level(signal.take_profit_3, "TP3", "target", style="dashed"))
    return out


def _ict_smc(candles, signal):
    ind = signal.indicators
    out = [
        level(ind["choch_level"], "CHoCH level", "choch",
              style="dashed", start_time=ind.get("choch_time")),
        level(ind["sweep_level"], "Swept liquidity", "liquidity",
              style="dotted", start_time=ind.get("sweep_time")),
    ]
    sweep_px = ind.get("sweep_low") if signal.direction == "long" else ind.get("sweep_high")
    if ind.get("sweep_time") is not None and sweep_px is not None:
        out.append(marker(ind["sweep_time"], sweep_px, "Liquidity sweep", "liquidity", 1))
    if ind.get("choch_time") is not None:
        out.append(marker(ind["choch_time"], ind["choch_level"], "CHoCH ✓", "choch", 2))
    return out


def _ict_fvg(candles, signal):
    ind = signal.indicators
    out = [zone(ind["fvg_top"], ind["fvg_bottom"], ind.get("fvg_start_time"),
                "Fair Value Gap", "fvg")]
    out.extend(_ict_smc(candles, signal))
    if ind.get("retest_time") is not None:
        out.append(marker(ind["retest_time"], signal.entry,
                          "FVG retest → entry", "entry", 3))
    return out


def _sr_zone(candles, signal):
    ind = signal.indicators
    label = f"{ind.get('side', 'S/R')} zone ({ind.get('touches', '?')}x)"
    return [zone(ind["zone_high"], ind["zone_low"], None, label, "sr")]


def _ema_cross(candles, signal):
    closes = [c.close for c in candles]
    ema9, ema21 = ema(closes, 9), ema(closes, 21)
    pts9 = [{"time": c.open_time, "value": v} for c, v in zip(candles, ema9)]
    pts21 = [{"time": c.open_time, "value": v} for c, v in zip(candles, ema21)]
    out = [series(pts9, "EMA9", "ema-fast"), series(pts21, "EMA21", "ema-slow")]
    ct = signal.indicators.get("cross_time")
    if ct is not None:
        out.append(marker(ct, signal.entry, "EMA cross", "entry", 1))
    return out


def _ce_lwma(candles, signal):
    ind = signal.indicators
    closes = [c.close for c in candles]
    pts = [{"time": c.open_time, "value": v} for c, v in zip(candles, lwma(closes, 200))]
    out = [series(pts, "LWMA200 (premium/discount)", "lwma")]
    if ind.get("ce_trail") is not None:
        out.append(level(ind["ce_trail"], "Chandelier trail", "trail", style="dashed"))
    return out


_BUILDERS = {
    "ict_fvg": _ict_fvg,
    "ict_smc": _ict_smc,
    "sr_zone": _sr_zone,
    "ema_cross": _ema_cross,
    "ce_lwma": _ce_lwma,
}


def _no_structure(candles, signal):
    return []


def build_chart_plan(candles, signal):
    """Return the full annotation list for one signal (structure + trade levels)."""
    ind = signal.indicators or {}
    strategy = ind.get("strategy")
    if strategy is None and "ema9" in ind:
        strategy = "ema_cross"  # ema_cross detector omits the "strategy" key
    builder = _BUILDERS.get(strategy, _no_structure)
    plan = list(builder(candles, signal))
    plan.extend(_trade_levels(signal))
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chart/test_plan.py -v`
Expected: PASS (2 passed). Note: `_ema_cross`/`_ce_lwma` get their own tests in Tasks 13/14; here they only need to import.

- [ ] **Step 5: Commit**

```bash
git add signals/chart/plan.py tests/chart/test_plan.py
git commit -m "feat(chart): build_chart_plan dispatcher + ict_fvg/ict_smc/sr_zone builders"
```

---

## Task 5: Renderer (mplfinance)

**Files:**
- Modify: `requirements.txt`
- Create: `signals/chart/render.py`
- Test: `tests/chart/test_render.py`

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt`:

```
mplfinance>=0.12
```

Then install it: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

Create `tests/chart/test_render.py`:

```python
from signals.chart.annotations import level, marker, series, zone
from signals.chart.render import render_chart
from signals.models import Candle, Signal

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _candles(n=60):
    out = []
    for i in range(n):
        base = 100 + i * 0.05
        out.append(Candle(open_time=i * 300000, open=base, high=base + 0.4,
                          low=base - 0.4, close=base + 0.1, volume=1.0))
    return out


def _signal():
    return Signal(id="s1", symbol="BTCUSD", timeframe="5m", direction="long",
                  entry=102.0, stop_loss=101.0, take_profit=103.0,
                  take_profit_2=104.0, take_profit_3=105.0, confidence=70,
                  rationale="r", indicators={}, news_headlines=[], created_at="t")


def test_render_chart_returns_png_bytes():
    candles = _candles()
    plan = [
        zone(102.5, 102.0, candles[40].open_time, "Fair Value Gap", "fvg"),
        level(102.0, "Entry", "entry"),
        level(101.0, "SL", "stop", style="dashed"),
        marker(candles[35].open_time, 101.2, "Liquidity sweep", "liquidity", 1),
        series([{"time": c.open_time, "value": c.close} for c in candles], "EMA9", "ema-fast"),
    ]
    png = render_chart(candles, plan, _signal())
    assert png[:8] == _PNG_MAGIC
    assert len(png) > 2000


def test_render_chart_handles_empty_plan():
    png = render_chart(_candles(), [], _signal())
    assert png[:8] == _PNG_MAGIC
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/chart/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.render'`

- [ ] **Step 4: Write the implementation**

Create `signals/chart/render.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/chart/test_render.py -v`
Expected: PASS (2 passed). Implementation note: right-edge label margins may need tuning when you eyeball a real render — that is cosmetic and does not block the test.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt signals/chart/render.py tests/chart/test_render.py
git commit -m "feat(chart): mplfinance annotated candlestick renderer"
```

---

## Task 6: Supabase Storage upload

**Files:**
- Create: `signals/chart/upload.py`
- Test: `tests/chart/test_upload.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_upload.py`:

```python
from signals.chart.upload import upload_chart


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "data": data})
        return _FakeResponse()


def test_upload_chart_posts_png_and_returns_public_url():
    session = _FakeSession()
    url = upload_chart(b"\x89PNG", "sig-123", "https://proj.supabase.co",
                       "service-key", session=session)
    call = session.calls[0]
    assert call["url"].endswith("/storage/v1/object/signal-charts/sig-123.png")
    assert call["headers"]["Content-Type"] == "image/png"
    assert call["data"] == b"\x89PNG"
    assert url == "https://proj.supabase.co/storage/v1/object/public/signal-charts/sig-123.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chart/test_upload.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.upload'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/upload.py`:

```python
"""Uploads a rendered chart PNG to Supabase Storage; returns the public URL."""
import requests

BUCKET = "signal-charts"


def upload_chart(png: bytes, signal_id: str, supabase_url: str,
                 service_key: str, session=None) -> str:
    """Upsert `{signal_id}.png` into the public bucket; return its public URL."""
    session = session or requests.Session()
    path = f"{signal_id}.png"
    response = session.post(
        f"{supabase_url}/storage/v1/object/{BUCKET}/{path}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
        data=png,
        timeout=20,
    )
    response.raise_for_status()
    return f"{supabase_url}/storage/v1/object/public/{BUCKET}/{path}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chart/test_upload.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add signals/chart/upload.py tests/chart/test_upload.py
git commit -m "feat(chart): upload rendered chart to Supabase Storage"
```

---

## Task 7: Signal model fields

**Files:**
- Modify: `signals/models.py` (`Signal` dataclass, after `take_profit_3`)
- Test: `tests/core/test_models_chart_fields.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_models_chart_fields.py`:

```python
from dataclasses import asdict, replace

from signals.models import (
    CandidateSetup, Confirmation, make_signal,
)


def _signal():
    setup = CandidateSetup("BTCUSD", "long", 100.0, 99.0, 101.0,
                           {"strategy": "ict_fvg"}, take_profit_2=102.0,
                           take_profit_3=103.0)
    return make_signal(setup, Confirmation("confirm", 70, "ok"), [], timeframe="5m")


def test_make_signal_defaults_chart_fields_to_none():
    signal = _signal()
    assert signal.chart_url is None
    assert signal.chart_data is None


def test_signal_asdict_includes_chart_fields():
    signal = replace(_signal(), chart_url="http://x/y.png",
                     chart_data={"plan": []})
    payload = asdict(signal)
    assert payload["chart_url"] == "http://x/y.png"
    assert payload["chart_data"] == {"plan": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_models_chart_fields.py -v`
Expected: FAIL with `AttributeError: 'Signal' object has no attribute 'chart_url'`

- [ ] **Step 3: Add the fields**

In `signals/models.py`, in the `Signal` dataclass, add two fields immediately after `take_profit_3: float | None = None`:

```python
    chart_url: str | None = None
    chart_data: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_models_chart_fields.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add signals/models.py tests/core/test_models_chart_fields.py
git commit -m "feat(chart): add chart_url/chart_data to Signal"
```

---

## Task 8: Pipeline attach (non-fatal)

**Files:**
- Create: `signals/chart/pipeline.py`
- Modify: `signals/run.py` (after line 495, before the `save_signal` try-block)
- Test: `tests/chart/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_pipeline.py`:

```python
import signals.chart.pipeline as pipeline
from signals.models import Signal


def _signal():
    return Signal(id="s1", symbol="XAUUSD", timeframe="5m", direction="long",
                  entry=100.0, stop_loss=99.0, take_profit=101.0,
                  take_profit_2=None, take_profit_3=None, confidence=70,
                  rationale="r", indicators={"strategy": "ict_fvg"},
                  news_headlines=[], created_at="t")


def test_attach_chart_sets_url_on_success(monkeypatch):
    monkeypatch.setattr(pipeline, "build_chart_plan", lambda c, s: [{"kind": "level"}])
    monkeypatch.setattr(pipeline, "render_chart", lambda c, p, s: b"PNG")
    monkeypatch.setattr(pipeline, "upload_chart",
                        lambda png, sid, url, key, session=None: "http://x/s1.png")
    out = pipeline.attach_chart(_signal(), [], supabase_url="u", service_key="k")
    assert out.chart_url == "http://x/s1.png"
    assert out.chart_data["plan"] == [{"kind": "level"}]


def test_attach_chart_swallows_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("render exploded")
    monkeypatch.setattr(pipeline, "build_chart_plan", lambda c, s: [])
    monkeypatch.setattr(pipeline, "render_chart", _boom)
    out = pipeline.attach_chart(_signal(), [], supabase_url="u", service_key="k")
    assert out.chart_url is None  # signal survives, text-only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chart/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.pipeline'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/pipeline.py`:

```python
"""Attaches a rendered chart to a signal. Never raises: a chart failure must
never cost a signal, so any error falls back to a text-only (chart_url=None)
signal."""
import dataclasses

from signals.chart.plan import build_chart_plan
from signals.chart.render import render_chart
from signals.chart.upload import upload_chart

SNAPSHOT_BARS = 60


def _snapshot(candles):
    return [
        {"t": c.open_time, "o": c.open, "h": c.high, "l": c.low, "c": c.close}
        for c in candles[-SNAPSHOT_BARS:]
    ]


def attach_chart(signal, candles, *, supabase_url, service_key, session=None):
    """Return a copy of `signal` with chart_url + chart_data set, or the
    original signal unchanged if rendering/upload fails."""
    try:
        plan = build_chart_plan(candles, signal)
        png = render_chart(candles, plan, signal)
        url = upload_chart(png, signal.id, supabase_url, service_key, session=session)
        return dataclasses.replace(
            signal, chart_url=url,
            chart_data={"plan": plan, "candles": _snapshot(candles)},
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad; charts are best-effort
        print(f"[{signal.symbol}] chart render/upload failed "
              f"({type(exc).__name__}: {exc}), sending text-only")
        return signal
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chart/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Wire it into `scan_symbol`**

In `signals/run.py`, add the import near the other signals imports (top of file):

```python
from signals.chart.pipeline import attach_chart
```

Then in `scan_symbol`, immediately after line 495 (`signal = make_signal(...)`) and before the `try:` block that calls `save_signal`, insert:

```python
    signal = attach_chart(
        signal, candles,
        supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
        session=session,
    )
```

- [ ] **Step 6: Verify the engine still passes its tests**

Run: `pytest tests/core/test_pipeline.py tests/core/test_xau_scan.py -v`
Expected: PASS. The autouse `conftest` fixture stubs `save_signal`; `attach_chart` runs for real but swallows any error, so no network calls escape (upload will fail against the fake Supabase URL and fall back to chart_url=None — which is the intended safe behavior). If a test asserts an exact stored payload, update it to tolerate `chart_url`/`chart_data`.

- [ ] **Step 7: Commit**

```bash
git add signals/chart/pipeline.py signals/run.py tests/chart/test_pipeline.py
git commit -m "feat(chart): attach chart to signal in scan_symbol (non-fatal)"
```

---

## Task 9: Telegram photo delivery

**Files:**
- Modify: `signals/telegram_client.py` (`format_caption`, `send_photo`, `send_alert`)
- Test: `tests/core/test_telegram.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_telegram.py`:

```python
from signals.models import Signal
from signals.telegram_client import format_caption, send_alert


def _signal(chart_url=None):
    return Signal(id="s1", symbol="XAUUSD", timeframe="5m", direction="long",
                  entry=2006.8, stop_loss=2001.8, take_profit=2009.3,
                  take_profit_2=2011.8, take_profit_3=2014.3, confidence=72,
                  rationale="x" * 2000, indicators={}, news_headlines=[],
                  created_at="t", chart_url=chart_url)


class _Rec:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})

        class _R:
            status_code = 200

            def raise_for_status(self_inner):
                return None
        return _R()


def test_caption_stays_under_telegram_limit():
    assert len(format_caption(_signal())) <= 1024


def test_send_alert_uses_photo_when_chart_present():
    rec = _Rec()
    send_alert(_signal(chart_url="http://x/s1.png"), "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    assert rec.calls[0]["json"]["photo"] == "http://x/s1.png"


def test_send_alert_falls_back_to_message_without_chart():
    rec = _Rec()
    send_alert(_signal(chart_url=None), "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendMessage")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_telegram.py -k "caption or photo or fallback" -v`
Expected: FAIL with `ImportError: cannot import name 'format_caption'`

- [ ] **Step 3: Write the implementation**

In `signals/telegram_client.py`, add `format_caption` after `format_alert` (reuses existing `_esc`, `_price`, `_direction_dot`, `_risk_reward`):

```python
def format_caption(signal: Signal) -> str:
    """Compact <=1024-char caption for the chart photo. The image carries the
    'why', so the long analysis text is dropped here."""
    direction = signal.direction.upper()
    dot = _direction_dot(signal.direction)
    tp2 = signal.take_profit_2 or signal.take_profit
    tp3 = signal.take_profit_3 or signal.take_profit
    return (
        f"{dot} <b>{direction} SIGNAL</b>\n"
        f"💹 <b>{_esc(signal.symbol)}</b> · <code>{_esc(signal.timeframe)}</code>\n"
        f"🎯 Confidence {signal.confidence}%\n"
        f"📍 Entry {_price(signal.entry)}  🛑 SL {_price(signal.stop_loss)}\n"
        f"🎯 TP {_price(signal.take_profit)} / {_price(tp2)} / {_price(tp3)}\n"
        f"⚖️ R:R {_risk_reward(signal.entry, signal.stop_loss, tp3)}"
    )


def send_photo(photo_url: str, caption: str, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one photo message; raises on failure so the caller can retry."""
    session = session or requests.Session()
    response = session.post(
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = (response.json() or {}).get("description") or ""
        except Exception:
            detail = (response.text or "")[:200]
        raise requests.HTTPError(
            f"{response.status_code} Telegram photo failed"
            + (f": {detail}" if detail else ""),
            response=response,
        )
    response.raise_for_status()
```

Then replace the existing `send_alert` body:

```python
def send_alert(signal: Signal, bot_token: str, chat_id: str,
               session=None) -> None:
    """Send one confirmed-signal alert — a photo when a chart was rendered,
    otherwise the text message."""
    if getattr(signal, "chart_url", None):
        send_photo(signal.chart_url, format_caption(signal), bot_token, chat_id,
                   session=session)
    else:
        send_message(format_alert(signal), bot_token, chat_id, session=session)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_telegram.py -v`
Expected: PASS (all existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add signals/telegram_client.py tests/core/test_telegram.py
git commit -m "feat(chart): Telegram sends chart photo with compact caption"
```

---

## Task 10: Web dashboard display

**Files:**
- Modify: `web/src/lib/signals.ts` (`Signal`, `SignalRow`, `parseRow`)
- Modify: `web/src/components/dashboard/SignalsGrid.tsx`

**Before writing web code:** read `web/AGENTS.md` — this repo pins a Next.js version with breaking changes; consult `web/node_modules/next/dist/docs/` before using any Next.js-specific API. The change below uses a plain `<img>` (no `next/image`) to stay framework-neutral.

- [ ] **Step 1: Add `chartUrl` to the types**

In `web/src/lib/signals.ts`, add to the `Signal` type (after `status`):

```typescript
  chartUrl: string | null;
```

Add to the `SignalRow` type (after `status?`):

```typescript
  chart_url?: string | null;
```

- [ ] **Step 2: Map it in `parseRow`**

In `parseRow` (the object returned around line 239–247), add:

```typescript
    chartUrl: typeof row.chart_url === "string" ? row.chart_url : null,
```

The fetch queries use `select=*`, so no query change is needed — the column arrives automatically.

- [ ] **Step 3: Render the image in the card**

In `web/src/components/dashboard/SignalsGrid.tsx`, in the expanded detail view (near the `AI rationale` block around line 339), add before the rationale:

```tsx
{signal.chartUrl && (
  <div className="mt-4">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-2">
      Setup chart
    </p>
    <img
      src={signal.chartUrl}
      alt={`${signal.symbol} ${signal.timeframe} ${signal.direction} setup`}
      loading="lazy"
      className="w-full rounded-lg border border-slate/15"
    />
  </div>
)}
```

- [ ] **Step 4: Verify the web build**

Run: `cd web && npm run lint && npm run build`
Expected: lint clean, build succeeds. Manually confirm a signal with a `chart_url` shows the image and one without still renders the text-only card (no broken image).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/signals.ts web/src/components/dashboard/SignalsGrid.tsx
git commit -m "feat(chart): show setup chart image on dashboard signal cards"
```

---

## Task 11: ict_smc detector timestamps + verify builder

**Files:**
- Modify: `signals/strategies/ict_smc/detector.py` (both `indicators` dicts)
- Test: `tests/strategies/test_ict_detector.py`, `tests/chart/test_plan.py`

The `_ict_smc` plan builder (Task 4) already reads `choch_time`, `sweep_time`, `sweep_low`/`sweep_high`. The bullish branch already stores `sweep_low` and the bearish branch already stores `sweep_high`; we only need to add the two timestamps to both dicts. Both branches have `sweep_i`, `choch_i`, and `bar` in scope.

- [ ] **Step 1: Write the failing test**

Append to `tests/chart/test_plan.py`:

```python
def test_ict_smc_plan_has_structure_markers():
    ind = {"strategy": "ict_smc", "choch_level": 101.0, "choch_time": 200,
           "sweep_level": 99.0, "sweep_low": 98.5, "sweep_time": 170}
    plan = build_chart_plan([], _signal(ind))
    markers = [a for a in plan if a["kind"] == "marker"]
    assert {m["order"] for m in markers} == {1, 2}
    assert not [a for a in plan if a["role"] == "fvg"]  # ict_smc draws no FVG
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chart/test_plan.py::test_ict_smc_plan_has_structure_markers -v`
Expected: PASS already if the builder is correct — but the *detector* must emit these keys in production. Continue to wire the detector so real signals carry them.

- [ ] **Step 3: Add timestamps in both detector branches**

In `signals/strategies/ict_smc/detector.py`, in the **bullish** `indicators` dict (`"structure": "bullish_choch"`, around line 125), add these two lines after `"sweep_low": bar.low,`:

```python
            "sweep_time": window[sweep_i].open_time,
            "choch_time": window[choch_i].open_time,
```

In the **bearish** `indicators` dict (`"structure": "bearish_choch"`, around line 174), add the same two lines after `"sweep_high": bar.high,`:

```python
            "sweep_time": window[sweep_i].open_time,
            "choch_time": window[choch_i].open_time,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategies/test_ict_detector.py tests/chart/test_plan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/ict_smc/detector.py tests/chart/test_plan.py
git commit -m "feat(chart): expose ict_smc event timestamps for chart markers"
```

---

## Task 12: sr_zone builder test

**Files:**
- Test: `tests/chart/test_plan.py`

`sr_zone` needs no detector change (its `zone_low`/`zone_high`/`side`/`touches` already exist and the box spans full width). Lock the builder behavior with a test.

- [ ] **Step 1: Write the test**

Append to `tests/chart/test_plan.py`:

```python
def test_sr_zone_plan_has_full_width_zone():
    ind = {"strategy": "sr_zone", "side": "support", "zone_low": 2000.0,
           "zone_high": 2003.0, "touches": 3}
    plan = build_chart_plan([], _signal(ind))
    zones = [a for a in plan if a["role"] == "sr"]
    assert len(zones) == 1
    assert zones[0]["start_time"] is None  # full chart width
    assert "support" in zones[0]["label"]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/chart/test_plan.py::test_sr_zone_plan_has_full_width_zone -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/chart/test_plan.py
git commit -m "test(chart): lock sr_zone chart plan"
```

---

## Task 13: ema_cross detector cross timestamp + builder test

**Files:**
- Modify: `signals/strategies/ema_cross/detector.py` (the `indicators` dict)
- Test: `tests/chart/test_plan.py`

The `_ema_cross` builder recomputes EMA9/EMA21 from candles and adds a cross marker when `indicators["cross_time"]` is present. The detector computes `cross_up`/`cross_down` indices (relative to `candles`) — store the crossing bar's `open_time`. The `indicators` dict is built once (around line 71) before both branches, so we assign `cross_time` inside whichever branch fires.

- [ ] **Step 1: Write the failing test**

Append to `tests/chart/test_plan.py`:

```python
from signals.models import Candle as _Candle


def test_ema_cross_plan_has_ema_series():
    candles = [_Candle(open_time=i, open=100, high=101, low=99, close=100 + i * 0.1,
                       volume=1.0) for i in range(30)]
    ind = {"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.2,
           "cross_time": candles[25].open_time}
    plan = build_chart_plan(candles, _signal(ind))
    series_roles = {a["role"] for a in plan if a["kind"] == "series"}
    assert series_roles == {"ema-fast", "ema-slow"}
    assert any(a["kind"] == "marker" and a["time"] == candles[25].open_time for a in plan)
```

- [ ] **Step 2: Run test to verify it passes at the plan layer**

Run: `pytest tests/chart/test_plan.py::test_ema_cross_plan_has_ema_series -v`
Expected: PASS (builder already handles this). The detector wiring below makes real signals carry `cross_time`.

- [ ] **Step 3: Store `cross_time` in the detector**

In `signals/strategies/ema_cross/detector.py`, in the **long** branch, add this line right after `tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "long")` (around line 96), before the `return CandidateSetup(... "long" ...)`:

```python
        indicators["cross_time"] = candles[cross_up].open_time
```

In the **short** branch, add this line right after `tp1, tp2, tp3 = take_profits_from_risk(entry, stop, "short")` (around line 113), before the `return CandidateSetup(... "short" ...)`:

```python
        indicators["cross_time"] = candles[cross_down].open_time
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategies/test_setup_detector.py tests/chart/test_plan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add signals/strategies/ema_cross/detector.py tests/chart/test_plan.py
git commit -m "feat(chart): expose ema_cross crossing timestamp for chart marker"
```

---

## Task 14: ce_lwma builder test + full-suite green

**Files:**
- Test: `tests/chart/test_plan.py`

`ce_lwma` needs no detector change (`ce_trail` exists; LWMA200 is recomputed). Lock its builder, then run the whole suite.

- [ ] **Step 1: Write the test**

Append to `tests/chart/test_plan.py`:

```python
def test_ce_lwma_plan_has_lwma_and_trail():
    candles = [_Candle(open_time=i, open=100, high=101, low=99, close=100,
                       volume=1.0) for i in range(210)]
    ind = {"strategy": "ce_lwma", "ce_trail": 99.5, "lwma200": 100.0,
           "zone": "discount"}
    plan = build_chart_plan(candles, _signal(ind))
    assert any(a["kind"] == "series" and a["role"] == "lwma" for a in plan)
    assert any(a["role"] == "trail" for a in plan)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/chart/test_plan.py::test_ce_lwma_plan_has_lwma_and_trail -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `pytest`
Expected: all tests PASS. Fix any test that asserted an exact stored-signal payload but now also sees `chart_url`/`chart_data`.

- [ ] **Step 4: Commit**

```bash
git add tests/chart/test_plan.py
git commit -m "test(chart): lock ce_lwma chart plan; full suite green"
```

---

## Definition of Done

- Every confirmed signal in `run.py` and `xau_scan.py` attempts a chart; a failure never blocks the signal.
- Telegram sends a photo + compact caption when a chart exists, text otherwise.
- The dashboard shows the setup image on cards that have one.
- All five strategies emit their own structure elements (FVG/CHoCH/sweep, S/R zone, EMA lines, LWMA/trail) plus entry/SL/TP.
- `chart_data` (plan + candle snapshot) is stored for the future interactive web chart.
- `pytest` is green; `cd web && npm run build` succeeds.
