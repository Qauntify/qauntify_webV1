import json
import sqlite3

from signals import run as run_module
from signals.config import Config
from signals.models import Candle, CandidateSetup
from signals.run import scan_symbol, with_retry


def _flat_candles(n=200, price=100.0):
    return [
        Candle(open_time=i, open=price, high=price + 1.0,
               low=price - 1.0, close=price, volume=1.0)
        for i in range(n)
    ]


def _config(tmp_path):
    return Config(
        sealion_api_key="sk-test",
        cryptopanic_api_key="cp-test",
        db_path=str(tmp_path / "signals.db"),
        json_path=str(tmp_path / "signals.json"),
    )


SETUP = CandidateSetup(
    symbol="BTCUSDT", direction="long", entry=100.0,
    stop_loss=98.0, take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)


class FakeLLM:
    def __init__(self, reply):
        self._reply = reply

    def chat(self, messages, temperature=0.2):
        return self._reply


def test_with_retry_returns_after_transient_failure():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "ok"

    assert with_retry(flaky, delay=0.0) == "ok"
    assert len(calls) == 2


def test_with_retry_raises_after_exhausting_attempts():
    def always_fails():
        raise RuntimeError("down")

    try:
        with_retry(always_fails, delay=0.0)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_scan_symbol_no_setup_stores_nothing(tmp_path, monkeypatch):
    # Flat prices produce no crossover → real detector returns None.
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 90, "rationale": "x"}')
    result = scan_symbol("BTCUSDT", cfg, llm)
    assert result is None
    assert not (tmp_path / "signals.json").exists()


def test_scan_symbol_confirmed_signal_is_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, api_key: ["BTC rally continues"])
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "Aligned."}')

    signal = scan_symbol("BTCUSDT", cfg, llm)

    assert signal is not None
    assert signal.confidence == 82
    conn = sqlite3.connect(cfg.db_path)
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 1
    with open(cfg.json_path) as f:
        data = json.load(f)
    assert data[0]["symbol"] == "BTCUSDT"
    assert data[0]["news_headlines"] == ["BTC rally continues"]


def test_scan_symbol_rejected_signal_not_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, api_key: [])
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "reject", "confidence": 25, "rationale": "Bearish news."}')

    result = scan_symbol("BTCUSDT", cfg, llm)

    assert result is None
    assert not (tmp_path / "signals.json").exists()


def test_scan_symbol_news_failure_proceeds_with_empty_headlines(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def broken_news(symbol, api_key):
        raise RuntimeError("cryptopanic down")

    monkeypatch.setattr(run_module, "fetch_headlines", broken_news)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 70, "rationale": "ok"}')

    signal = scan_symbol("BTCUSDT", cfg, llm)

    assert signal is not None
    assert signal.news_headlines == []


def test_scan_symbol_binance_failure_returns_none(tmp_path, monkeypatch):
    def broken_candles(symbol, interval, limit):
        raise RuntimeError("binance down")

    monkeypatch.setattr(run_module, "fetch_candles", broken_candles)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    cfg = _config(tmp_path)
    llm = FakeLLM(reply="{}")

    assert scan_symbol("BTCUSDT", cfg, llm) is None
