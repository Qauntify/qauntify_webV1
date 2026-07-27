"""Pre-registered analysis for the LLM confirmation-gate A/B.

Fixed in advance (see docs/superpowers/specs/2026-07-26-ai-gate-ab-design.md):

  * primary metric — mean realised R under the engine's scale-out model
  * comparison    — delivered (confirmed) vs shadow (LLM-rejected)
  * test          — two-sided permutation test, alpha = 0.05
  * stopping rule — n = 250 per arm, or 60 days, whichever comes first

Choosing the test after seeing the data is how noise gets promoted to a
finding, so none of the above is adjustable at read time. The script warns
loudly when an arm is below target rather than quietly reporting a p-value that
cannot mean anything yet.

Usage: .venv/bin/python -m scripts.gate_report
"""
import os
import random
import statistics
import sys

from signals.backtest import scaled_r
from signals.storage import list_closed_signals

ALPHA = 0.05
TARGET_N = 250


def permutation_p(a, b, trials=20000, seed=7):
    """Two-sided p for the difference in means.

    Distribution-free on purpose: R-multiples are heavily skewed (a bounded
    -1R downside against a long right tail), so the normal approximation behind
    a t-test is poor at these sample sizes.
    """
    if len(a) < 2 or len(b) < 2:
        return 1.0
    observed = abs(statistics.mean(a) - statistics.mean(b))
    pool = list(a) + list(b)
    split = len(a)
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        rng.shuffle(pool)
        diff = abs(statistics.mean(pool[:split]) - statistics.mean(pool[split:]))
        if diff >= observed:
            hits += 1
    return hits / trials


def realised_r(row):
    """Realised R for one closed signal, or None when it cannot be scored.

    Mirrors the backtester exactly: a third booked at each target, stop trailed
    to breakeven once TP1 is banked. The tp*_hit_at timestamps matter — a trade
    that banked TP1 and then reversed ends with status 'sl_hit' but is not a
    full -1R loss, and scoring it from the final status alone would understate
    every partial win in both arms.
    """
    entry, stop = row.get("entry"), row.get("stop_loss")
    if entry is None or stop is None or entry == stop:
        return None
    tps = [row.get("take_profit"), row.get("take_profit_2"),
           row.get("take_profit_3")]
    tps = [t for t in tps if t is not None]
    if not tps:
        return None
    reached = sum(1 for k in ("tp1_hit_at", "tp2_hit_at", "tp3_hit_at")
                  if row.get(k))
    if row.get("status") in ("tp3_hit", "tp_hit"):
        reached = len(tps)
    return scaled_r(row["direction"], entry, stop, tps,
                    min(reached, len(tps)), row.get("status") == "sl_hit")


def _describe(label, rs):
    if len(rs) < 2:
        print(f"  {label:24} n={len(rs)}")
        return
    print(f"  {label:24} n={len(rs):4d}  mean {statistics.mean(rs):+.3f}R  "
          f"win {sum(1 for r in rs if r > 0) / len(rs) * 100:5.1f}%")


def main():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")

    rows = list_closed_signals(url, key, include_shadow=True)
    delivered = [r for r in rows if not r.get("shadow")]
    # Only this experiment's shadows. Other trials (e.g. the sr_limit paper
    # run) are also stored as shadows; pooling them would compare the gate
    # against an unrelated strategy rather than against its own rejects.
    shadow = [r for r in rows
              if r.get("shadow") and r.get("experiment") == "gate_ab"]
    a = [x for x in (realised_r(r) for r in delivered) if x is not None]
    b = [x for x in (realised_r(r) for r in shadow) if x is not None]

    print("LLM confirmation gate — pre-registered analysis\n")
    _describe("confirmed (delivered)", a)
    _describe("rejected (shadow)", b)

    if len(a) < 2 or len(b) < 2:
        print("\nNot enough data in one or both arms yet.")
        return

    smallest = min(len(a), len(b))
    if smallest < TARGET_N:
        print(f"\n*** WARNING: smallest arm is {smallest}, target is "
              f"{TARGET_N}. ***\nReading the result now risks stopping on "
              "noise — which is the exact failure this experiment exists to "
              "avoid. Reported for monitoring only.")

    diff = statistics.mean(b) - statistics.mean(a)
    p = permutation_p(a, b)
    print(f"\ndifference (shadow - delivered): {diff:+.3f}R")
    print(f"permutation p                  : {p:.3f}")
    if p >= ALPHA:
        print("\nVERDICT: NOT significant — the gate is neither shown to help "
              "nor to hurt.")
    elif diff > 0:
        print("\nVERDICT: significant — REJECTED setups outperformed. The gate "
              "is discarding better trades; remove or invert it.")
    else:
        print("\nVERDICT: significant — confirmed setups outperformed. The "
              "gate is working; consider raising the confidence floor.")


if __name__ == "__main__":
    main()
