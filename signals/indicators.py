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


def _dx_value(plus_di, minus_di):
    total = plus_di + minus_di
    if total == 0.0:
        return 0.0
    return 100.0 * abs(plus_di - minus_di) / total


def adx(highs, lows, closes, period=14):
    """Wilder-smoothed Average Directional Index: how strongly a market is
    trending (high) vs. ranging (low), independent of direction. Needs
    2*period-1 bars of warm-up: one period to seed the smoothed +DM/-DM/TR,
    then another to seed the DX smoothing that produces ADX itself."""
    n = len(closes)
    if n < 2 * period:
        return [None] * n

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    true_ranges = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0.0 else 0.0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0.0 else 0.0
        true_ranges[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    smoothed_plus_dm = sum(plus_dm[1:period + 1])
    smoothed_minus_dm = sum(minus_dm[1:period + 1])
    smoothed_tr = sum(true_ranges[1:period + 1])

    dx_values = [None] * period
    plus_di = 100.0 * smoothed_plus_dm / smoothed_tr if smoothed_tr else 0.0
    minus_di = 100.0 * smoothed_minus_dm / smoothed_tr if smoothed_tr else 0.0
    dx_values.append(_dx_value(plus_di, minus_di))

    for i in range(period + 1, n):
        smoothed_plus_dm = smoothed_plus_dm - smoothed_plus_dm / period + plus_dm[i]
        smoothed_minus_dm = smoothed_minus_dm - smoothed_minus_dm / period + minus_dm[i]
        smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[i]
        plus_di = 100.0 * smoothed_plus_dm / smoothed_tr if smoothed_tr else 0.0
        minus_di = 100.0 * smoothed_minus_dm / smoothed_tr if smoothed_tr else 0.0
        dx_values.append(_dx_value(plus_di, minus_di))

    # ADX is itself a Wilder-smoothed average of DX, seeded with a plain
    # SMA of the first `period` DX values once they exist.
    out = [None] * (2 * period - 1)
    start = period
    prev = sum(dx_values[start:start + period]) / period
    out.append(prev)
    for i in range(start + period, n):
        prev = (prev * (period - 1) + dx_values[i]) / period
        out.append(prev)
    return out


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


def lwma(values, period):
    """Linear Weighted Moving Average — newer bars weigh more (period, …, 1)."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    if n < period:
        return [None] * n
    weights = list(range(1, period + 1))
    weight_sum = period * (period + 1) / 2.0
    out = [None] * (period - 1)
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        out.append(sum(v * w for v, w in zip(window, weights)) / weight_sum)
    return out


def chandelier_exit(highs, lows, closes, period=22, multiplier=4.5,
                    lookback=None):
    """Chandelier Exit trails + direction (TradingView-style).

    Returns (long_stop, short_stop, direction) lists aligned with input.
    direction is 1 (long), -1 (short), or None during warm-up.
    Active trail for a bar is long_stop when direction==1 else short_stop.
    """
    n = len(closes)
    lb = lookback if lookback is not None else period
    atr_vals = atr(highs, lows, closes, period)
    long_stop = [None] * n
    short_stop = [None] * n
    direction = [None] * n
    warm = max(period, lb)
    if n < warm + 1:
        return long_stop, short_stop, direction

    prev_dir = None
    for i in range(warm - 1, n):
        if atr_vals[i] is None:
            continue
        hh = max(highs[i - lb + 1:i + 1])
        ll = min(lows[i - lb + 1:i + 1])
        long_stop[i] = hh - multiplier * atr_vals[i]
        short_stop[i] = ll + multiplier * atr_vals[i]
        if prev_dir is None:
            # Seed: close relative to the mid of the two trails.
            mid = (long_stop[i] + short_stop[i]) / 2.0
            prev_dir = 1 if closes[i] >= mid else -1
        elif prev_dir == 1 and closes[i] < long_stop[i]:
            prev_dir = -1
        elif prev_dir == -1 and closes[i] > short_stop[i]:
            prev_dir = 1
        direction[i] = prev_dir
    return long_stop, short_stop, direction
