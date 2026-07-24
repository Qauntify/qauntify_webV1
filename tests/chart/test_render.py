from signals.chart.annotations import level, marker, series, zone
from signals.chart.render import _price_bounds, render_chart
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


def test_price_bounds_expands_to_include_targets_above_candles():
    candles = _candles()  # highs top out around ~103.4
    plan = [
        level(200.0, "TP3", "target", style="dashed"),  # far above the candles
        level(50.0, "SL", "stop", style="dashed"),      # far below the candles
    ]
    lo, hi = _price_bounds(candles, plan)
    assert hi > 200.0  # TP3 is inside the view (with padding), not clipped
    assert lo < 50.0   # SL is inside the view too

