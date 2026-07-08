from signals import run as run_module
from signals.config import Config
from signals.models import BotSettings, Candle, CandidateSetup
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
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
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
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: ["Bitcoin steady"])
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
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: ["BTC rally continues"])
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
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
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
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def broken_news(symbol, session=None):
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
    def broken_candles(symbol, interval, limit, session=None):
        raise RuntimeError("binance down")

    monkeypatch.setattr(run_module, "fetch_candles", broken_candles)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    llm = FakeLLM(reply="{}")

    assert scan_symbol("BTCUSDT", _config(), llm) == run_module.ScanResult()


def test_scan_symbol_storage_failure_discards_without_raising(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)

    def broken_save(signal, supabase_url, service_key, session=None):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(run_module, "save_signal", broken_save)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "ok"}')

    result = scan_symbol("BTCUSDT", _config(), llm)
    assert result.signal is None
    assert result.no_signal is None


def test_scan_symbol_never_prints_news_secrets(monkeypatch, capsys):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def leaky_news(symbol, session=None):
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

    def capture_detect(strategy, symbol, candles, *series):
        seen["candles"] = candles
        return None

    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        candles + [forming])
    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    llm = FakeLLM(reply="{}")

    scan_symbol("BTCUSDT", _config(), llm)

    assert seen["candles"][-1].close == 100.0  # forming 999-close bar excluded
    assert len(seen["candles"]) == 200


def test_scan_symbol_filters_provided_feed_titles_without_refetching(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def must_not_fetch(symbol, session=None):
        raise AssertionError("feed titles were provided; no network fetch")

    monkeypatch.setattr(run_module, "fetch_headlines", must_not_fetch)
    _capture_saves(monkeypatch)
    _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')

    titles = ["Bitcoin rally continues", "Solana hits new high"]
    result = scan_symbol("BTCUSDT", _config(), llm, feed_titles=titles)

    assert result.signal is not None
    assert result.signal.news_headlines == ["Bitcoin rally continues"]


def test_scan_symbol_returns_candles_for_reuse(monkeypatch):
    candles = _flat_candles(n=200)
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: candles)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"rationale": "flat"}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    # Closed candles come back so the outcome tracker can reuse them.
    assert result.candles == candles[:-1]


def test_scan_symbol_threads_session_through_fetches(monkeypatch):
    sessions_seen = {}

    def capture_candles(symbol, interval, limit, session=None):
        sessions_seen["candles"] = session
        return _flat_candles()

    def capture_save(signal, supabase_url, service_key, session=None):
        sessions_seen["save"] = session

    monkeypatch.setattr(run_module, "fetch_candles", capture_candles)
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    monkeypatch.setattr(run_module, "save_signal", capture_save)
    _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')

    marker = object()
    scan_symbol("BTCUSDT", _config(), llm, session=marker)

    assert sessions_seen["candles"] is marker
    assert sessions_seen["save"] is marker


def test_main_scans_run_in_parallel_and_keep_symbol_order(monkeypatch):
    import threading

    settings = BotSettings(
        symbols=("BTCUSDT", "ETHUSDT", "PAXGUSDT"))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "fetch_feed_titles",
                        lambda session=None: [])
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])

    # 3 symbols per session; the barrier is reused across the two sessions'
    # sequential batches since each ThreadPoolExecutor fully drains before
    # the next session starts.
    started = threading.Barrier(3, timeout=5)
    scanned = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe, feed_titles=None,
                  session=None):
        # Every scan in a session's batch must be in flight before any
        # finishes — proves the loop is parallel, not sequential.
        started.wait()
        scanned.append((symbol, timeframe))
        return run_module.ScanResult()

    monkeypatch.setattr(run_module, "scan_symbol", fake_scan)
    runs = []
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    run_module.main()

    assert sorted(scanned) == sorted(
        (symbol, trading_session.timeframe)
        for trading_session in run_module.TRADING_SESSIONS
        for symbol in settings.symbols
    )
    assert len(runs) == 1


def test_main_reports_expired_signals_in_run_summary(monkeypatch):
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "fetch_feed_titles",
                        lambda session=None: [])
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None,
        session=None: run_module.ScanResult())

    expired_row = {"symbol": "ETHUSDT", "direction": "long", "entry": 100.0}
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None:
                        [(expired_row, "expired")])
    runs = []
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    run_module.main()

    outcomes = runs[0]["outcomes"]
    assert {"symbol": "ETHUSDT", "status": "EXPIRED",
            "extra": "LONG closed"} in outcomes


def test_main_passes_scan_candles_to_outcome_tracker(monkeypatch):
    settings = BotSettings(symbols=("BTCUSDT",))
    candles = _flat_candles(n=5)
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "fetch_feed_titles",
                        lambda session=None: [])
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None,
        session=None: run_module.ScanResult(candles=candles))

    seen = {}

    def capture_track(cfg, prefetched=None, session=None):
        seen["prefetched"] = prefetched
        return []

    monkeypatch.setattr(run_module, "track_open_signals", capture_track)
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    run_module.main()

    assert seen["prefetched"] == {
        ("BTCUSDT", "15m"): candles,
        ("BTCUSDT", "1h"): candles,
    }


def test_trading_sessions_define_scalp_and_swing():
    from signals.models import TRADING_SESSIONS

    by_name = {s.name: s for s in TRADING_SESSIONS}
    assert set(by_name) == {"scalp", "swing"}
    assert by_name["scalp"].timeframe == "15m"
    assert by_name["swing"].timeframe == "1h"
    # Scalp must expire much faster than swing: a 15m setup that sat open
    # for two weeks is meaningless.
    assert by_name["scalp"].max_open_days < by_name["swing"].max_open_days


def test_scan_symbol_uses_the_session_timeframe(monkeypatch):
    seen = {}

    def capture_candles(symbol, interval, limit, session=None):
        seen["interval"] = interval
        return _flat_candles()

    monkeypatch.setattr(run_module, "fetch_candles", capture_candles)
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')

    result = scan_symbol("BTCUSDT", _config(), llm, timeframe="15m")

    assert seen["interval"] == "15m"
    assert result.signal.timeframe == "15m"
    assert saved[0][0].timeframe == "15m"
    assert events[0][0]["timeframe"] == "15m"


def test_already_signaled_dedup_window_scales_with_timeframe(monkeypatch):
    from datetime import datetime, timedelta, timezone

    # Same-direction signal stored 50 minutes ago.
    stored_at = datetime.now(timezone.utc) - timedelta(minutes=50)
    captured = {}

    def fake_latest(symbol, url, key, timeframe=None, session=None):
        captured.setdefault("timeframes", []).append(timeframe)
        return {"direction": "long", "created_at": stored_at.isoformat()}

    monkeypatch.setattr(run_module, "latest_signal", fake_latest)

    # 1h bars: dedup window 3h -> still a duplicate.
    assert run_module.already_signaled(SETUP, _config(), timeframe="1h") is True
    # 15m bars: dedup window 45m -> 50 minutes ago is a fresh setup again.
    assert run_module.already_signaled(SETUP, _config(), timeframe="15m") is False
    # The lookup itself must be per-timeframe so sessions don't block each other.
    assert captured["timeframes"] == ["1h", "15m"]


def test_main_scans_every_symbol_in_both_sessions(monkeypatch):
    settings = BotSettings(symbols=("BTCUSDT", "ETHUSDT"))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "fetch_feed_titles",
                        lambda session=None: [])
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])

    scanned = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe,
                  feed_titles=None, session=None):
        scanned.append((symbol, timeframe))
        return run_module.ScanResult()

    monkeypatch.setattr(run_module, "scan_symbol", fake_scan)
    runs = []
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    run_module.main()

    assert sorted(scanned) == [
        ("BTCUSDT", "15m"), ("BTCUSDT", "1h"),
        ("ETHUSDT", "15m"), ("ETHUSDT", "1h"),
    ]
    outcomes = runs[0]["outcomes"]
    assert [(o["symbol"], o["timeframe"]) for o in outcomes] == [
        ("BTCUSDT", "15m"), ("ETHUSDT", "15m"),
        ("BTCUSDT", "1h"), ("ETHUSDT", "1h"),
    ]


def test_main_prefetch_is_keyed_by_symbol_and_timeframe(monkeypatch):
    settings = BotSettings(symbols=("BTCUSDT",))
    candles = _flat_candles(n=5)
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "fetch_feed_titles",
                        lambda session=None: [])
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None,
        session=None: run_module.ScanResult(candles=candles))

    seen = {}

    def capture_track(cfg, prefetched=None, session=None):
        seen["prefetched"] = prefetched
        return []

    monkeypatch.setattr(run_module, "track_open_signals", capture_track)
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    run_module.main()

    assert seen["prefetched"] == {
        ("BTCUSDT", "15m"): candles,
        ("BTCUSDT", "1h"): candles,
    }


def test_scan_symbol_skips_when_recently_evaluated_this_session(monkeypatch):
    from datetime import datetime, timedelta, timezone

    recent = datetime.now(timezone.utc) - timedelta(minutes=20)
    monkeypatch.setattr(run_module, "latest_ai_event_time",
                        lambda symbol, timeframe, url, key, session=None:
                        recent.isoformat())
    fetch_called = []
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda *a, **k: fetch_called.append(1) or _flat_candles())

    # 20 minutes ago is well inside swing's (1h) throttle window.
    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply="{}"),
                         timeframe="1h")

    assert result == run_module.ScanResult()
    assert fetch_called == []  # market data isn't even fetched — no LLM spam


def test_scan_symbol_runs_when_throttle_window_has_elapsed(monkeypatch):
    from datetime import datetime, timedelta, timezone

    stale = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(run_module, "latest_ai_event_time",
                        lambda symbol, timeframe, url, key, session=None:
                        stale.isoformat())
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    _capture_ai_events(monkeypatch)

    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "flat"}'),
                         timeframe="1h")

    assert result.no_signal is not None  # a real evaluation happened


def test_scan_symbol_runs_when_never_evaluated_before(monkeypatch):
    monkeypatch.setattr(run_module, "latest_ai_event_time",
                        lambda symbol, timeframe, url, key, session=None: None)
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    _capture_ai_events(monkeypatch)

    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "flat"}'),
                         timeframe="15m")

    assert result.no_signal is not None


def test_scan_symbol_proceeds_when_throttle_lookup_fails(monkeypatch):
    def boom(symbol, timeframe, url, key, session=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(run_module, "latest_ai_event_time", boom)
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    _capture_ai_events(monkeypatch)

    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "flat"}'),
                         timeframe="1h")

    assert result.no_signal is not None  # fail open — evaluate rather than go silent


def test_scan_symbol_scalp_throttle_is_shorter_than_swing(monkeypatch):
    from datetime import datetime, timedelta, timezone

    # 20 minutes ago: outside scalp's (15m) throttle window, inside swing's (1h).
    stamp = datetime.now(timezone.utc) - timedelta(minutes=20)
    monkeypatch.setattr(run_module, "latest_ai_event_time",
                        lambda symbol, timeframe, url, key, session=None:
                        stamp.isoformat())
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, session=None: [])
    _capture_ai_events(monkeypatch)

    swing_result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "x"}'),
                               timeframe="1h")
    scalp_result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "x"}'),
                               timeframe="15m")

    assert swing_result == run_module.ScanResult()  # still throttled
    assert scalp_result.no_signal is not None  # 20 min clears the 15m window
