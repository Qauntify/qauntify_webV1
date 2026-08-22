"""On-demand pipeline entrypoint. Usage: python -m signals.run"""
import os

from signals.models import sessions_for_timeframes
from signals.pipeline.engine import main as engine_main


def _sessions_from_env():
    """Parse ENGINE_SESSIONS (comma-separated 5m/15m/1h) from GitHub dispatch."""
    raw = os.environ.get("ENGINE_SESSIONS", "").strip()
    if not raw:
        return None
    return sessions_for_timeframes(raw.split(","))


if __name__ == "__main__":
    engine_main(sessions=_sessions_from_env())
