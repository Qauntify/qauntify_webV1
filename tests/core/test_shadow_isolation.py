"""Shadow rows must never compete with live signals for the one-open slot.

The one-open-per-symbol+timeframe index exists to stop overlapping engine runs
publishing two live RECOMMENDATIONS. A shadow row is never delivered, so it has
no business inside that constraint — and when it was, inserts failed on the
unique violation and were swallowed by callers that must not break a live scan.
Shadows then went missing exactly when a live signal was open, which is not
random and biases the confirmation-gate A/B.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"

LIVE_INDEX = "signals_one_open_per_symbol_tf"
SHADOW_INDEX = "signals_one_open_shadow_per_experiment"


def _migrations_sql():
    """All migrations concatenated in apply order."""
    paths = sorted(MIGRATIONS.glob("*.sql"))
    assert paths, f"no migrations found in {MIGRATIONS}"
    return "\n".join(p.read_text() for p in paths)


def _definitions(name):
    """Every CREATE body for `name`, in apply order. The last one wins."""
    return re.findall(
        rf"create unique index[^;]*?{name}\b(.*?);",
        _migrations_sql(),
        flags=re.IGNORECASE | re.DOTALL,
    )


def test_live_uniqueness_index_still_exists():
    assert _definitions(LIVE_INDEX), f"{LIVE_INDEX} is not defined anywhere"


def test_live_uniqueness_applies_only_to_delivered_rows():
    """Without this filter a paper/shadow insert collides with a live signal on
    the same market and is silently dropped."""
    final = _definitions(LIVE_INDEX)[-1]
    assert "shadow = false" in final.lower(), (
        f"{LIVE_INDEX} must exclude shadow rows; last definition was:\n{final}"
    )


def test_live_uniqueness_still_covers_the_open_statuses():
    """The original protection must survive the fix."""
    final = _definitions(LIVE_INDEX)[-1].lower()
    for status in ("'open'", "'tp1_hit'", "'tp2_hit'"):
        assert status in final, f"{LIVE_INDEX} no longer covers {status}"


def test_shadows_keep_their_own_one_open_rule_per_experiment():
    """Dropping shadows out of the live index must not let one experiment stack
    duplicate open rows on a single market."""
    definitions = _definitions(SHADOW_INDEX)
    assert definitions, f"{SHADOW_INDEX} is not defined"
    final = definitions[-1].lower()
    assert "shadow = true" in final
    assert "experiment" in final
    assert "symbol" in final and "timeframe" in final


def test_shadow_isolation_migration_applies_after_the_shadow_column():
    """The index filters on `shadow`, so it must sort after the migration that
    adds the column — these run in filename order."""
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    adds_column = next(n for n in names if "shadow_signals" in n)
    fixes_index = next(n for n in names if "shadow_rows_bypass" in n)
    assert names.index(fixes_index) > names.index(adds_column)
