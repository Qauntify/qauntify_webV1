"""Thin causal adapter over the production strategy router and indicators."""
from __future__ import annotations

import hashlib
import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from signals.indicators import adx, atr, ema, macd_histogram, rsi
from signals.strategies import detect_setup
from signals.strategies import router


SUPPORTED_STRATEGIES = frozenset({
    "ema_cross", "ict_smc", "ce_lwma", "ict_fvg", "sr_zone",
})


@lru_cache(maxsize=None)
def strategy_version(strategy_name: str) -> str:
    """Use the actual detector source hash instead of a hand-written version."""
    detector = {
        "ema_cross": router.detect_ema_setup,
        "ict_smc": router.detect_ict_setup,
        "ce_lwma": router.detect_ce_setup,
        "ict_fvg": router.detect_ict_fvg_setup,
        "sr_zone": router.detect_sr_setup,
    }[strategy_name]
    source = inspect.getsource(inspect.getmodule(detector)).encode("utf-8")
    return f"sha256:{hashlib.sha256(source).hexdigest()}"


@dataclass(frozen=True)
class IndicatorSeries:
    ema9: list
    ema21: list
    rsi14: list
    macd_hist: list
    atr14: list
    adx14: list

    def through(self, end: int) -> tuple[list, ...]:
        return tuple(PrefixView(series, end) for series in (
            self.ema9, self.ema21, self.rsi14, self.macd_hist,
            self.atr14, self.adx14,
        ))


class PrefixView(Sequence):
    """Read-only sequence prefix that avoids copying full replay history."""

    def __init__(self, values: Sequence, end: int):
        if end < 0 or end > len(values):
            raise ValueError("Prefix end is outside the source sequence")
        self._values = values
        self._end = end

    def __len__(self) -> int:
        return self._end

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(self._end)
            return self._values[start:stop:step]
        normalized = index + self._end if index < 0 else index
        if normalized < 0 or normalized >= self._end:
            raise IndexError(index)
        return self._values[normalized]


def calculate_causal_indicators(candles) -> IndicatorSeries:
    closes = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    return IndicatorSeries(
        ema9=ema(closes, 9),
        ema21=ema(closes, 21),
        rsi14=rsi(closes, 14),
        macd_hist=macd_histogram(closes),
        atr14=atr(highs, lows, closes, 14),
        adx14=adx(highs, lows, closes, 14),
    )


def evaluate_strategy(
    strategy_name: str,
    symbol: str,
    candles,
    indicators: IndicatorSeries,
    *,
    htf_trend: str | None = None,
    h1_candles=None,
):
    """Call the same router as live execution with history ending at now."""
    if strategy_name not in SUPPORTED_STRATEGIES:
        raise ValueError(f"Unsupported strategy: {strategy_name!r}")
    end = len(candles)
    ema9, ema21, rsi14, macd_hist, atr14, adx14 = indicators.through(end)
    return detect_setup(
        strategy_name,
        symbol,
        candles,
        ema9,
        ema21,
        rsi14,
        macd_hist,
        atr14,
        adx14=adx14,
        htf_trend=htf_trend,
        h1_candles=h1_candles,
    )
