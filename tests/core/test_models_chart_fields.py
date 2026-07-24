from dataclasses import asdict, replace

from signals.models import (
    CandidateSetup, Confirmation, make_signal,
)


def _signal():
    setup = CandidateSetup("BTCUSD", "long", 100.0, 99.0, 101.0,
                           {"strategy": "ict_fvg"}, take_profit_2=102.0,
                           take_profit_3=103.0)
    return make_signal(setup, Confirmation("confirm", 70, "ok"), [], timeframe="5m")


def test_make_signal_defaults_chart_fields_to_none():
    signal = _signal()
    assert signal.chart_url is None
    assert signal.chart_data is None


def test_signal_asdict_includes_chart_fields():
    signal = replace(_signal(), chart_url="http://x/y.png",
                     chart_data={"plan": []})
    payload = asdict(signal)
    assert payload["chart_url"] == "http://x/y.png"
    assert payload["chart_data"] == {"plan": []}
