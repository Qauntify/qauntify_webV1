"""CLI entry point for the real-time outcome watcher.

Implementation lives in signals.outcomes.realtime so this module stays a thin
wrapper for `python -m signals.realtime_watcher` compatibility.
"""
from signals.outcomes.realtime import main

if __name__ == "__main__":
    main()
