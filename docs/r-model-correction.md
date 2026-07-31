# The R-model correction, 2026-07-28

Every expectancy number this project produced before this date was overstated
by roughly **0.24R per trade**. This records what was wrong, how it was found,
and what the corrected numbers are.

## The bug

`signals/r_model.py` scored a scale-out as though the stop moved to breakeven
once TP1 was banked. `signals/backtest.py::simulate_scaled` and the live
`signals/outcome_tracker.py` both walked a **fixed** stop.

That pairing describes no trade anyone ever made. It credited a position twice:

- **for surviving** a pullback to entry — because the simulation still tracked
  the original, wider stop, so the trade stayed alive and could go on to reach
  TP2 and TP3; and
- **for losing nothing** when the stop finally hit — because the scoring
  assumed the stop had been moved to breakeven.

A real trader gets one or the other, never both. Keep the stop and the unbooked
remainder loses 1R. Move it and you are scratched out before TP2/TP3.

## Why the fixed stop is the correct model

Not a judgement call — it is what the system does:

- `signals/telegram_client.py` publishes `Entry / SL / TP1 / TP2 / TP3` and
  never asks the follower to trail anything.
- `signals/outcome_tracker.py:121` reads `signal_row["stop_loss"]` and settles
  against that same level for the whole life of the trade.

So the data the engine collects is fixed-stop data, and the scoring now matches
it. If the engine ever does start telling followers to trail to breakeven,
`outcome_tracker` has to change first and `r_model` second — never only the
scoring.

## Reference values

| Outcome | Was | Now |
|---|---|---|
| Ran to TP3 | +2.00R | +2.00R |
| TP2 then stopped | +1.00R | **+0.67R** |
| TP1 then stopped | +0.33R | **−0.33R** (a loss, not a win) |
| Stopped before any target | −1.00R | −1.00R |
| Expired untouched | 0.00R | 0.00R |

The TP1 row is the one that mattered most: a trade that banks TP1 and reverses
was counted as a **winner** and is in fact a **loser**.

## Corrected results — 8.87 years, BTC and ETH, verified Binance archives

| Strategy | Reported before | Corrected | Verdict |
|---|---|---|---|
| `sr_limit` 1h (maker) | +0.113R · t=+6.81 · +675R | **−0.015R** · t=−0.94 | indistinguishable from zero |
| `bbma_extreme` | +0.081R · t=+5.88 · +390R | **−0.153R** · t=−10.60 · −738R | losing |
| `bbma_reentry` | +0.111R · t=+8.39 · +531R | **−0.137R** · t=−9.63 · −656R | losing |
| `sr_zone` 15m (taker) | −0.280R | **−0.415R** · −6,711R | losing badly |

**Nothing in the repository has a demonstrated edge.** Every rules strategy
measured over nine years is either losing or statistically indistinguishable
from zero. `sr_limit` — the one that looked promotable, and the reason the
paper trial exists — is flat once scored honestly.

`orb_rvol` could not be measured: it has a spec and a plan but no importable
detector on this branch.

## Blast radius

The same model is ported to TypeScript in `web/src/lib/track-record.ts` and
drives the public `/track-record` page, so the published win rate and
expectancy carried the same overstatement. Both languages are fixed, the
methodology copy in `web/src/components/track-record/MethodologyNote.tsx` is
updated, and `tests/core/test_r_model_parity.py` pins the two together.

Any closed-signal statistics quoted publicly before 2026-07-28 were computed
under the broken model. They are recomputed browser-side from stored rows, so
the page corrects itself once deployed — no backfill is needed.

## How this was found

A BBMA result looked too good: a sub-1R first target hit ~70% of the time,
producing a large positive expectancy. Re-simulating with a stop that genuinely
moved to breakeven after TP1 — rather than one scored as if it had — turned
+389R into −1,209R. That gap was the tell, and it was not BBMA-specific.

The lesson worth keeping: when a strategy's edge appears to come from the exit
rather than the entry, check that the exit being scored is the exit being
simulated.
