import json

import pandas as pd

from ml.outcomes.label_v3 import LabelV3Settings, export_labels, resolve_labels


def _candles(rows=70, price=100.0):
    ts = pd.date_range("2024-01-01", periods=rows, freq="5min")
    return pd.DataFrame({"timestamp": ts, "open": price, "high": price + .1, "low": price - .1, "close": price, "volume": 1})


def test_same_candle_tie_is_conservative_stop():
    candles = _candles()
    candles.loc[15, ["high", "low"]] = [103.0, 97.0]
    result = resolve_labels(candles, LabelV3Settings())
    assert result.loc[14, "long_result"] == "AMBIGUOUS_CONSERVATIVE_SL"
    assert result.loc[14, "short_result"] == "AMBIGUOUS_CONSERVATIVE_SL"
    assert result.loc[14, "long_gross_r"] == -1.0
    assert result.loc[14, "short_gross_r"] == -1.0


def test_last_48_rows_are_right_censored():
    result = resolve_labels(_candles())
    assert result["right_censored"].sum() == 48
    assert not result.loc[result["right_censored"], "supervised_eligible"].any()


def test_decision_timestamp_is_bar_close_and_entry_is_next_open():
    result = resolve_labels(_candles())
    assert result.loc[14, "decision_timestamp"] == pd.Timestamp("2024-01-01 01:15")
    assert result.loc[14, "entry_timestamp"] == result.loc[14, "decision_timestamp"]
    assert result.loc[14, "source_bar_open_timestamp"] == pd.Timestamp("2024-01-01 01:10")


def test_material_gap_crossing_is_invalid():
    candles = _candles(100)
    gap = ((pd.Timestamp("2024-01-01 02:00"), pd.Timestamp("2024-01-01 03:00")),)
    result = resolve_labels(candles, material_gaps=gap)
    assert (result["invalid_reason"] == "MATERIAL_SOURCE_GAP").any()


def test_manifest_serializes_unresolved_rows(tmp_path):
    result = resolve_labels(_candles())
    manifest = export_labels(result, tmp_path / "labels")
    stored = json.loads((tmp_path / "labels" / "label_manifest.json").read_text("utf-8"))
    assert stored["rows"] == len(result)
    assert stored["long_results"]["UNRESOLVED"] > 0
    assert manifest["file_checksums"]
