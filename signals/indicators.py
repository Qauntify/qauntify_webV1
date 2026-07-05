"""Pure-function technical indicators.

All functions return lists aligned 1:1 with their input, with None
padding during the indicator's warm-up window.
"""


def ema(values, period):
    """Exponential moving average seeded with the SMA of the first `period` values."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    if n < period:
        return [None] * n
    out = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    k = 2.0 / (period + 1)
    for v in values[period:]:
        prev = (v - prev) * k + prev
        out.append(prev)
    return out


def rsi(values, period=14):
    """Wilder-smoothed RSI. Flat series (no gains, no losses) is defined as 50."""
    n = len(values)
    if n < period + 1:
        return [None] * n
    out = [None] * period
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out.append(_rsi_value(avg_gain, avg_loss))
    for i in range(period + 1, n):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        out.append(_rsi_value(avg_gain, avg_loss))
    return out


def _rsi_value(avg_gain, avg_loss):
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd_histogram(values, fast=12, slow=26, signal=9):
    """MACD histogram: (EMA_fast - EMA_slow) minus its EMA_signal smoothing."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [
        f - s if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    start = next((i for i, v in enumerate(macd_line) if v is not None), len(macd_line))
    signal_line = [None] * start + ema(macd_line[start:], signal)
    return [
        m - s if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]


def atr(highs, lows, closes, period=14):
    """Wilder-smoothed Average True Range."""
    n = len(closes)
    if n < period + 1:
        return [None] * n
    true_ranges = [None]
    for i in range(1, n):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    out = [None] * period
    prev = sum(true_ranges[1:period + 1]) / period
    out.append(prev)
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + true_ranges[i]) / period
        out.append(prev)
    return out
