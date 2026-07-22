from signals import run as run_module
from signals.config import Config
from signals.models import BotSettings, Candle, CandidateSetup
from signals.run import scan_symbol, with_retry

import pytest


@pytest.fixture(autouse=True)
def _stub_rag(monkeypatch):
    """Pipeline unit tests do not hit Supabase for RAG."""
    monkeypatch.setattr(run_module, "retrieve_context", lambda *a, **k: "")


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


def _patch_engine_lock(monkeypatch):
    """main() acquires a DB lock; tests without Supabase always pass it."""
    monkeypatch.setattr(run_module, "try_acquire_engine_lock",
                        lambda *a, **k: True)
    monkeypatch.setattr(run_module, "release_engine_lock",
                        lambda *a, **k: None)


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
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"rationale": "No EMA crossover yet."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    assert result.signal is None
    assert result.no_signal is not None
    assert result.no_signal.kind == "no_setup"
    assert "no valid trade setup" in result.no_signal.rationale.lower()
    assert saved == []
    assert len(events) == 1


def test_scan_symbol_confirmed_signal_is_stored(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
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
    # Purely technical: no news is fetched or stored.
    assert stored_signal.news_headlines == []
    assert len(events) == 1
    assert events[0][0]["kind"] == "confirm"


def test_scan_symbol_rejected_signal_not_stored(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    saved = _capture_saves(monkeypatch)
    events = _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "reject", "confidence": 25, "rationale": "Bearish setup."}')

    result = scan_symbol("BTCUSDT", _config(), llm)

    assert result.signal is None
    assert result.no_signal is not None
    assert result.no_signal.kind == "rejected"
    assert result.no_signal.rationale == "Bearish setup."
    assert saved == []
    assert len(events) == 1
    assert events[0][0]["kind"] == "reject"


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
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)

    def broken_save(signal, supabase_url, service_key, session=None):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(run_module, "save_signal", broken_save)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "ok"}')

    result = scan_symbol("BTCUSDT", _config(), llm)
    assert result.signal is None
    assert result.no_signal is None


def test_scan_symbol_drops_forming_candle(monkeypatch):
    candles = _flat_candles(n=200)
    forming = Candle(open_time=999, open=100.0, high=1000.0,
                     low=99.0, close=999.0, volume=1.0)
    seen = {}

    def capture_detect(strategy, symbol, candles, *series, **kwargs):
        seen["candles"] = candles
        return None

    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        candles + [forming])
    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    llm = FakeLLM(reply="{}")

    scan_symbol("BTCUSDT", _config(), llm)

    assert seen["candles"][-1].close == 100.0  # forming 999-close bar excluded
    assert len(seen["candles"]) == 200


def _rising_candles(n=40, start=100.0, step=1.0):
    return [
        Candle(open_time=i, open=start + i * step, high=start + i * step + 1.0,
              low=start + i * step - 1.0, close=start + i * step, volume=1.0)
        for i in range(n)
    ]


def _falling_candles(n=40, start=140.0, step=1.0):
    return [
        Candle(open_time=i, open=start - i * step, high=start - i * step + 1.0,
              low=start - i * step - 1.0, close=start - i * step, volume=1.0)
        for i in range(n)
    ]


def test_fetch_htf_trend_up_when_fast_ema_above_slow(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _rising_candles())
    assert run_module._fetch_htf_trend("BTCUSDT", "1h", _config()) == "up"


def test_fetch_htf_trend_down_when_fast_ema_below_slow(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _falling_candles())
    assert run_module._fetch_htf_trend("BTCUSDT", "1h", _config()) == "down"


def test_fetch_htf_trend_raises_on_fetch_failure(monkeypatch):
    def boom(symbol, interval, limit, session=None):
        raise RuntimeError("binance down")

    monkeypatch.setattr(run_module, "fetch_candles", boom)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    import pytest
    with pytest.raises(RuntimeError):
        run_module._fetch_htf_trend("BTCUSDT", "1h", _config())


def test_fetch_htf_trend_none_during_warmup(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _rising_candles(n=5))
    assert run_module._fetch_htf_trend("BTCUSDT", "1h", _config()) is None


def test_scan_symbol_computes_and_passes_adx_to_detect_setup(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    seen = {}

    def capture_detect(strategy, symbol, candles, ema9, ema21, rsi14, macd_hist,
                       atr14, adx14=None, htf_trend=None, h1_candles=None):
        seen["adx14"] = adx14
        return None

    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    llm = FakeLLM(reply='{"rationale": "flat"}')

    scan_symbol("BTCUSDT", _config(), llm)

    assert seen["adx14"] is not None
    assert len(seen["adx14"]) == 199  # 200 candles minus the dropped forming one
    assert seen["adx14"][-1] is not None


def test_scan_symbol_passes_htf_trend_when_confluence_timeframe_given(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())
    monkeypatch.setattr(run_module, "_fetch_htf_trend",
                        lambda symbol, timeframe, cfg, session=None: "up")
    seen = {}

    def capture_detect(strategy, symbol, candles, ema9, ema21, rsi14, macd_hist,
                       atr14, adx14=None, htf_trend=None, h1_candles=None):
        seen["htf_trend"] = htf_trend
        return None

    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    llm = FakeLLM(reply='{"rationale": "flat"}')

    scan_symbol("BTCUSDT", _config(), llm, confluence_timeframe="1h")

    assert seen["htf_trend"] == "up"


def test_scan_symbol_skips_htf_fetch_without_confluence_timeframe(monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: _flat_candles())

    def must_not_fetch(symbol, timeframe, cfg, session=None):
        raise AssertionError("no confluence_timeframe given; HTF trend must not be fetched")

    monkeypatch.setattr(run_module, "_fetch_htf_trend", must_not_fetch)
    seen = {}

    def capture_detect(strategy, symbol, candles, ema9, ema21, rsi14, macd_hist,
                       atr14, adx14=None, htf_trend=None, h1_candles=None):
        seen["htf_trend"] = htf_trend
        return None

    monkeypatch.setattr(run_module, "detect_setup", capture_detect)
    llm = FakeLLM(reply='{"rationale": "flat"}')

    scan_symbol("BTCUSDT", _config(), llm)

    assert seen["htf_trend"] is None


def test_scan_symbol_returns_candles_for_reuse(monkeypatch):
    candles = _flat_candles(n=200)
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None: candles)
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
    monkeypatch.setattr(run_module, "save_signal", capture_save)
    _capture_ai_events(monkeypatch)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')

    marker = object()
    scan_symbol("BTCUSDT", _config(), llm, session=marker)

    assert sessions_seen["candles"] is marker
    assert sessions_seen["save"] is marker


def test_main_scans_run_in_parallel_and_keep_symbol_order(monkeypatch):
    _patch_engine_lock(monkeypatch)
    import threading

    settings = BotSettings(
        symbols=("BTCUSDT", "ETHUSDT", "PAXGUSDT"))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])

    # 3 symbols per session; the barrier is reused across the two sessions'
    # sequential batches since each ThreadPoolExecutor fully drains before
    # the next session starts.
    started = threading.Barrier(3, timeout=5)
    scanned = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
                  session=None, recent_events=None, recent_signals=None,
                  open_symbols=None, confluence_timeframe=None,
                  min_store_confidence=0):
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
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
        session=None, recent_events=None, recent_signals=None,
        open_symbols=None, confluence_timeframe=None, min_store_confidence=0:
        run_module.ScanResult())

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
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    candles = _flat_candles(n=5)
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
        session=None, recent_events=None, recent_signals=None,
        open_symbols=None, confluence_timeframe=None, min_store_confidence=0:
        run_module.ScanResult(candles=candles))

    seen = {}

    def capture_track(cfg, prefetched=None, session=None):
        seen["prefetched"] = prefetched
        return []

    monkeypatch.setattr(run_module, "track_open_signals", capture_track)
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    run_module.main()

    assert seen["prefetched"] == {
        ("BTCUSDT", "5m"): candles,
        ("BTCUSDT", "15m"): candles,
        ("BTCUSDT", "1h"): candles,
    }


def test_trading_sessions_define_scalp_and_swing():
    from signals.models import TRADING_SESSIONS

    by_name = {s.name: s for s in TRADING_SESSIONS}
    assert set(by_name) == {"super_scalp", "scalp", "swing"}
    assert by_name["super_scalp"].timeframe == "5m"
    assert by_name["super_scalp"].strategy == "ict_fvg"
    assert by_name["super_scalp"].confluence_timeframe == "15m"
    assert by_name["scalp"].timeframe == "15m"
    assert by_name["swing"].timeframe == "1h"
    # Scalp must expire much faster than swing: a 15m setup that sat open
    # for two weeks is meaningless.
    assert by_name["scalp"].max_open_days < by_name["swing"].max_open_days
    assert by_name["super_scalp"].max_open_days <= by_name["scalp"].max_open_days
    # Scalp is hardcoded to sr_zone (no HTF confluence gate) — best backtested
    # frequency + TP-hit rate on 15m.
    assert by_name["scalp"].strategy == "sr_zone"
    assert by_name["scalp"].confluence_timeframe is None
    assert by_name["swing"].confluence_timeframe == "4h"
    assert by_name["swing"].strategy is None


def test_scan_symbol_uses_the_session_timeframe(monkeypatch):
    seen = {}

    def capture_candles(symbol, interval, limit, session=None):
        seen["interval"] = interval
        return _flat_candles()

    monkeypatch.setattr(run_module, "fetch_candles", capture_candles)
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
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


def test_recently_evaluated_uses_prefetched_map_without_querying(monkeypatch):
    from datetime import datetime, timedelta, timezone

    def boom(*a, **k):
        raise AssertionError("per-symbol query must be skipped when recent_events is given")

    monkeypatch.setattr(run_module, "latest_ai_event_time", boom)

    recent = datetime.now(timezone.utc) - timedelta(minutes=20)
    recent_events = {"BTCUSDT": recent.isoformat()}

    # 20 minutes ago is inside swing's (1h) throttle window.
    assert run_module._recently_evaluated(
        "BTCUSDT", "1h", _config(), recent_events=recent_events) is True
    # A symbol absent from the map is treated as never evaluated.
    assert run_module._recently_evaluated(
        "ETHUSDT", "1h", _config(), recent_events=recent_events) is False


def test_already_signaled_uses_prefetched_map_without_querying(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("per-symbol query must be skipped when recent_signals is given")

    monkeypatch.setattr(run_module, "latest_signal", boom)

    from datetime import datetime, timezone
    recent_signals = {
        "BTCUSDT": {"direction": "long", "created_at": datetime.now(timezone.utc).isoformat()},
    }

    assert run_module.already_signaled(
        SETUP, _config(), timeframe="1h", recent_signals=recent_signals) is True
    # A symbol absent from the map behaves like "no prior signal".
    other_setup = CandidateSetup(
        symbol="ETHUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0, indicators={})
    assert run_module.already_signaled(
        other_setup, _config(), timeframe="1h", recent_signals=recent_signals) is False


def test_main_prefetches_recent_maps_once_per_session_not_per_symbol(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT", "ETHUSDT", "PAXGUSDT"))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
        session=None, recent_events=None, recent_signals=None,
        open_symbols=None, confluence_timeframe=None, min_store_confidence=0:
        run_module.ScanResult())
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    events_calls = []
    signals_calls = []
    monkeypatch.setattr(
        run_module, "latest_ai_event_times_since",
        lambda symbols, timeframe, since, url, key, session=None:
        events_calls.append((tuple(symbols), timeframe)) or {})
    monkeypatch.setattr(
        run_module, "latest_signals_since",
        lambda symbols, timeframe, since, url, key, session=None:
        signals_calls.append((tuple(symbols), timeframe)) or {})

    run_module.main()

    # One batched call per session (3 sessions), each covering all 3
    # symbols — not one call per symbol.
    assert events_calls == [
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "5m"),
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "15m"),
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "1h"),
    ]
    assert signals_calls == [
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "5m"),
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "15m"),
        (("BTCUSDT", "ETHUSDT", "PAXGUSDT"), "1h"),
    ]


def test_main_passes_prefetched_maps_into_scan_symbol(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    sentinel_events = {"BTCUSDT": "2026-07-09T00:00:00+00:00"}
    sentinel_signals = {"BTCUSDT": {"direction": "long", "created_at": "2026-07-09T00:00:00+00:00"}}
    monkeypatch.setattr(run_module, "latest_ai_event_times_since",
                        lambda *a, **k: sentinel_events)
    monkeypatch.setattr(run_module, "latest_signals_since",
                        lambda *a, **k: sentinel_signals)

    seen = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
                  session=None, recent_events=None, recent_signals=None,
                  open_symbols=None, confluence_timeframe=None,
                  min_store_confidence=0):
        seen.append((recent_events, recent_signals))
        return run_module.ScanResult()

    monkeypatch.setattr(run_module, "scan_symbol", fake_scan)

    run_module.main()

    assert all(pair == (sentinel_events, sentinel_signals) for pair in seen)


def test_main_scans_every_symbol_in_both_sessions(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT", "ETHUSDT"))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])

    scanned = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe,
                  feed_titles=None, calendar_events=None, session=None, recent_events=None,
                  recent_signals=None, open_symbols=None,
                  confluence_timeframe=None, min_store_confidence=0):
        scanned.append((symbol, timeframe))
        return run_module.ScanResult()

    monkeypatch.setattr(run_module, "scan_symbol", fake_scan)
    runs = []
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: runs.append(run))

    run_module.main()

    assert sorted(scanned) == [
        ("BTCUSDT", "15m"), ("BTCUSDT", "1h"), ("BTCUSDT", "5m"),
        ("ETHUSDT", "15m"), ("ETHUSDT", "1h"), ("ETHUSDT", "5m"),
    ]
    outcomes = runs[0]["outcomes"]
    assert [(o["symbol"], o["timeframe"]) for o in outcomes] == [
        ("BTCUSDT", "5m"), ("ETHUSDT", "5m"),
        ("BTCUSDT", "15m"), ("ETHUSDT", "15m"),
        ("BTCUSDT", "1h"), ("ETHUSDT", "1h"),
    ]


def test_main_passes_each_sessions_confluence_timeframe_to_scan_symbol(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(run_module, "track_open_signals",
                        lambda cfg, prefetched=None, session=None: [])
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    seen = []

    def fake_scan(symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
                  session=None, recent_events=None, recent_signals=None,
                  open_symbols=None, confluence_timeframe=None,
                  min_store_confidence=0):
        seen.append((timeframe, confluence_timeframe))
        return run_module.ScanResult()

    monkeypatch.setattr(run_module, "scan_symbol", fake_scan)

    run_module.main()

    assert sorted(seen) == [("15m", None), ("1h", "4h"), ("5m", "15m")]


def test_main_prefetch_is_keyed_by_symbol_and_timeframe(monkeypatch):
    _patch_engine_lock(monkeypatch)
    settings = BotSettings(symbols=("BTCUSDT",))
    candles = _flat_candles(n=5)
    monkeypatch.setattr(run_module, "load_config", _config)
    monkeypatch.setattr(run_module, "fetch_bot_settings",
                        lambda url, key, session=None: settings)
    monkeypatch.setattr(run_module, "_prefetch_open_symbols",
                        lambda *a, **k: set())
    monkeypatch.setattr(
        run_module, "scan_symbol",
        lambda symbol, cfg, llm, *, strategy, timeframe, feed_titles=None, calendar_events=None,
        session=None, recent_events=None, recent_signals=None,
        open_symbols=None, confluence_timeframe=None, min_store_confidence=0:
        run_module.ScanResult(candles=candles))

    seen = {}

    def capture_track(cfg, prefetched=None, session=None):
        seen["prefetched"] = prefetched
        return []

    monkeypatch.setattr(run_module, "track_open_signals", capture_track)
    monkeypatch.setattr(run_module, "save_engine_run",
                        lambda run, url, key, session=None: None)

    run_module.main()

    assert seen["prefetched"] == {
        ("BTCUSDT", "5m"): candles,
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
    _capture_ai_events(monkeypatch)

    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "flat"}'),
                         timeframe="15m")

    assert result.no_signal is not None


def test_scan_symbol_skips_when_throttle_lookup_fails(monkeypatch):
    def boom(symbol, timeframe, url, key, session=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(run_module, "latest_ai_event_time", boom)
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit, session=None:
                        _flat_candles())
    _capture_ai_events(monkeypatch)

    result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "flat"}'),
                         timeframe="1h")

    # Fail closed: skip evaluation when recency cannot be verified.
    assert result.signal is None
    assert result.no_signal is None


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
    _capture_ai_events(monkeypatch)

    swing_result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "x"}'),
                               timeframe="1h")
    scalp_result = scan_symbol("BTCUSDT", _config(), FakeLLM(reply='{"rationale": "x"}'),
                               timeframe="15m")

    assert swing_result == run_module.ScanResult()  # still throttled
    assert scalp_result.no_signal is not None  # 20 min clears the 15m window
