# Outcome Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a signal closes terminal (TP3 win or SL loss), render a chart of the setup context + real price path + per-target fills + HIT/STOP flag, attach it to the Telegram outcome alert, and store `outcome_chart_url` for the dashboard.

**Architecture:** Reuse the `signals/chart/` package. A new pure `outcome_plan` builder emits annotation primitives; a thin `render_outcome_chart` shares the existing renderer's base plot; a non-fatal `attach_outcome_chart` wires into `outcome_tracker.track_open_signals` right where outcome alerts fire; `send_outcome_alert` gains a photo-or-text branch.

**Tech Stack:** Python 3.12, mplfinance/matplotlib, Supabase Storage/PostgREST, Telegram Bot API, Next.js/React (web).

---

## File Structure

**Create:**
- `signals/chart/outcome_plan.py` — `first_cross`, `merge_outcome_candles`, `build_outcome_plan`.
- `signals/chart/outcome_pipeline.py` — `attach_outcome_chart` (non-fatal wrapper).
- `tests/chart/test_outcome_plan.py`, `tests/chart/test_outcome_render.py`, `tests/chart/test_outcome_pipeline.py`.

**Modify:**
- `supabase/schema.sql` — `outcome_chart_url` column.
- `signals/chart/render.py` — extract `_base_plot`/`_to_png`; add `render_outcome_chart` + `win`/`loss` color roles.
- `signals/chart/upload.py` — optional `suffix` param.
- `signals/storage.py` — `set_outcome_chart_url`; add `chart_data` to `list_open_signals` select.
- `signals/outcome_tracker.py` — render+persist+send on terminal outcomes.
- `signals/telegram_client.py` — `send_outcome_alert` photo-or-text.
- `tests/conftest.py` — inert outcome-chart stubs.
- `web/src/lib/signals.ts`, `web/src/components/dashboard/SignalsGrid.tsx` — show the outcome image.

---

## Task 1: DB column

**Files:** Modify `supabase/schema.sql` (append at end)

- [ ] **Step 1: Append the migration SQL**

Add to the end of `supabase/schema.sql`:

```sql
-- Outcome charts: PNG of how a closed trade played out (TP3 win / SL loss).
alter table public.signals add column if not exists outcome_chart_url text;
```

- [ ] **Step 2: Apply it to Supabase**

Run the appended SQL in the Supabase SQL editor. Verify: `select column_name from information_schema.columns where table_name='signals' and column_name='outcome_chart_url';` returns one row.

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(outcome-chart): add outcome_chart_url column"
```

---

## Task 2: Outcome plan builder

**Files:**
- Create: `signals/chart/outcome_plan.py`
- Test: `tests/chart/test_outcome_plan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_outcome_plan.py`:

```python
from signals.models import Candle
from signals.chart.outcome_plan import (
    first_cross, merge_outcome_candles, build_outcome_plan,
)


def _c(t, o, h, l, c):
    return Candle(open_time=t, open=o, high=h, low=l, close=c, volume=0.0)


def test_first_cross_long_and_short():
    ups = [_c(1, 100, 100.5, 99.5, 100), _c(2, 100, 102, 100, 101.5)]
    assert first_cross(ups, 101.0, "long", "tp") == 2
    assert first_cross(ups, 99.0, "long", "sl") is None
    downs = [_c(1, 100, 100.5, 99.5, 100), _c(2, 100, 100, 98, 98.5)]
    assert first_cross(downs, 98.5, "short", "tp") == 2
    assert first_cross(downs, 101.0, "short", "sl") is None


def test_merge_dedupes_sorts_and_finds_entry_time():
    chart_data = {"candles": [{"t": 1, "o": 1, "h": 2, "l": 0, "c": 1},
                              {"t": 2, "o": 1, "h": 2, "l": 0, "c": 1}]}
    window = [_c(2, 5, 6, 4, 5), _c(3, 5, 6, 4, 5)]  # t=2 overlaps -> window wins
    merged, entry_time = merge_outcome_candles(chart_data, window)
    assert [c.open_time for c in merged] == [1, 2, 3]
    assert merged[1].close == 5  # window candle won the t=2 collision
    assert entry_time == 2  # last snapshot candle


def test_merge_without_snapshot_falls_back_to_window():
    window = [_c(10, 1, 2, 0, 1), _c(11, 1, 2, 0, 1)]
    merged, entry_time = merge_outcome_candles(None, window)
    assert [c.open_time for c in merged] == [10, 11]
    assert entry_time == 10


def _win_row():
    return {"symbol": "XAUUSD", "timeframe": "5m", "direction": "long",
            "entry": 100.0, "stop_loss": 98.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0}


def _rising_candles():
    # entry at t=0 (100), rising through 101,102,103
    return [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 101.2, 100, 101),
            _c(2, 101, 102.2, 101, 102), _c(3, 102, 103.2, 102, 103)]


def test_build_outcome_plan_win_has_ticks_flag_and_zone():
    plan = build_outcome_plan(_win_row(), "tp3_hit", _rising_candles(), 0)
    roles = [a["role"] for a in plan]
    assert roles.count("target") >= 3  # TP1/TP2/TP3 levels
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "TP1 ✓" in labels and "TP2 ✓" in labels and "✅ TP3 HIT" in labels
    assert any(a["kind"] == "zone" and a["role"] == "win" for a in plan)


def test_build_outcome_plan_loss_shows_partial_and_stop():
    row = _win_row()
    # rise through TP1 then drop to SL
    candles = [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 101.2, 100, 101),
               _c(2, 101, 101, 97.5, 98)]
    plan = build_outcome_plan(row, "sl_hit", candles, 0)
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "TP1 ✓" in labels  # honest: banked TP1 before reversing
    assert "🛑 SL HIT" in labels
    assert any(a["kind"] == "zone" and a["role"] == "loss" for a in plan)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.outcome_plan'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/outcome_plan.py`:

```python
"""Builds the annotation plan + merged candles for an outcome (result) chart."""
from signals.chart.annotations import level, marker, zone
from signals.models import Candle


def first_cross(candles, level_price, direction, kind):
    """open_time of the first candle to cross `level_price`, else None.

    kind "tp": long hits when high >= level, short when low <= level.
    kind "sl": long hits when low <= level, short when high >= level.
    """
    for c in candles:
        if kind == "tp":
            hit = c.high >= level_price if direction == "long" else c.low <= level_price
        else:
            hit = c.low <= level_price if direction == "long" else c.high >= level_price
        if hit:
            return c.open_time
    return None


def _snapshot_candles(chart_data):
    snap = (chart_data or {}).get("candles") or []
    return [Candle(open_time=c["t"], open=c["o"], high=c["h"], low=c["l"],
                   close=c["c"], volume=0.0) for c in snap]


def merge_outcome_candles(chart_data, window):
    """Merge the stored setup snapshot with the price-path `window`.

    Deduped by open_time (window wins collisions) and sorted. Returns
    (candles, entry_time) where entry_time is the last snapshot candle's
    open_time, or the first window candle's when there is no snapshot.
    """
    setup = _snapshot_candles(chart_data)
    by_time = {}
    for c in setup + list(window):
        by_time[c.open_time] = c
    merged = [by_time[t] for t in sorted(by_time)]
    entry_time = setup[-1].open_time if setup else (window[0].open_time if window else None)
    return merged, entry_time


def _tp_levels(row):
    tp1 = row.get("take_profit_1") if row.get("take_profit_1") is not None else row.get("take_profit")
    return (
        float(tp1) if tp1 is not None else None,
        float(row["take_profit_2"]) if row.get("take_profit_2") is not None else None,
        float(row["take_profit_3"]) if row.get("take_profit_3") is not None else None,
    )


def build_outcome_plan(signal_row, outcome, candles, entry_time):
    """Annotation list for an outcome chart: entry/SL/TP levels, per-target ✓
    marks, the HIT/STOP flag, and the captured-move (win) or loss zone."""
    direction = signal_row["direction"]
    entry = float(signal_row["entry"])
    stop = float(signal_row["stop_loss"])
    tp1, tp2, tp3 = _tp_levels(signal_row)

    plan = [level(entry, "Entry", "entry"),
            level(stop, "SL", "stop", style="dashed")]
    for lvl, lbl in ((tp1, "TP1"), (tp2, "TP2"), (tp3, "TP3")):
        if lvl is not None:
            plan.append(level(lvl, lbl, "target", style="dashed"))

    post = [c for c in candles if c.open_time >= entry_time]
    win = outcome in ("tp3_hit", "tp_hit")

    for lvl, lbl in ((tp1, "TP1 ✓"), (tp2, "TP2 ✓")):
        if lvl is None:
            continue
        t = first_cross(post, lvl, direction, "tp")
        if t is not None:
            plan.append(marker(t, lvl, lbl, "target"))

    if win:
        top = tp3 if tp3 is not None else tp1
        t = first_cross(post, top, direction, "tp")
        if t is not None:
            plan.append(marker(t, top, "✅ TP3 HIT", "win"))
        plan.append(zone(top, entry, entry_time, "Captured move", "win"))
    else:
        t = first_cross(post, stop, direction, "sl")
        if t is not None:
            plan.append(marker(t, stop, "🛑 SL HIT", "loss"))
        plan.append(zone(entry, stop, entry_time, "Loss", "loss"))

    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_plan.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add signals/chart/outcome_plan.py tests/chart/test_outcome_plan.py
git commit -m "feat(outcome-chart): outcome plan builder + candle merge"
```

---

## Task 3: Outcome renderer (shared base plot)

**Files:**
- Modify: `signals/chart/render.py`
- Test: `tests/chart/test_outcome_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_outcome_render.py`:

```python
from signals.chart.outcome_plan import build_outcome_plan
from signals.chart.render import render_outcome_chart
from signals.models import Candle

_PNG = b"\x89PNG\r\n\x1a\n"


def _c(t, o, h, l, c):
    return Candle(open_time=t, open=o, high=h, low=l, close=c, volume=0.0)


def _row():
    return {"symbol": "XAUUSD", "timeframe": "5m", "direction": "long",
            "entry": 100.0, "stop_loss": 98.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0}


def _candles(n=30):
    out = []
    for i in range(n):
        base = 99 + i * 0.15
        out.append(_c(i * 300000, base, base + 0.3, base - 0.3, base + 0.1))
    return out


def test_render_outcome_chart_returns_png():
    candles = _candles()
    plan = build_outcome_plan(_row(), "tp3_hit", candles, candles[5].open_time)
    png = render_outcome_chart(candles, plan, _row(), candles[5].open_time, "tp3_hit")
    assert png[:8] == _PNG and len(png) > 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_outcome_chart'`

- [ ] **Step 3: Refactor + add the outcome renderer**

In `signals/chart/render.py`:

(a) Add `win`/`loss` to the color maps. Change `ROLE_LINE` and `ROLE_FILL` to include the new roles:

```python
ROLE_LINE = {
    "choch": "#a78bfa", "liquidity": "#f59e0b", "entry": "#e2e8f0",
    "stop": "#fb7185", "target": "#34d399", "trail": "#f59e0b",
    "ema-fast": "#38bdf8", "ema-slow": "#f59e0b", "lwma": "#a78bfa",
    "win": "#34d399", "loss": "#fb7185",
}
ROLE_FILL = {"fvg": "#14b8a6", "sr": "#38bdf8", "premium": "#fb7185",
             "discount": "#2dd4bf", "win": "#34d399", "loss": "#fb7185"}
```

(b) Extract the base plot and PNG helpers, and rewrite `render_chart` to use them. Replace the entire existing `render_chart` function with:

```python
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
    tag = "✅ TP3 HIT" if win else "🛑 SL HIT"
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
```

Note: the old `render_chart` body ended by building a `BytesIO`, calling `fig.savefig(...)`, `plt.close(fig)`, and returning `buf.getvalue()`. That logic now lives in `_to_png`. Make sure no duplicate leftover `render_chart` remains.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_render.py tests/chart/test_render.py -v`
Expected: PASS (the new outcome test AND the existing `render_chart` tests — the refactor is behavior-preserving).

- [ ] **Step 5: Commit**

```bash
git add signals/chart/render.py tests/chart/test_outcome_render.py
git commit -m "feat(outcome-chart): render_outcome_chart on shared base plot"
```

---

## Task 4: upload_chart suffix param

**Files:**
- Modify: `signals/chart/upload.py`
- Test: `tests/chart/test_upload.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/chart/test_upload.py`:

```python
def test_upload_chart_suffix_changes_object_key():
    from signals.chart.upload import upload_chart

    class _Resp:
        status_code = 200
        def raise_for_status(self):
            return None

    class _Sess:
        def __init__(self):
            self.calls = []
        def post(self, url, headers=None, data=None, timeout=None):
            self.calls.append(url)
            return _Resp()

    s = _Sess()
    url = upload_chart(b"\x89PNG", "sig-9", "https://p.supabase.co", "k",
                       session=s, suffix="-outcome")
    assert s.calls[0].endswith("/signal-charts/sig-9-outcome.png")
    assert url.endswith("/public/signal-charts/sig-9-outcome.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_upload.py::test_upload_chart_suffix_changes_object_key -v`
Expected: FAIL with `TypeError: upload_chart() got an unexpected keyword argument 'suffix'`

- [ ] **Step 3: Add the param**

In `signals/chart/upload.py`, change the `upload_chart` signature and the `path` line:

```python
def upload_chart(png: bytes, signal_id: str, supabase_url: str,
                 service_key: str, session=None, suffix: str = "") -> str:
    """Upsert `{signal_id}{suffix}.png` into the public bucket; return its URL."""
    session = session or requests.Session()
    path = f"{signal_id}{suffix}.png"
```

(The rest of the function body — headers, POST, return — is unchanged; it already uses `path`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/chart/test_upload.py -v`
Expected: PASS (existing test + the new one).

- [ ] **Step 5: Commit**

```bash
git add signals/chart/upload.py tests/chart/test_upload.py
git commit -m "feat(outcome-chart): upload_chart suffix for -outcome key"
```

---

## Task 5: storage setter + open-signal select

**Files:**
- Modify: `signals/storage.py`
- Test: `tests/core/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_storage.py`:

```python
def test_set_outcome_chart_url_patches_row():
    from signals.storage import set_outcome_chart_url

    class _Resp:
        status_code = 200
        def raise_for_status(self):
            return None

    class _Sess:
        def __init__(self):
            self.calls = []
        def patch(self, url, headers=None, json=None, timeout=None):
            self.calls.append({"url": url, "json": json})
            return _Resp()

    s = _Sess()
    set_outcome_chart_url("sig-1", "http://x/sig-1-outcome.png",
                          "https://p.supabase.co", "key", session=s)
    assert "id=eq.sig-1" in s.calls[0]["url"]
    assert s.calls[0]["json"] == {"outcome_chart_url": "http://x/sig-1-outcome.png"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_storage.py::test_set_outcome_chart_url_patches_row -v`
Expected: FAIL with `ImportError: cannot import name 'set_outcome_chart_url'`

- [ ] **Step 3: Add the setter and widen the open-signals select**

In `signals/storage.py`, add this function (place it right after `update_signal_outcome`):

```python
def set_outcome_chart_url(signal_id: str, url: str, supabase_url: str,
                          service_key: str, session=None) -> None:
    """PATCH just the outcome_chart_url on one signal row."""
    session = session or requests.Session()
    response = session.patch(
        f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"outcome_chart_url": url},
        timeout=15,
    )
    response.raise_for_status()
```

Then, in `list_open_signals`, add `chart_data` to the `select=` column list so the outcome renderer can use the stored setup snapshot. Change the select fragment from:

```python
            "take_profit,take_profit_1,take_profit_2,take_profit_3,"
            "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at"
```

to:

```python
            "take_profit,take_profit_1,take_profit_2,take_profit_3,"
            "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,chart_data"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_storage.py -v`
Expected: PASS (existing storage tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add signals/storage.py tests/core/test_storage.py
git commit -m "feat(outcome-chart): set_outcome_chart_url + chart_data in open select"
```

---

## Task 6: Non-fatal attach_outcome_chart

**Files:**
- Create: `signals/chart/outcome_pipeline.py`
- Test: `tests/chart/test_outcome_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/chart/test_outcome_pipeline.py`:

```python
import signals.chart.outcome_pipeline as op
from signals.models import Candle


def _c(t):
    return Candle(open_time=t, open=1, high=2, low=0, close=1, volume=0.0)


def _row():
    return {"id": "s1", "symbol": "XAUUSD", "timeframe": "5m",
            "direction": "long", "entry": 100.0, "stop_loss": 98.0,
            "take_profit_1": 101.0, "take_profit_2": 102.0, "take_profit_3": 103.0,
            "chart_data": {"candles": [{"t": 0, "o": 1, "h": 2, "l": 0, "c": 1}]}}


def test_attach_outcome_chart_returns_url_on_success(monkeypatch):
    monkeypatch.setattr(op, "build_outcome_plan", lambda *a, **k: [{"kind": "level"}])
    monkeypatch.setattr(op, "render_outcome_chart", lambda *a, **k: b"PNG")
    monkeypatch.setattr(op, "upload_chart",
                        lambda png, sid, url, key, session=None, suffix="": f"http://x/{sid}{suffix}.png")
    got = op.attach_outcome_chart(_row(), "tp3_hit", [_c(1)],
                                  supabase_url="u", service_key="k")
    assert got == "http://x/s1-outcome.png"


def test_attach_outcome_chart_swallows_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("render exploded")
    monkeypatch.setattr(op, "render_outcome_chart", _boom)
    got = op.attach_outcome_chart(_row(), "sl_hit", [_c(1)],
                                  supabase_url="u", service_key="k")
    assert got is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signals.chart.outcome_pipeline'`

- [ ] **Step 3: Write the implementation**

Create `signals/chart/outcome_pipeline.py`:

```python
"""Renders + uploads an outcome chart. Never raises: a chart failure must
never drop or delay the outcome alert."""
from signals.chart.outcome_plan import build_outcome_plan, merge_outcome_candles
from signals.chart.render import render_outcome_chart
from signals.chart.upload import upload_chart


def attach_outcome_chart(signal_row, outcome, window, *, supabase_url,
                         service_key, session=None):
    """Return the uploaded outcome-chart URL, or None if anything fails."""
    try:
        candles, entry_time = merge_outcome_candles(
            signal_row.get("chart_data"), window)
        if not candles or entry_time is None:
            return None
        plan = build_outcome_plan(signal_row, outcome, candles, entry_time)
        png = render_outcome_chart(candles, plan, signal_row, entry_time, outcome)
        return upload_chart(png, signal_row["id"], supabase_url, service_key,
                            session=session, suffix="-outcome")
    except Exception as exc:  # noqa: BLE001 - charts are best-effort
        print(f"[{signal_row.get('symbol')}] outcome chart failed "
              f"({type(exc).__name__}: {exc}), sending text-only")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/chart/test_outcome_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add signals/chart/outcome_pipeline.py tests/chart/test_outcome_pipeline.py
git commit -m "feat(outcome-chart): non-fatal attach_outcome_chart wrapper"
```

---

## Task 7: Wire into the outcome tracker

**Files:**
- Modify: `signals/outcome_tracker.py`
- Modify: `tests/conftest.py`
- Test: `tests/core/test_outcome.py`

- [ ] **Step 1: Keep run-level outcome tests hermetic**

In `tests/conftest.py`, add two entries to the `_INERT_RUN_STORAGE_DEFAULTS` dict so outcome tests don't do real rendering/network:

```python
    "signals.outcome_tracker.attach_outcome_chart": lambda *a, **k: None,
    "signals.outcome_tracker.set_outcome_chart_url": lambda *a, **k: None,
```

- [ ] **Step 2: Write the failing test**

Append to `tests/core/test_outcome.py`:

```python
def test_terminal_outcome_attaches_and_stores_chart_url(monkeypatch):
    import signals.outcome_tracker as ot
    from datetime import datetime, timezone
    from signals.models import Candle

    # created_at must be recent so the candles below fall inside the trade's
    # life window; open_times are anchored to it so check_outcome_events sees
    # them (it skips any candle with open_time < created_ms).
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    created_ms = int(datetime.fromisoformat(created).timestamp() * 1000)

    row = {"id": "s1", "symbol": "XAUUSD", "timeframe": "5m",
           "direction": "long", "entry": 100.0, "stop_loss": 98.0,
           "take_profit": 103.0, "take_profit_1": 101.0,
           "take_profit_2": 102.0, "take_profit_3": 103.0,
           "status": "open", "created_at": created,
           "chart_data": {"candles": []}}

    # First candle drops to the stop -> terminal sl_hit. candles_covering does
    # fetch_candles(...)[:-1], so return one extra (forming) candle.
    def _candles(*a, **k):
        return [Candle(open_time=created_ms + i * 300000, open=100,
                       high=100.5, low=97.5, close=98, volume=0.0)
                for i in range(3)]

    monkeypatch.setattr(ot, "list_open_signals", lambda *a, **k: [row])
    monkeypatch.setattr(ot, "fetch_candles", _candles)
    monkeypatch.setattr(ot, "update_signal_outcome", lambda *a, **k: None)
    stored = {}
    monkeypatch.setattr(ot, "attach_outcome_chart",
                        lambda *a, **k: "http://x/s1-outcome.png")
    monkeypatch.setattr(ot, "set_outcome_chart_url",
                        lambda sid, url, *a, **k: stored.update({sid: url}))

    class _Cfg:
        supabase_url = "u"; supabase_service_key = "k"
        telegram_bot_token = ""; telegram_channel_id = ""

    closed = ot.track_open_signals(_Cfg())
    assert stored.get("s1") == "http://x/s1-outcome.png"
    assert closed and closed[0][0].get("outcome_chart_url") == "http://x/s1-outcome.png"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_outcome.py::test_terminal_outcome_attaches_and_stores_chart_url -v`
Expected: FAIL with `AttributeError: module 'signals.outcome_tracker' has no attribute 'attach_outcome_chart'`

- [ ] **Step 4: Wire the tracker**

In `signals/outcome_tracker.py`, add imports near the top (with the other `signals.*` imports):

```python
from signals.chart.outcome_pipeline import attach_outcome_chart
from signals.storage import list_open_signals, update_signal_outcome, set_outcome_chart_url
```

(Replace the existing `from signals.storage import list_open_signals, update_signal_outcome` line with the one above.)

Then, inside the `for outcome, closed_at in events:` loop, immediately after the line `row = {**row, "status": outcome}` and before the `if (outcome in ("tp1_hit", ...` Telegram block, insert:

```python
            if outcome in ("tp3_hit", "tp_hit", "sl_hit"):
                chart_url = attach_outcome_chart(
                    row, outcome, window,
                    supabase_url=cfg.supabase_url,
                    service_key=cfg.supabase_service_key,
                    session=session,
                )
                if chart_url:
                    row = {**row, "outcome_chart_url": chart_url}
                    try:
                        set_outcome_chart_url(
                            row["id"], chart_url, cfg.supabase_url,
                            cfg.supabase_service_key, session=session,
                        )
                    except Exception as exc:
                        print(f"[{symbol}] failed to store outcome_chart_url "
                              f"({type(exc).__name__}), continuing")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_outcome.py -v`
Expected: PASS (existing outcome tests + the new one). The conftest stubs keep the pre-existing tests inert; the new test overrides them with its own monkeypatches.

- [ ] **Step 6: Commit**

```bash
git add signals/outcome_tracker.py tests/conftest.py tests/core/test_outcome.py
git commit -m "feat(outcome-chart): render + persist outcome chart on terminal close"
```

---

## Task 8: Telegram photo outcome alert

**Files:**
- Modify: `signals/telegram_client.py`
- Test: `tests/core/test_telegram.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_telegram.py`:

```python
def _outcome_row(outcome_chart_url=None):
    return {"symbol": "XAUUSD", "direction": "long", "entry": 100.0,
            "stop_loss": 98.0, "take_profit": 103.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0,
            "outcome_chart_url": outcome_chart_url}


def test_outcome_alert_uses_photo_when_chart_present():
    from signals.telegram_client import send_outcome_alert
    rec = _ChartRec()
    send_outcome_alert(_outcome_row("http://x/s1-outcome.png"), "tp3_hit",
                       "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendPhoto")
    assert rec.calls[0]["json"]["photo"] == "http://x/s1-outcome.png"


def test_outcome_alert_falls_back_to_message_without_chart():
    from signals.telegram_client import send_outcome_alert
    rec = _ChartRec()
    send_outcome_alert(_outcome_row(None), "sl_hit", "tok", "chat", session=rec)
    assert rec.calls[0]["url"].endswith("/sendMessage")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_telegram.py -k outcome_alert_uses_photo -v`
Expected: FAIL (current `send_outcome_alert` always calls `sendMessage`).

- [ ] **Step 3: Add the photo-or-text branch**

In `signals/telegram_client.py`, replace the existing `send_outcome_alert` function body with:

```python
def send_outcome_alert(signal_row: dict, outcome: str, bot_token: str,
                       chat_id: str, session=None) -> None:
    """Send one TP/SL-hit alert — a photo when an outcome chart exists,
    otherwise the text message."""
    text = format_outcome_alert(signal_row, outcome)
    url = signal_row.get("outcome_chart_url")
    if url:
        send_photo(url, text, bot_token, chat_id, session=session)
    else:
        send_message(text, bot_token, chat_id, session=session)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_telegram.py -v`
Expected: PASS (all existing telegram tests + the 2 new ones).

- [ ] **Step 5: Commit**

```bash
git add signals/telegram_client.py tests/core/test_telegram.py
git commit -m "feat(outcome-chart): Telegram outcome alert sends the chart photo"
```

---

## Task 9: Web display

**Files:**
- Modify: `web/src/lib/signals.ts`
- Modify: `web/src/components/dashboard/SignalsGrid.tsx`

**Before writing web code:** read `web/AGENTS.md` (pinned Next.js). Use a plain `<img>`, not `next/image`.

- [ ] **Step 1: Add `outcomeChartUrl` to the types**

In `web/src/lib/signals.ts`, add to the `Signal` type (after `chartUrl`):

```typescript
  outcomeChartUrl: string | null;
```

Add to the `SignalRow` type (after `chart_url?`):

```typescript
  outcome_chart_url?: string | null;
```

- [ ] **Step 2: Map it in `parseRow`**

In the object `parseRow` returns (right after the `chartUrl:` line), add:

```typescript
    outcomeChartUrl: typeof row.outcome_chart_url === "string" ? row.outcome_chart_url : null,
```

- [ ] **Step 3: Render the outcome image in the detail view**

In `web/src/components/dashboard/SignalsGrid.tsx`, immediately after the existing setup-chart `{signal.chartUrl && ( ... )}` block, add:

```tsx
{signal.outcomeChartUrl && (
  <div className="mt-4">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate/70 mb-1">
      Outcome
    </p>
    <img
      src={signal.outcomeChartUrl}
      alt={`${signal.symbol} ${signal.timeframe} ${signal.direction} outcome`}
      loading="lazy"
      className="w-full rounded-lg border border-slate/15"
    />
  </div>
)}
```

- [ ] **Step 4: Verify the web build**

Run: `cd web && npm run lint && npm run build`
Expected: build succeeds. (`Signal` is only constructed in `parseRow` and the `Hero.tsx` sample — the sample sets `chartUrl: null`; add `outcomeChartUrl: null` there too if the build flags it as a missing property.)

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/signals.ts web/src/components/dashboard/SignalsGrid.tsx web/src/components/landing/Hero.tsx
git commit -m "feat(outcome-chart): show outcome image on dashboard cards"
```

---

## Definition of Done

- A terminal close (`tp3_hit`/`sl_hit`/legacy `tp_hit`) renders an outcome chart from the merged setup-snapshot + price-path candles, uploads it as `{id}-outcome.png`, stores `outcome_chart_url`, and the Telegram outcome alert is sent as a photo.
- Partial TP1/TP2 and expiry are unaffected (still text / no alert).
- A chart failure never drops or delays the outcome alert (non-fatal).
- The dashboard shows the outcome image on closed cards.
- `pytest` green; `cd web && npm run build` succeeds.
```
