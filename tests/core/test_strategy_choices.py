"""The admin strategy dropdown, the Python validator and the database CHECK
constraint must offer exactly the same set.

They drifted: the constraint allowed three strategies while Python validated
against all five, so a value Python accepted would be rejected by the database
on write — a failure that only shows up when someone actually changes the
setting.
"""
import re
from pathlib import Path

import pytest

from signals.models import (
    ADMIN_SELECTABLE_STRATEGIES,
    DEFAULT_SIGNAL_STRATEGY,
    SIGNAL_STRATEGIES,
    TRADING_SESSIONS,
)

ROOT = Path(__file__).resolve().parents[2]
ADMIN_TS = ROOT / "web" / "src" / "lib" / "supabase" / "admin.ts"
MIGRATIONS = ROOT / "supabase" / "migrations"


def test_admin_selectable_is_a_subset_of_implemented_strategies():
    assert set(ADMIN_SELECTABLE_STRATEGIES) <= set(SIGNAL_STRATEGIES)


def test_default_strategy_is_selectable():
    assert DEFAULT_SIGNAL_STRATEGY in ADMIN_SELECTABLE_STRATEGIES


def test_session_pinned_strategies_are_not_offered_to_the_admin():
    """A session that pins its own strategy ignores the toggle, so offering
    that strategy in the dropdown would be a control that does nothing."""
    pinned = {s.strategy for s in TRADING_SESSIONS if s.strategy}
    # sr_zone is both pinned (scalp) and selectable for the swing session,
    # which is legitimate — it is the others that must not leak in.
    assert "ict_fvg" in pinned
    assert "ict_fvg" not in ADMIN_SELECTABLE_STRATEGIES
    assert "ce_lwma" not in ADMIN_SELECTABLE_STRATEGIES


def test_admin_dropdown_matches_python():
    if not ADMIN_TS.exists():
        pytest.skip(f"{ADMIN_TS} not present")
    block = re.search(r"export const SIGNAL_STRATEGIES\s*=\s*\[(.*?)\]\s*as const",
                      ADMIN_TS.read_text(), re.S)
    assert block, "SIGNAL_STRATEGIES not found in admin.ts"
    ids = tuple(re.findall(r'id:\s*"([^"]+)"', block.group(1)))
    assert ids == ADMIN_SELECTABLE_STRATEGIES


def test_database_constraint_matches_python():
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))
    assert sql, f"no migrations found in {MIGRATIONS}"
    # The last constraint definition wins, same as applying them in order.
    checks = re.findall(
        r"bot_settings_signal_strategy_check\s*\n?\s*check\s*\(\s*signal_strategy\s+in\s*\(([^)]*)\)",
        sql, re.I)
    assert checks, "bot_settings_signal_strategy_check not found in migrations"
    allowed = tuple(re.findall(r"'([^']+)'", checks[-1]))
    assert allowed == ADMIN_SELECTABLE_STRATEGIES
