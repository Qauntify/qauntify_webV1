import pytest

from ml.replay.strategy_adapter import (
    IndicatorSeries,
    PrefixView,
    calculate_causal_indicators,
    evaluate_strategy,
)
from signals.models import Candle
from signals.strategies import detect_setup


def test_adapter_matches_production_router_on_same_history():
    prices = [100.0] * 40
    candles = [Candle(i * 300_000, p, p + 1, p - 1, p, 1.0) for i, p in enumerate(prices)]
    indicators = calculate_causal_indicators(candles)
    adapted = evaluate_strategy("ema_cross", "XAUUSD", candles, indicators)
    series = indicators.through(len(candles))
    production = detect_setup(
        "ema_cross", "XAUUSD", candles, *series[:5], adx14=series[5],
        htf_trend=None, h1_candles=None,
    )
    assert adapted == production


@pytest.mark.parametrize(
    ("fast_before", "fast_after", "macd", "direction"),
    [(99.0, 101.0, 0.5, "long"), (101.0, 99.0, -0.5, "short")],
)
def test_adapter_matches_valid_live_setup_fields(
    fast_before, fast_after, macd, direction,
):
    count = 20
    candles = [Candle(i, 100, 101, 99, 100, 1.0) for i in range(count)]
    indicators = IndicatorSeries(
        ema9=[fast_before] * (count - 1) + [fast_after],
        ema21=[100.0] * count,
        rsi14=[55.0 if direction == "long" else 45.0] * count,
        macd_hist=[macd] * count,
        atr14=[2.0] * count,
        adx14=[25.0] * count,
    )
    adapted = evaluate_strategy("ema_cross", "XAUUSD", candles, indicators)
    series = indicators.through(count)
    production = detect_setup(
        "ema_cross", "XAUUSD", candles, *series[:5], adx14=series[5],
        htf_trend=None, h1_candles=None,
    )
    assert adapted == production
    assert adapted is not None
    assert adapted.direction == direction
    assert adapted.entry == production.entry
    assert adapted.stop_loss == production.stop_loss
    assert adapted.resolved_take_profits() == production.resolved_take_profits()
    assert adapted.indicators == production.indicators


def test_causal_indicators_before_boundary_ignore_future_candles():
    base = [Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(40)]
    future = base + [Candle(40 + i, 1000, 1001, 999, 1000, 1) for i in range(10)]
    before = calculate_causal_indicators(base)
    after = calculate_causal_indicators(future)
    assert before.ema21 == after.ema21[:len(base)]
    assert before.atr14 == after.atr14[:len(base)]
    assert before.adx14 == after.adx14[:len(base)]


def test_prefix_view_matches_list_prefix_without_copying_source():
    source = [1, 2, 3, 4, 5]
    prefix = PrefixView(source, 3)
    assert list(prefix) == source[:3]
    assert prefix[-1] == 3
    assert prefix[-2:] == [2, 3]
    source[2] = 30
    assert prefix[-1] == 30
