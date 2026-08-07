"""Tests for signals/retention.py — deletes old rows from tables that grow
forever with no natural cap (ai_events, engine_runs, xau_scan_runs).
signals and agent_debates are permanent content and must never be pruned."""
from signals import retention


class _Cfg:
    supabase_url = "u"
    supabase_service_key = "k"


def test_run_retention_cleanup_covers_every_unbounded_log_table(monkeypatch):
    calls = []
    monkeypatch.setattr(
        retention, "delete_rows_older_than",
        lambda table, column, days, *a, **k: calls.append((table, column, days)))

    retention.run_retention_cleanup(_Cfg())

    tables = [c[0] for c in calls]
    assert "ai_events" in tables
    assert "engine_runs" in tables
    assert "xau_scan_runs" in tables


def test_run_retention_cleanup_never_touches_permanent_content(monkeypatch):
    calls = []
    monkeypatch.setattr(
        retention, "delete_rows_older_than",
        lambda table, column, days, *a, **k: calls.append(table))

    retention.run_retention_cleanup(_Cfg())

    assert "signals" not in calls
    assert "agent_debates" not in calls


def test_run_retention_cleanup_continues_past_a_single_table_failure(monkeypatch):
    calls = []

    def fake_delete(table, column, days, *a, **k):
        calls.append(table)
        if table == "ai_events":
            raise RuntimeError("delete failed")

    monkeypatch.setattr(retention, "delete_rows_older_than", fake_delete)

    retention.run_retention_cleanup(_Cfg())  # must not raise

    assert calls == ["ai_events", "engine_runs", "xau_scan_runs"]
