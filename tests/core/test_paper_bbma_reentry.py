"""The BBMA Re-entry paper trial records, and must never deliver.

A paper signal is stored so its forward outcome can be compared against the
nine-year backtest. It is not a recommendation: it bypasses the LLM gate,
Telegram and chart rendering, is written with shadow=True so every user-facing
read path filters it out, and can never break a live scan.
"""
import pytest

from signals.pipeline import scan as run
from signals.pipeline.market_data import MarketData
from signals.models import Candle
from signals.strategies.bbma.stack import MIN_CANDLES


class _Cfg:
    supabase_url = "https://example.invalid"
    supabase_service_key = "key"


def _market(candles):
    n = len(candles)
    return MarketData(
        candles=candles, ema9=[None] * n, ema21=[None] * n, rsi14=[None] * n,
        macd_hist=[None] * n, atr14=[5.0] * n, adx14=[20.0] * n,
        htf_trend="up", h1_candles=None,
    )


def _flat_candles(n=MIN_CANDLES):
    return [
        Candle(open_time=i * 3_600_000, open=100.0, high=100.5, low=99.5,
               close=100.0, volume=1.0)
        for i in range(n)
    ]


@pytest.fixture
def saved(monkeypatch):
    """Capture save_signal calls instead of hitting Supabase."""
    calls = []
    monkeypatch.setattr(run, "save_signal",
                        lambda *a, **kw: calls.append((a, kw)))
    return calls


def _fire(monkeypatch, setup):
    """Make the detector return `setup` regardless of the candles."""
    import signals.strategies.bbma as bbma
    monkeypatch.setattr(bbma, "detect_reentry", lambda *a, **kw: setup)


def test_disabled_by_default(saved, monkeypatch):
    """The flag defaults off, so a normal deployment records nothing."""
    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", False)
    run._record_paper_bbma_reentry(
        "BTCUSD", _market(_flat_candles()), _Cfg(),
        timeframe="1h", session=None)
    assert saved == []


def test_ignores_timeframes_other_than_its_own(saved, monkeypatch):
    """The trial is pinned to the configuration the backtest measured; firing
    it on the 5m or 15m session would record an untested strategy."""
    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", True)
    for timeframe in ("5m", "15m", "4h"):
        run._record_paper_bbma_reentry(
            "BTCUSD", _market(_flat_candles()), _Cfg(),
            timeframe=timeframe, session=None)
    assert saved == []


def test_records_nothing_when_no_setup_is_found(saved, monkeypatch):
    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", True)
    run._record_paper_bbma_reentry(
        "BTCUSD", _market(_flat_candles()), _Cfg(),
        timeframe="1h", session=None)
    assert saved == []


def test_records_a_setup_as_a_shadow_row(saved, monkeypatch):
    from signals.models import CandidateSetup

    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", True)
    _fire(monkeypatch, CandidateSetup(
        "BTCUSD", "long", 100.0, 95.0, 105.0,
        {"strategy": "bbma_reentry"}, take_profit_2=110.0, take_profit_3=115.0))

    run._record_paper_bbma_reentry(
        "BTCUSD", _market(_flat_candles()), _Cfg(),
        timeframe="1h", session=None)

    assert len(saved) == 1
    _, kwargs = saved[0]
    assert kwargs["shadow"] is True, "a paper row must never be user-visible"
    assert kwargs["experiment"] == "bbma_reentry", (
        "unrelated trials must not pool together in analysis")


def test_a_storage_failure_never_breaks_the_scan(monkeypatch):
    """Swallowing is deliberate: an experiment must not take down delivery."""
    from signals.models import CandidateSetup

    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", True)
    _fire(monkeypatch, CandidateSetup(
        "BTCUSD", "long", 100.0, 95.0, 105.0, {"strategy": "bbma_reentry"}))

    def _boom(*a, **kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(run, "save_signal", _boom)
    run._record_paper_bbma_reentry(          # must not raise
        "BTCUSD", _market(_flat_candles()), _Cfg(),
        timeframe="1h", session=None)


def test_a_detector_failure_never_breaks_the_scan(monkeypatch, saved):
    monkeypatch.setattr(run, "PAPER_BBMA_REENTRY", True)

    def _boom(*a, **kw):
        raise ValueError("bad candles")

    import signals.strategies.bbma as bbma
    monkeypatch.setattr(bbma, "detect_reentry", _boom)
    run._record_paper_bbma_reentry(          # must not raise
        "BTCUSD", _market(_flat_candles()), _Cfg(),
        timeframe="1h", session=None)
    assert saved == []


def test_trial_timeframe_matches_the_swing_session_that_carries_it():
    """The trial rides the session that scans 1h against a 4h confluence trend
    — the exact configuration measured in the backtest. If that session's
    timeframe ever changes, this pin fails rather than silently recording an
    unmeasured setup."""
    from signals.models import TRADING_SESSIONS
    swing = next(s for s in TRADING_SESSIONS if s.name == "swing")
    assert run.PAPER_BBMA_REENTRY_TIMEFRAME == swing.timeframe
    assert swing.confluence_timeframe == "4h"
