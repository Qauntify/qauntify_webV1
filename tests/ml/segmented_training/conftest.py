"""Skip the segmented-training tests without the optional training stack.

See tests/ml/tuning/conftest.py for why this is a skip and not a hard error.
"""
import pytest

pytest.importorskip("pyarrow", reason="needs requirements-training.txt")
pytest.importorskip("sklearn", reason="needs requirements-training.txt")
pytest.importorskip("joblib", reason="needs requirements-training.txt")
