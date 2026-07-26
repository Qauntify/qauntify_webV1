"""Unit tests for the pre-registered confirmation-gate analysis."""
from scripts.gate_report import permutation_p, realised_r


def test_permutation_test_detects_a_real_difference():
    a = [1.0] * 40
    b = [-1.0] * 40
    assert permutation_p(a, b, trials=2000, seed=1) < 0.05


def test_permutation_test_reports_no_difference_for_identical_arms():
    a = [0.5, -1.0, 2.0, -1.0, 0.3] * 12
    assert permutation_p(a, list(a), trials=2000, seed=1) > 0.5


def test_permutation_test_is_not_fooled_by_a_small_noisy_gap():
    """The failure mode this whole experiment exists to avoid: a visible gap
    between arms that is nothing but sampling noise."""
    a = [1.0, -1.0, 2.0, -1.0, 0.5, -1.0]
    b = [1.2, -1.0, 2.4, -1.0, 0.6, -1.0]
    assert permutation_p(a, b, trials=2000, seed=1) > 0.05


def _row(status, **kw):
    row = {"direction": "long", "entry": 100.0, "stop_loss": 99.0,
           "take_profit": 101.0, "take_profit_2": 102.0,
           "take_profit_3": 103.0, "status": status}
    row.update(kw)
    return row


def test_realised_r_full_win_books_every_target():
    # 1R/2R/3R booked a third each = 2R.
    r = realised_r(_row("tp3_hit"))
    assert abs(r - 2.0) < 1e-9


def test_realised_r_clean_stop_is_minus_one():
    assert realised_r(_row("sl_hit")) == -1.0


def test_realised_r_counts_a_banked_tp1_before_a_stop():
    """A trade that banks TP1 then reverses is NOT a full loss — reading the
    final status alone would wrongly score it -1R."""
    r = realised_r(_row("sl_hit", tp1_hit_at="2026-07-20T00:00:00Z"))
    assert abs(r - (1.0 / 3.0)) < 1e-9


def test_realised_r_rejects_zero_risk_rows():
    assert realised_r(_row("sl_hit", stop_loss=100.0)) is None
