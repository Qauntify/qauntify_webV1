import pytest

# The fake Supabase URL used across these tests (abc.supabase.co) is a real,
# routable domain that stalls for the full connect timeout instead of
# failing fast, so any storage call a test forgets to mock silently eats
# many real seconds instead of raising instantly. These autouse defaults
# make every signals.run-level storage call inert unless a test explicitly
# overrides one with its own monkeypatch.setattr — which simply takes
# precedence, since it runs after this fixture within the same test.

_INERT_RUN_STORAGE_DEFAULTS = {
    "signals.run.latest_ai_event_time": lambda *a, **k: None,
    "signals.run.latest_ai_event_times_since": lambda *a, **k: {},
    "signals.run.latest_signal": lambda *a, **k: None,
    "signals.run.latest_signals_since": lambda *a, **k: {},
    "signals.run.save_ai_event": lambda *a, **k: None,
    "signals.run.save_signal": lambda *a, **k: None,
    "signals.run.save_engine_run": lambda *a, **k: None,
}


@pytest.fixture(autouse=True)
def _no_real_storage_calls(monkeypatch):
    for target, default in _INERT_RUN_STORAGE_DEFAULTS.items():
        monkeypatch.setattr(target, default)
