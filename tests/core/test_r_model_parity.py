"""The R model exists in two languages: signals/r_model.py drives the
calibration report and the gate A/B, web/src/lib/track-record.ts drives the
public page. They must not drift — the whole point of r_model.py is that there
is one answer to "what was this trade worth".

This test reads the TypeScript and asserts the numbers match. It is deliberately
crude: a real shared artifact would be worth building only if the model grows
past a handful of constants.
"""
import re
from pathlib import Path

import pytest

from signals.r_model import COST_BPS, DEFAULT_COST_BPS, scaled_r

TS_PATH = (Path(__file__).resolve().parents[2]
           / "web" / "src" / "lib" / "track-record.ts")


def _ts_source() -> str:
    if not TS_PATH.exists():
        pytest.skip(f"{TS_PATH} not present")
    return TS_PATH.read_text()


def test_cost_table_matches_the_typescript_port():
    source = _ts_source()
    block = re.search(r"const COST_BPS[^=]*=\s*\{(.*?)\}", source, re.S)
    assert block, "COST_BPS table not found in track-record.ts"
    ts_costs = {
        symbol: float(value)
        for symbol, value in re.findall(r"(\w+)\s*:\s*([\d.]+)", block.group(1))
    }
    assert ts_costs == COST_BPS


def test_default_cost_matches_the_typescript_port():
    source = _ts_source()
    match = re.search(r"const DEFAULT_COST_BPS\s*=\s*([\d.]+)", source)
    assert match, "DEFAULT_COST_BPS not found in track-record.ts"
    assert float(match.group(1)) == DEFAULT_COST_BPS


@pytest.mark.parametrize("reached,stopped,expected", [
    (3, False, 2.0),        # full run to the last target
    (2, True, 2 / 3),       # TP2 banked, last third stopped at full risk
    (1, True, -1 / 3),      # TP1 banked and still a net loss
    (0, True, -1.0),        # stopped before any target
    (0, False, 0.0),        # untouched expiry
])
def test_scale_out_reference_values(reached, stopped, expected):
    """Pins the numbers quoted to users in MethodologyNote.tsx. If any of these
    change, that copy is wrong and has to change with them."""
    assert scaled_r("long", 100, 98, [102, 104, 106], reached, stopped) \
        == pytest.approx(expected)
