from signals.chart.annotations import level, marker, series, zone
from signals.chart.render import (
    RENDER_BARS, _price_bounds, _setup_title, render_chart, view_for_plan,
)
from signals.models import Candle, Signal

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _candles(n=60):
    out = []
    for i in range(n):
        base = 100 + i * 0.05
        out.append(Candle(open_time=i * 300000, open=base, high=base + 0.4,
                          low=base - 0.4, close=base + 0.1, volume=1.0))
    return out


def _signal(**kwargs):
    base = dict(
        id="s1", symbol="BTCUSD", timeframe="5m", direction="long",
        entry=102.0, stop_loss=101.0, take_profit=103.0,
        take_profit_2=104.0, take_profit_3=105.0, confidence=70,
        rationale="r", indicators={}, news_headlines=[], created_at="t",
    )
    base.update(kwargs)
    return Signal(**base)


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


def test_price_bounds_expands_to_include_targets_above_candles():
    candles = _candles()  # highs top out around ~103.4
    plan = [
        level(200.0, "TP3", "target", style="dashed"),  # far above the candles
        level(50.0, "SL", "stop", style="dashed"),      # far below the candles
    ]
    lo, hi = _price_bounds(candles, plan)
    assert hi > 200.0  # TP3 is inside the view (with padding), not clipped
    assert lo < 50.0   # SL is inside the view too


def test_view_for_plan_includes_early_sweep_beyond_blind_trim():
    """Sweep 55 bars back would vanish under a last-40 trim — keep it."""
    candles = _candles(70)
    sweep_t = candles[10].open_time  # 60 bars before the end
    plan = [
        marker(sweep_t, 100.5, "1. Liquidity sweep", "liquidity", 1),
        level(102.0, "Entry", "entry"),
    ]
    view = view_for_plan(candles, plan)
    assert view[0].open_time <= sweep_t
    assert any(c.open_time == sweep_t for c in view)
    # Blind trim would have started at candles[30]; we must start earlier.
    assert view[0].open_time < candles[-RENDER_BARS].open_time


def test_setup_title_includes_ict_structure():
    sig = _signal(indicators={"structure": "bullish_choch_fvg", "strategy": "ict_fvg"})
    assert "bullish_choch_fvg" in _setup_title(sig)
