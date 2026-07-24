from argparse import Namespace

from ml.replay.cli import _effective_limit


def test_explicit_dry_run_date_window_is_not_silently_truncated():
    args = Namespace(limit=None, dry_run=True, start="2024-01-01", end="2024-01-07")
    assert _effective_limit(args) is None


def test_unbounded_dry_run_retains_safety_limit():
    args = Namespace(limit=None, dry_run=True, start=None, end=None)
    assert _effective_limit(args) == 500
