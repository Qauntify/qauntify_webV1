"""Skip the tuning tests when the optional training stack is absent.

`requirements.txt` deliberately stays light so the live engine installs fast.
The offline training deps live in `requirements-training.txt`. Without this
guard a plain `.venv/bin/pytest` aborts COLLECTION on the missing import, which
takes the whole suite down with it — including the ~370 engine tests that have
nothing to do with ML. Skipping is the right failure mode: CI installs the
training extras and still runs everything.
"""
import pytest

pytest.importorskip("pyarrow", reason="needs requirements-training.txt")
