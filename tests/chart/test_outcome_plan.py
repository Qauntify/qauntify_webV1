from signals.models import Candle
from signals.chart.outcome_plan import (
    first_cross, merge_outcome_candles, build_outcome_plan,
)


def _c(t, o, h, l, c):
    return Candle(open_time=t, open=o, high=h, low=l, close=c, volume=0.0)


def test_first_cross_long_and_short():
    ups = [_c(1, 100, 100.5, 99.5, 100), _c(2, 100, 102, 100, 101.5)]
    assert first_cross(ups, 101.0, "long", "tp") == 2
    assert first_cross(ups, 99.0, "long", "sl") is None
    downs = [_c(1, 100, 100.5, 99.5, 100), _c(2, 100, 100, 98, 98.5)]
    assert first_cross(downs, 98.5, "short", "tp") == 2
    assert first_cross(downs, 101.0, "short", "sl") is None


def test_merge_dedupes_sorts_and_finds_entry_time():
    chart_data = {"candles": [{"t": 1, "o": 1, "h": 2, "l": 0, "c": 1},
                              {"t": 2, "o": 1, "h": 2, "l": 0, "c": 1}]}
    window = [_c(2, 5, 6, 4, 5), _c(3, 5, 6, 4, 5)]  # t=2 overlaps -> window wins
    merged, entry_time = merge_outcome_candles(chart_data, window)
    assert [c.open_time for c in merged] == [1, 2, 3]
    assert merged[1].close == 5  # window candle won the t=2 collision
    assert entry_time == 2  # last snapshot candle


def test_merge_drops_orphaned_snapshot_across_time_hole():
    """Setup snapshot + later window with missing middle bars must not paint a gap."""
    chart_data = {"candles": [
        {"t": 0, "o": 5050, "h": 5051, "l": 5049, "c": 5050},
        {"t": 60_000, "o": 5050, "h": 5052, "l": 5048, "c": 5049},
    ]}
    # Hole: next kept bars start minutes later near TP prices.
    window = [
        _c(600_000, 4980, 4982, 4978, 4979),
        _c(660_000, 4979, 4980, 4970, 4971),
        _c(720_000, 4971, 4972, 4965, 4966),
    ]
    merged, entry_time = merge_outcome_candles(chart_data, window)
    assert [c.open_time for c in merged] == [600_000, 660_000, 720_000]
    assert entry_time == 600_000


def test_merge_without_snapshot_falls_back_to_window():
    window = [_c(10, 1, 2, 0, 1), _c(11, 1, 2, 0, 1)]
    merged, entry_time = merge_outcome_candles(None, window)
    assert [c.open_time for c in merged] == [10, 11]
    assert entry_time == 10


def _win_row():
    return {"symbol": "XAUUSD", "timeframe": "5m", "direction": "long",
            "entry": 100.0, "stop_loss": 98.0, "take_profit_1": 101.0,
            "take_profit_2": 102.0, "take_profit_3": 103.0}


def _rising_candles():
    # entry at t=0 (100), rising through 101,102,103
    return [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 101.2, 100, 101),
            _c(2, 101, 102.2, 101, 102), _c(3, 102, 103.2, 102, 103)]


def test_build_outcome_plan_win_has_ticks_flag_and_zone():
    plan = build_outcome_plan(_win_row(), "tp3_hit", _rising_candles(), 0)
    roles = [a["role"] for a in plan]
    assert roles.count("target") >= 3  # TP1/TP2/TP3 levels
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "TP1 ✓" in labels and "TP2 ✓" in labels and "✓ TP3 HIT" in labels
    win_zones = [a for a in plan if a["kind"] == "zone" and a["role"] == "win"]
    assert win_zones and win_zones[0].get("end_time") == 3  # TP3 hit bar
    levels = [a for a in plan if a["kind"] == "level"]
    assert all(a.get("start_time") == 0 for a in levels)
    assert all(a.get("end_time") == 3 for a in levels)


def test_build_outcome_plan_loss_shows_partial_and_stop():
    row = _win_row()
    # Pure stop: never tags TP1.
    candles = [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 100, 97.5, 98)]
    plan = build_outcome_plan(row, "sl_hit", candles, 0)
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "TP1 ✓" not in labels
    assert "✗ SL HIT" in labels
    loss_zones = [a for a in plan if a["kind"] == "zone" and a["role"] == "loss"]
    assert loss_zones and loss_zones[0].get("end_time") == 1  # SL hit bar
    # Unused TPs stay off the chart so a stop doesn't zoom into empty air.
    assert not any(
        a["kind"] == "level" and a["label"].startswith("TP") for a in plan
    )

def test_build_outcome_plan_tp1_then_sl_counts_as_win():
    row = {**_win_row(), "tp1_hit_at": "2026-07-01T01:00:00Z"}
    # Rise through TP1 then drop to SL — still a win once TP1 banked.
    candles = [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 101.2, 100, 101),
               _c(2, 101, 101, 97.5, 98)]
    plan = build_outcome_plan(row, "tp1_hit", candles, 0)
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "TP1 ✓" in labels
    assert "✓ TP1 WIN" in labels
    assert "✗ SL HIT" not in labels
    assert any(a["kind"] == "zone" and a["role"] == "win" for a in plan)
    assert not any(a["kind"] == "zone" and a["role"] == "loss" for a in plan)


def test_build_outcome_plan_closed_tp2_win():
    row = {
        **_win_row(),
        "tp1_hit_at": "2026-07-01T01:00:00Z",
        "tp2_hit_at": "2026-07-01T02:00:00Z",
    }
    candles = [_c(0, 100, 100.2, 99.8, 100), _c(1, 100, 101.2, 100, 101),
               _c(2, 101, 102.2, 101, 102), _c(3, 102, 102, 97.5, 98)]
    plan = build_outcome_plan(row, "tp2_hit", candles, 0)
    labels = [a.get("label") for a in plan if a["kind"] == "marker"]
    assert "✓ TP2 WIN" in labels
    assert any(a["kind"] == "zone" and a["role"] == "win" for a in plan)
