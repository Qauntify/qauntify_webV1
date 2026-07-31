"""The sweep's gating map — Extreme must never pick up an HTF gate by accident."""
from scripts.bbma_report import CONFLUENCE, TIMEFRAMES, htf_for


def test_extreme_is_ungated_on_every_timeframe():
    for timeframe in TIMEFRAMES:
        assert htf_for("bbma_extreme", timeframe) is None


def test_reentry_steps_one_timeframe_up():
    assert htf_for("bbma_reentry", "1h") == "4h"
    assert htf_for("bbma_reentry", "4h") == "1d"


def test_every_swept_timeframe_has_a_confluence_mapping():
    for timeframe in TIMEFRAMES:
        assert timeframe in CONFLUENCE


def test_15m_is_not_swept():
    """Kraken caps OHLC at 721 bars — 7.5 days at 15m, which cannot produce a
    trade count worth reading."""
    assert "15m" not in TIMEFRAMES
