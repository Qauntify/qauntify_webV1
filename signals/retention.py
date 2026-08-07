"""Deletes old rows from tables that grow forever with no natural cap:
ai_events (LLM decision audit log), engine_runs / xau_scan_runs (heartbeat
logs, one row per cron/tick cycle). signals and agent_debates are permanent
historical/showcase content and are never pruned here.
"""
from signals.storage import delete_rows_older_than

# (table, date_column, days_to_keep)
_RETENTION = [
    ("ai_events", "created_at", 90),
    ("engine_runs", "finished_at", 30),
    ("xau_scan_runs", "finished_at", 30),
]


def run_retention_cleanup(cfg, session=None) -> None:
    """Best-effort: a failure on one table must not block the others."""
    for table, column, days in _RETENTION:
        try:
            delete_rows_older_than(table, column, days, cfg.supabase_url,
                                   cfg.supabase_service_key, session=session)
        except Exception as exc:
            print(f"retention cleanup failed for {table} "
                  f"({type(exc).__name__}), continuing")
