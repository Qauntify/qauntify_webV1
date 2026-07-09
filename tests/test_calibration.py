from signals.calibration import (
    _bucket_stats,
    _confidence_bucket,
    _r_multiple,
    _strategy_of,
    calibration_report,
    summarize_by,
)


def _row(**overrides):
    row = {
        "symbol": "BTCUSDT", "timeframe": "1h", "direction": "long",
        "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
        "confidence": 80, "status": "tp_hit", "indicators": {},
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_r_multiple_tp_hit_uses_reward_risk_ratio():
    row = _row(status="tp_hit", entry=100.0, stop_loss=98.0, take_profit=104.0)
    assert _r_multiple(row) == 2.0


def test_r_multiple_sl_hit_is_minus_one():
    assert _r_multiple(_row(status="sl_hit")) == -1.0


def test_r_multiple_expired_is_zero():
    # outcome_tracker records no exit price for expired signals, so their
    # true P&L is unknown — treated as neutral rather than guessed.
    assert _r_multiple(_row(status="expired")) == 0.0


def test_r_multiple_short_direction_uses_absolute_distances():
    row = _row(status="tp_hit", direction="short", entry=100.0,
              stop_loss=102.0, take_profit=96.0)
    assert _r_multiple(row) == 2.0


def test_bucket_stats_counts_and_win_rate():
    rows = [_row(status="tp_hit"), _row(status="tp_hit"),
            _row(status="sl_hit"), _row(status="expired")]
    stats = _bucket_stats(rows)
    assert stats["count"] == 4
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["expired"] == 1
    # Win rate is decided-outcomes only: expired rows aren't a win or a loss.
    assert stats["win_rate"] == 2 / 3


def test_bucket_stats_win_rate_none_when_no_decided_outcomes():
    assert _bucket_stats([_row(status="expired")])["win_rate"] is None


def test_bucket_stats_empty_rows():
    assert _bucket_stats([]) == {
        "count": 0, "wins": 0, "losses": 0, "expired": 0,
        "win_rate": None, "avg_r": None,
    }


def test_confidence_bucket_groups_by_ten():
    assert _confidence_bucket(82) == "80-89"
    assert _confidence_bucket(80) == "80-89"
    assert _confidence_bucket(79) == "70-79"
    assert _confidence_bucket(None) == "unknown"


def test_strategy_of_defaults_to_ema_cross():
    assert _strategy_of(_row(indicators={})) == "ema_cross"
    assert _strategy_of(_row(indicators={"strategy": "ict_smc"})) == "ict_smc"


def test_summarize_by_groups_rows():
    rows = [
        _row(symbol="BTCUSDT", status="tp_hit"),
        _row(symbol="BTCUSDT", status="sl_hit"),
        _row(symbol="ETHUSDT", status="tp_hit"),
    ]
    grouped = summarize_by(rows, lambda r: r["symbol"])
    assert grouped["BTCUSDT"]["count"] == 2
    assert grouped["ETHUSDT"]["count"] == 1


def test_calibration_report_has_all_groupings():
    rows = [
        _row(symbol="BTCUSDT", timeframe="1h", confidence=85,
            status="tp_hit", indicators={}),
        _row(symbol="ETHUSDT", timeframe="15m", confidence=60,
            status="sl_hit", indicators={"strategy": "ict_smc"}),
    ]
    report = calibration_report(rows)
    assert report["overall"]["count"] == 2
    assert set(report["by_strategy"]) == {"ema_cross", "ict_smc"}
    assert set(report["by_symbol"]) == {"BTCUSDT", "ETHUSDT"}
    assert set(report["by_timeframe"]) == {"1h", "15m"}
    assert set(report["by_confidence"]) == {"80-89", "60-69"}


def test_calibration_report_empty_rows():
    report = calibration_report([])
    assert report["overall"]["count"] == 0
    assert report["by_strategy"] == {}
