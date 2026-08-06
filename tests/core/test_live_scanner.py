"""Live scanner poll cycle."""
from datetime import datetime, timezone

from signals.live_scanner import tick


def test_tick_runs_engine_only_for_due_sessions():
    now_ms = int(datetime(2026, 8, 6, 13, 0, 5, tzinfo=timezone.utc).timestamp() * 1000)

    seen = []

    def fake_run(*, sessions=None):
        seen.append(tuple(s.name for s in sessions))

    last_fired: dict[str, int] = {}
    names = tick(last_fired, now_ms=now_ms, run_fn=fake_run)
    assert set(names) == {"super_scalp", "scalp", "swing"}
    assert len(seen) == 1
    assert set(seen[0]) == {"super_scalp", "scalp", "swing"}

    # Same bar again — no re-fire
    assert tick(last_fired, now_ms=now_ms, run_fn=fake_run) == []
    assert len(seen) == 1


def test_tick_idle_mid_bar():
    now_ms = int(datetime(2026, 8, 6, 13, 2, 30, tzinfo=timezone.utc).timestamp() * 1000)
    called = []
    assert tick({}, now_ms=now_ms, run_fn=lambda **k: called.append(k)) == []
    assert called == []
