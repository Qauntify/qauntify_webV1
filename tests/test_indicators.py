from signals.indicators import atr, ema, macd_histogram, rsi


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
