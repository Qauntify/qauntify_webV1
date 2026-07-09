from signals.indicators import adx, atr, ema, macd_histogram, rsi


def test_ema_constant_series_equals_constant():
    values = [50.0] * 30
    result = ema(values, 9)
    assert result[:8] == [None] * 8
    for v in result[8:]:
        assert abs(v - 50.0) < 1e-9


def test_ema_shorter_than_period_is_all_none():
    assert ema([1.0, 2.0, 3.0], 9) == [None, None, None]


def test_ema_tracks_rising_trend_below_price():
    values = [float(i) for i in range(1, 31)]  # 1..30 rising
    result = ema(values, 9)
    assert result[-1] is not None
    assert result[-1] < values[-1]  # EMA lags a rising price
    assert result[-1] > result[-2]  # but is itself rising


def test_rsi_all_gains_is_100():
    values = [float(i) for i in range(1, 31)]
    result = rsi(values, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert abs(v - 100.0) < 1e-9


def test_rsi_all_losses_is_0():
    values = [float(i) for i in range(31, 1, -1)]
    result = rsi(values, 14)
    for v in result[14:]:
        assert abs(v - 0.0) < 1e-9


def test_rsi_flat_series_is_50():
    values = [50.0] * 30
    result = rsi(values, 14)
    for v in result[14:]:
        assert abs(v - 50.0) < 1e-9


def test_macd_histogram_constant_series_is_zero():
    values = [50.0] * 60
    result = macd_histogram(values)
    assert result[-1] is not None
    assert abs(result[-1]) < 1e-9


def test_macd_histogram_length_matches_input():
    values = [float(i) for i in range(60)]
    assert len(macd_histogram(values)) == 60


def test_atr_constant_range_candles():
    n = 30
    highs = [102.0] * n
    lows = [98.0] * n
    closes = [100.0] * n
    result = atr(highs, lows, closes, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert abs(v - 4.0) < 1e-9  # high-low = 4 every bar


def test_atr_too_short_is_all_none():
    assert atr([1.0] * 5, [0.5] * 5, [0.8] * 5, 14) == [None] * 5


def test_adx_too_short_is_all_none():
    n = 10
    assert adx([1.0] * n, [0.5] * n, [0.8] * n, 14) == [None] * n


def test_adx_warmup_padding_length():
    n = 40
    highs = [100.0 + i * 0.5 for i in range(n)]
    lows = [98.0 + i * 0.5 for i in range(n)]
    closes = [99.0 + i * 0.5 for i in range(n)]
    result = adx(highs, lows, closes, 14)
    assert len(result) == n
    # ADX needs a full period of DX values before its own smoothing starts,
    # so warm-up runs longer than a plain ATR/RSI (roughly 2x the period).
    assert result[:27] == [None] * 27
    assert result[27] is not None


def test_adx_flat_series_is_zero():
    # No directional movement at all (every bar's high/low is unchanged) ->
    # +DI and -DI are both zero -> ADX is defined as 0, not trending.
    n = 40
    highs = [101.0] * n
    lows = [99.0] * n
    closes = [100.0] * n
    result = adx(highs, lows, closes, 14)
    for v in result[27:]:
        assert abs(v - 0.0) < 1e-9


def test_adx_strong_uptrend_is_high():
    # Every bar makes a new high and a new low, no overlap -> textbook
    # strongly-trending series -> ADX should read high (>40).
    n = 40
    highs = [100.0 + i * 3.0 for i in range(n)]
    lows = [98.0 + i * 3.0 for i in range(n)]
    closes = [99.0 + i * 3.0 for i in range(n)]
    result = adx(highs, lows, closes, 14)
    assert result[-1] > 40.0


def test_adx_choppy_series_is_low():
    # Alternating up/down swings of equal size -> no sustained direction ->
    # ADX should read low (<20), the "don't trade this" regime.
    n = 40
    highs, lows, closes = [], [], []
    for i in range(n):
        base = 100.0 + (2.0 if i % 2 == 0 else -2.0)
        highs.append(base + 1.0)
        lows.append(base - 1.0)
        closes.append(base)
    result = adx(highs, lows, closes, 14)
    assert result[-1] < 20.0
