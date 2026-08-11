import pytest

# The fake Supabase URL used across these tests (abc.supabase.co) is a real,
# routable domain that stalls for the full connect timeout instead of
# failing fast, so any storage call a test forgets to mock silently eats
# many real seconds instead of raising instantly. These autouse defaults
# make every signals.pipeline-level storage call inert unless a test
# explicitly overrides one with its own monkeypatch.setattr — which simply
# takes precedence, since it runs after this fixture within the same test.

_INERT_RUN_STORAGE_DEFAULTS = {
    "signals.pipeline.dedup.latest_ai_event_time": lambda *a, **k: None,
    "signals.pipeline.dedup.latest_ai_event_times_since": lambda *a, **k: {},
    "signals.pipeline.dedup.latest_signal": lambda *a, **k: None,
    "signals.pipeline.dedup.latest_signals_since": lambda *a, **k: {},
    "signals.pipeline.scan.save_ai_event": lambda *a, **k: None,
    "signals.pipeline.scan.save_signal": lambda *a, **k: None,
    "signals.pipeline.engine.save_engine_run": lambda *a, **k: None,
    "signals.pipeline.scan.attach_chart": lambda signal, *a, **k: signal,
    "signals.outcomes.tracker.attach_outcome_chart": lambda *a, **k: None,
    "signals.outcomes.tracker.set_outcome_chart_url": lambda *a, **k: None,
    "signals.outcomes.tracker.list_signals_missing_outcome_chart": lambda *a, **k: [],
    "signals.retention.delete_rows_older_than": lambda *a, **k: None,
}


@pytest.fixture(autouse=True)
def _no_real_storage_calls(monkeypatch):
    for target, default in _INERT_RUN_STORAGE_DEFAULTS.items():
        monkeypatch.setattr(target, default)
