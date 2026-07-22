"""Unit tests for the 1-minute XAUUSD scalper entrypoint."""
from signals import xau_scan
from signals.config import Config
from signals.models import (
    BotSettings,
    CandidateSetup,
    Confirmation,
    ScanResult,
    make_signal,
)


def _cfg():
    return Config(
        sealion_api_key="k1",
        supabase_url="https://x.supabase.co",
        supabase_service_key="svc",
        sealion_api_keys=tuple(f"k{i}" for i in range(1, 8)),
    )


def _fake_signal():
    setup = CandidateSetup("XAUUSD", "long", 2400.0, 2398.0, 2404.0,
                           {"strategy": "ict_fvg"})
    return make_signal(setup, Confirmation("confirm", 75, "ok"), [], timeframe="1m")


def test_scalper_keys_reserves_the_last_three():
    keys = tuple(f"k{i}" for i in range(1, 8))
    assert xau_scan.scalper_keys(keys) == ("k5", "k6", "k7")


def test_scalper_keys_falls_back_when_fewer_than_five():
    assert xau_scan.scalper_keys(("k1", "k2")) == ("k1", "k2")


def test_pick_key_rotates_by_minute():
    keys = ("a", "b", "c")
    assert xau_scan._pick_key(keys, minute=0) == "a"
    assert xau_scan._pick_key(keys, minute=4) == "b"  # 4 % 3 == 1


def test_scan_once_scans_xauusd_1m_ict_fvg_and_alerts(monkeypatch):
    captured = {}

    def fake_scan(symbol, cfg, llm, **kwargs):
        captured["symbol"] = symbol
        captured["kwargs"] = kwargs
        return ScanResult(signal=_fake_signal())

    alerts = []
    monkeypatch.setattr(xau_scan, "scan_symbol", fake_scan)
    monkeypatch.setattr(xau_scan, "maybe_send_alert",
                        lambda sig, settings, cfg: alerts.append(sig))

    xau_scan.scan_once(_cfg(), BotSettings())

    assert captured["symbol"] == "XAUUSD"
    kw = captured["kwargs"]
    assert kw["strategy"] == "ict_fvg"
    assert kw["timeframe"] == "1m"
    assert kw["confluence_timeframe"] is None
    assert kw["skip_recency"] is True
    assert kw["log_no_setup"] is False
    assert len(alerts) == 1


def test_scan_once_uses_a_scalper_key(monkeypatch):
    seen = {}

    def fake_scan(symbol, cfg, llm, **kwargs):
        seen["key"] = llm._api_key
        return ScanResult()

    monkeypatch.setattr(xau_scan, "scan_symbol", fake_scan)
    xau_scan.scan_once(_cfg(), BotSettings())
    assert seen["key"] in ("k5", "k6", "k7")  # never the main engine's k1-k4


def test_scan_once_no_signal_sends_no_alert(monkeypatch):
    monkeypatch.setattr(xau_scan, "scan_symbol",
                        lambda symbol, cfg, llm, **kwargs: ScanResult())
    alerts = []
    monkeypatch.setattr(xau_scan, "maybe_send_alert",
                        lambda *a, **k: alerts.append(1))
    xau_scan.scan_once(_cfg(), BotSettings())
    assert alerts == []
