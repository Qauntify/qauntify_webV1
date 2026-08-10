"""Unit tests for the independent War Room Floor pipeline."""
from signals import war_room_scan
from signals.config import FloorConfig
from signals.debate import FloorAgents
from signals.models import CandidateSetup, TIMEFRAME_MINUTES


def _floor():
    return FloorConfig(
        structure_key="sk",
        momentum_key="mk",
        manager_key="nk",
        supabase_url="https://x.supabase.co",
        supabase_service_key="svc",
    )


def _setup(symbol="BTCUSD"):
    return CandidateSetup(
        symbol, "long", 100.0, 99.0, 102.0,
        {"strategy": "cloud_mss"},
        take_profit_2=103.0, take_profit_3=104.0,
    )


class StubLLM:
    def chat(self, messages, temperature=0.2):
        return "stub"


def test_floor_timeframe_maps_to_15m_bars():
    assert TIMEFRAME_MINUTES["floor"] == 15


def test_scan_skips_when_no_candidate(monkeypatch):
    class Mkt:
        candles = []
        ema9 = ema21 = rsi14 = macd_hist = atr14 = adx14 = None
        htf_trend = None
        h1_candles = None

    monkeypatch.setattr(war_room_scan, "_load_market_data",
                        lambda *a, **k: (Mkt(), []))
    monkeypatch.setattr(war_room_scan, "detect_setup", lambda *a, **k: None)
    agents = FloorAgents(StubLLM(), StubLLM(), StubLLM())
    assert war_room_scan.scan_symbol_floor(
        "BTCUSD", _floor(), agents,
    ) is None


def test_scan_skips_when_manager_rejects(monkeypatch):
    class Mkt:
        candles = []
        ema9 = ema21 = rsi14 = macd_hist = atr14 = adx14 = None
        htf_trend = None
        h1_candles = None

    monkeypatch.setattr(
        war_room_scan, "_load_market_data",
        lambda *a, **k: (Mkt(), []),
    )
    monkeypatch.setattr(war_room_scan, "detect_setup", lambda *a, **k: _setup())
    monkeypatch.setattr(war_room_scan, "already_signaled", lambda *a, **k: False)
    monkeypatch.setattr(
        war_room_scan, "run_debate",
        lambda *a, **k: {
            "manager_verdict": "reject",
            "manager_confidence": 20,
            "transcript": [
                {"agent": "Structure Analyst", "message": "x"},
                {"agent": "Momentum Analyst", "message": "y"},
                {"agent": "Manager", "message": "no"},
            ],
        },
    )
    agents = FloorAgents(StubLLM(), StubLLM(), StubLLM())
    assert war_room_scan.scan_symbol_floor(
        "BTCUSD", _floor(), agents,
    ) is None


def test_scan_stores_floor_signal_on_manager_agree(monkeypatch):
    class Mkt:
        candles = []
        ema9 = ema21 = rsi14 = macd_hist = atr14 = adx14 = None
        htf_trend = None
        h1_candles = None

    saved = {}

    monkeypatch.setattr(
        war_room_scan, "_load_market_data",
        lambda *a, **k: (Mkt(), []),
    )
    monkeypatch.setattr(war_room_scan, "detect_setup", lambda *a, **k: _setup())
    monkeypatch.setattr(war_room_scan, "already_signaled", lambda *a, **k: False)
    monkeypatch.setattr(
        war_room_scan, "run_debate",
        lambda *a, **k: {
            "manager_verdict": "agree",
            "manager_confidence": 75,
            "transcript": [
                {"agent": "Structure Analyst", "message": "ok"},
                {"agent": "Momentum Analyst", "message": "ok"},
                {"agent": "Manager", "message": "publish"},
            ],
        },
    )
    monkeypatch.setattr(
        war_room_scan, "setup_stop_risk_ok", lambda *a, **k: (True, ""),
    )
    monkeypatch.setattr(
        war_room_scan, "attach_chart", lambda signal, *a, **k: signal,
    )
    monkeypatch.setattr(
        war_room_scan, "with_retry", lambda fn: fn(),
    )
    monkeypatch.setattr(
        war_room_scan, "save_signal",
        lambda signal, *a, **k: saved.setdefault("signal", signal),
    )
    monkeypatch.setattr(
        war_room_scan, "save_debate",
        lambda debate, *a, **k: saved.setdefault("debate", debate),
    )

    agents = FloorAgents(StubLLM(), StubLLM(), StubLLM())
    signal = war_room_scan.scan_symbol_floor("BTCUSD", _floor(), agents)

    assert signal is not None
    assert signal.timeframe == "floor"
    assert signal.indicators.get("channel") == "war_room"
    assert saved["signal"].timeframe == "floor"
    assert saved["debate"]["timeframe"] == "floor"
    assert saved["debate"]["signal_id"] == signal.id
