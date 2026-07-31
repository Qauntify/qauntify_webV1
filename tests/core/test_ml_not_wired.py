"""The live signal path must not depend on the ML research tree.

`signals/ml/` and `ml/` are scaffolding: a whole training, replay, thresholding
and inference stack exists in-tree, and none of it decides what a user
receives. That is a deliberate choice — the training data's leakage-safety is
not verified end to end (docs/ml-training-progress-report.md) — but it is the
kind of choice that quietly stops being true.

These tests make the claim executable. If a model is ever connected, the right
move is to delete the assertion in the same commit that adds the wiring, and to
put it behind a sampling flag with shadow-recorded verdicts first.
"""
import ast
from pathlib import Path

import pytest

SIGNALS = Path(__file__).resolve().parents[2] / "signals"

# Everything the engine executes to produce and settle a delivered signal.
LIVE_PATH = [
    SIGNALS / "run.py",
    SIGNALS / "xau_scan.py",
    SIGNALS / "composer.py",
    SIGNALS / "outcome_tracker.py",
    SIGNALS / "storage.py",
    SIGNALS / "models.py",
    SIGNALS / "r_model.py",
    SIGNALS / "strategies" / "router.py",
]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("path", LIVE_PATH, ids=lambda p: p.name)
def test_live_module_does_not_import_the_ml_tree(path):
    offenders = {
        name for name in _imported_modules(path)
        if name == "ml" or name.startswith("ml.")
        or name == "signals.ml" or name.startswith("signals.ml.")
    }
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. The ML tree is research "
        "scaffolding and is not wired into the live signal path — see "
        "signals/ml/__init__.py. If this is intentional, gate it behind a "
        "sampling flag with shadow-recorded verdicts and update this test."
    )


def test_strategy_router_dispatches_only_to_rule_detectors():
    """The router is the single place a strategy is chosen. Keeping it free of
    model calls is what makes the claim above checkable in one file."""
    source = (SIGNALS / "strategies" / "router.py").read_text()
    for banned in ("predict", "score_candidate", "expected_r", "keras", "load_model"):
        assert banned not in source, f"router.py references {banned!r}"
