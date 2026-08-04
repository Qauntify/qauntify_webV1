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
    monkeypatch.setattr(xau_scan, "maybe_run_debate", lambda *a, **k: None)

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


def _patch_main_deps(monkeypatch, scan_result):
    monkeypatch.setattr(xau_scan, "load_config", lambda: _cfg())
    monkeypatch.setattr(xau_scan, "fetch_bot_settings",
                        lambda *a, **k: BotSettings())
    monkeypatch.setattr(xau_scan, "scan_once",
                        lambda cfg, settings, session=None: scan_result)


def test_main_writes_heartbeat_with_signal_found_true(monkeypatch):
    calls = []
    _patch_main_deps(monkeypatch, ScanResult(signal=_fake_signal()))
    monkeypatch.setattr(xau_scan, "save_xau_scan_run",
                        lambda run, *a, **k: calls.append(run))

    xau_scan.main()

    assert len(calls) == 1
    assert calls[0]["signal_found"] is True
    assert "run_id" in calls[0] and "finished_at" in calls[0]


def test_main_writes_heartbeat_with_signal_found_false(monkeypatch):
    calls = []
    _patch_main_deps(monkeypatch, ScanResult())
    monkeypatch.setattr(xau_scan, "save_xau_scan_run",
                        lambda run, *a, **k: calls.append(run))

    xau_scan.main()

    assert len(calls) == 1
    assert calls[0]["signal_found"] is False


def test_main_swallows_heartbeat_failure(monkeypatch):
    _patch_main_deps(monkeypatch, ScanResult())

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(xau_scan, "save_xau_scan_run", boom)

    xau_scan.main()  # must not raise
