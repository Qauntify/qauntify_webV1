from signals.chart.annotations import zone, level, marker, series


def test_zone_orders_prices_and_tags_kind():
    z = zone(101.0, 100.0, 1234, "Fair Value Gap", "fvg")
    assert z["kind"] == "zone"
    assert z["price_top"] == 101.0 and z["price_bottom"] == 100.0
    assert z["start_time"] == 1234 and z["role"] == "fvg"


def test_level_defaults_to_solid_full_width():
    lv = level(100.5, "Entry", "entry")
    assert lv == {"kind": "level", "price": 100.5, "label": "Entry",
                  "role": "entry", "style": "solid", "start_time": None}


def test_marker_carries_order():
    m = marker(42, 99.0, "Liquidity sweep", "liquidity", 1)
    assert m["kind"] == "marker" and m["time"] == 42 and m["order"] == 1


def test_series_holds_points():
    s = series([{"time": 1, "value": 100.0}], "EMA9", "ema-fast")
    assert s["kind"] == "series" and s["points"][0]["value"] == 100.0
