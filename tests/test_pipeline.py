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


def _config():
    return Config(
        sealion_api_key="sk-test",
        supabase_url="https://abc.supabase.co",
        supabase_service_key="service-key",
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


def _capture_saves(monkeypatch):
    """Replace run.save_signal with a recorder; returns the call list."""
    saved = []

    def fake_save(signal, supabase_url, service_key, session=None):
        saved.append((signal, supabase_url, service_key))

    monkeypatch.setattr(run_module, "save_signal", fake_save)
    return saved


def _capture_ai_events(monkeypatch):
    """Replace run.save_ai_event with a recorder; returns the call list."""
    events = []

    def fake_save(event, supabase_url, service_key, session=None):
        events.append((event, supabase_url, service_key))

    monkeypatch.setattr(run_module, "save_ai_event", fake_save)
    return events


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


def test_scan_symbol_no_setup_stores_nothing(monkeypatch):
    # Flat prices produce no crossover → real detector returns None.
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol: [])
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"rationale": "Indicators flat."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    assert result.signal is None
    assert result.no_signal is not None
    assert result.no_signal.kind == "no_setup"
    assert saved == []
    assert len(events) == 1
    assert events[0][0]["kind"] == "no_setup"


def test_scan_symbol_no_setup_returns_no_signal_report(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol: ["Bitcoin steady"])
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"rationale": "No EMA crossover yet."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    assert result.signal is None
    assert result.no_signal is not None
    assert result.no_signal.kind == "no_setup"
    assert result.no_signal.rationale == "No EMA crossover yet."
    assert saved == []
    assert len(events) == 1


def test_scan_symbol_confirmed_signal_is_stored(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol: ["BTC rally continues"])
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "Aligned."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    signal = result.signal
    assert signal is not None
    assert signal.confidence == 82
    assert len(saved) == 1
    stored_signal, url, key = saved[0]
    assert stored_signal is signal
    assert url == "https://abc.supabase.co"
    assert key == "service-key"
    assert stored_signal.news_headlines == ["BTC rally continues"]
    assert len(events) == 1
    assert events[0][0]["kind"] == "confirm"


def test_scan_symbol_rejected_signal_not_stored(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol: [])
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "reject", "confidence": 25, "rationale": "Bearish news."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    assert result.signal is None
    assert result.no_signal is not None
    assert result.no_signal.kind == "rejected"
    assert result.no_signal.rationale == "Bearish news."
    assert saved == []
    assert len(events) == 1
    assert events[0][0]["kind"] == "reject"


def test_scan_symbol_news_failure_proceeds_with_empty_headlines(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def broken_news(symbol):
        raise RuntimeError("all RSS feeds unavailable")

    monkeypatch.setattr(run_module, "fetch_headlines", broken_news)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    _capture_saves(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 70, "rationale": "ok"}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    signal = result.signal
    assert signal is not None
    assert signal.news_headlines == []


def test_scan_symbol_binance_failure_returns_none(monkeypatch):
    def broken_candles(symbol, interval, limit):
        raise RuntimeError("binance down")

    monkeypatch.setattr(run_module, "fetch_candles", broken_candles)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    llm = FakeLLM(reply="{}")

    assert scan_symbol("BTCUSDT", _config(), llm) == run_module.ScanResult()


def test_scan_symbol_storage_failure_discards_without_raising(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol: [])
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)

    def broken_save(signal, supabase_url, service_key, session=None):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(run_module, "save_signal", broken_save)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "ok"}')

    assert scan_symbol("BTCUSDT", _config(), llm) == run_module.ScanResult()


def test_scan_symbol_never_prints_news_secrets(monkeypatch, capsys):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def leaky_news(symbol):
        # Guards the invariant that news exception text (which could embed a
        # URL with credentials, depending on the source) is never printed.
        raise RuntimeError(
            "401 Client Error for url: https://news.example.com/api"
            "?auth_token=SECRET-TOKEN-123&currencies=BTC"
        )

    monkeypatch.setattr(run_module, "fetch_headlines", leaky_news)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    _capture_saves(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 70, "rationale": "ok"}')

    scan_symbol("BTCUSDT", _config(), llm)

    captured = capsys.readouterr()
    assert "SECRET-TOKEN-123" not in captured.out
    assert "SECRET-TOKEN-123" not in captured.err


def test_scan_symbol_drops_forming_candle(monkeypatch):
    candles = _flat_candles(n=200)
    forming = Candle(open_time=999, open=100.0, high=1000.0,
                     low=99.0, close=999.0, volume=1.0)
    seen = {}

    def capture_detect(symbol, candles, *series):
        seen["candles"] = candles
        return None

    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: candles + [forming])
    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    llm = FakeLLM(reply="{}")

    scan_symbol("BTCUSDT", _config(), llm)

    assert seen["candles"][-1].close == 100.0  # forming 999-close bar excluded
    assert len(seen["candles"]) == 200
