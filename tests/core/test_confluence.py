from signals.config import Config
from signals.models import BotSettings, Candle, CandidateSetup, Confirmation, make_signal
from signals.pipeline import confluence as confluence_module


def _config():
    return Config(
        sealion_api_key="sk-test",
        supabase_url="https://abc.supabase.co",
        supabase_service_key="service-key",
    )


def _settings():
    return BotSettings()


def _signal(symbol="BTCUSD", direction="long", strategy="cloud_mss",
           timeframe="15m", confidence=70):
    setup = CandidateSetup(
        symbol=symbol, direction=direction, entry=100.0, stop_loss=98.0,
        take_profit=104.0, indicators={"strategy": strategy},
    )
    confirmation = Confirmation("confirm", confidence, "looks good")
    return make_signal(setup, confirmation, [], timeframe=timeframe)


def test_detect_confluence_publishes_when_different_strategy_already_open(monkeypatch):
    signal = _signal(strategy="cloud_mss", timeframe="15m")
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "1h", "indicators": {"strategy": "msnr"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: False)
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))
    sent = []
    monkeypatch.setattr(confluence_module, "maybe_send_alert",
                        lambda sig, *a, **k: sent.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert len(published) == 1
    confluence = published[0]
    assert confluence.timeframe == "confluence"
    assert confluence.indicators["confluence_of"] == ["cloud_mss@15m", "msnr@1h"]
    assert confluence.indicators["source_timeframe"] == "15m"
    assert confluence.entry == signal.entry
    assert confluence.stop_loss == signal.stop_loss
    assert confluence.confidence == signal.confidence
    assert saved == [confluence]
    assert sent == [confluence]


def test_detect_confluence_skips_when_no_other_strategy_open(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    monkeypatch.setattr(confluence_module, "open_signals_same_direction",
                        lambda *a, **k: [])
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert published == []
    assert saved == []


def test_detect_confluence_skips_when_confluence_already_open(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "1h", "indicators": {"strategy": "msnr"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: True)
    saved = []
    monkeypatch.setattr(confluence_module, "save_signal",
                        lambda sig, *a, **k: saved.append(sig))

    published = confluence_module.detect_confluence(
        [signal], {}, _settings(), _config())

    assert published == []
    assert saved == []


def test_detect_confluence_attaches_chart_when_candles_available(monkeypatch):
    signal = _signal(symbol="ETHUSD", timeframe="1h")
    candles = [Candle(open_time=0, open=100, high=101, low=99,
                      close=100, volume=1.0)]
    monkeypatch.setattr(
        confluence_module, "open_signals_same_direction",
        lambda *a, **k: [{"timeframe": "5m", "indicators": {"strategy": "ict_fvg"}}],
    )
    monkeypatch.setattr(confluence_module, "has_open_confluence_signal",
                        lambda *a, **k: False)
    monkeypatch.setattr(confluence_module, "save_signal", lambda *a, **k: None)
    monkeypatch.setattr(confluence_module, "maybe_send_alert", lambda *a, **k: None)

    charted = []

    def fake_attach(sig, candles_arg, **kwargs):
        charted.append((sig, candles_arg))
        return sig

    monkeypatch.setattr(confluence_module, "attach_chart", fake_attach)

    confluence_module.detect_confluence(
        [signal], {("ETHUSD", "1h"): candles}, _settings(), _config())

    assert len(charted) == 1
    assert charted[0][1] == candles


def test_detect_confluence_skips_signal_with_no_strategy_tag(monkeypatch):
    signal = _signal(strategy="cloud_mss")
    # Simulate a signal whose indicators never got a strategy tag -- must not
    # crash, must not query, must not publish.
    from dataclasses import replace
    untagged = replace(signal, indicators={})

    called = []
    monkeypatch.setattr(confluence_module, "open_signals_same_direction",
                        lambda *a, **k: called.append(1) or [])

    published = confluence_module.detect_confluence(
        [untagged], {}, _settings(), _config())

    assert published == []
    assert called == []
