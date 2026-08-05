"""Aggregate OHLC candles into wider buckets (used by offline chart scripts)."""
from __future__ import annotations

from signals.models import Candle


def resample_candles(candles: list[Candle], minutes: int) -> list[Candle]:
    """Fold candles into `minutes`-wide buckets aligned to the UTC epoch."""
    width = minutes * 60_000
    out: list[Candle] = []
    for candle in candles:
        bucket = candle.open_time - (candle.open_time % width)
        if out and out[-1].open_time == bucket:
            prev = out[-1]
            out[-1] = Candle(
                open_time=bucket,
                open=prev.open,
                high=max(prev.high, candle.high),
                low=min(prev.low, candle.low),
                close=candle.close,
                volume=prev.volume + candle.volume,
            )
        else:
            out.append(
                Candle(
                    open_time=bucket,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
            )
    return out
