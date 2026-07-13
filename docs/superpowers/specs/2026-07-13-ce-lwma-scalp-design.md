# 15m CE + LWMA Strategy Design

Date: 2026-07-13

## Goal

Replace the 15m scalp detector with Chandelier Exit (H1) + LWMA200 (M15) trend/zone logic. Keep 1h swing on the existing admin `ema_cross` / `ict_smc` strategy. Add multi-level take-profits (1R / 2R / 3R) with Telegram + status updates on each TP hit; full close on TP3 or SL.

## Decisions (approved)

- **Approach A**: hardcode `ce_lwma` on the scalp `TradingSession`; swing uses `bot_settings.signal_strategy`.
- **Entry**: fresh H1 CE direction flip only, gated by zone:
  - Long: CE flips bullish AND discount (CE below LWMA200)
  - Short: CE flips bearish AND premium (CE above LWMA200)
- **CE params**: H1, ATR period 22, multiplier 4.5, lookback 22. CE1 and CE2 use the same settings — implement one CE series (duplicate values optional for display parity).
- **MA**: M15 LWMA period 200 on close.
- **Risk**: entry = last closed M15 close; SL = active CE trail; TP1/TP2/TP3 = 1R / 2R / 3R where R = |entry − SL|.
- **Outcomes**: `open` → `tp1_hit` → `tp2_hit` → `tp3_hit` (terminal win); `sl_hit` possible anytime; Telegram on each new level; no breakeven SL move; no partial P&L sizing.
- **LLM**: keep existing confirm/reject gate for stored signals.

## Architecture

1. `signals/indicators.py` — add `lwma`, `chandelier_exit`.
2. `signals/strategies/ce_lwma/detector.py` — `detect_setup` for scalp.
3. `TradingSession.strategy` optional field; scalp = `ce_lwma`, swing = None (use global).
4. `run.py` — for scalp fetch H1 candles for CE; compute LWMA on M15; route via session strategy.
5. Multi-TP data model per `docs/superpowers/specs/2026-07-09-multi-level-take-profit-design.md` (not yet implemented): columns `take_profit_1/2/3`, statuses `tp1_hit`/`tp2_hit`/`tp3_hit`, timestamps; migrate away from single `take_profit` / `tp_hit`.
6. Outcome tracker walks candles, emits ordered events, Telegram per event.
7. Composer/UI/export/stats updated for new strategy indicators and multi-TP statuses.

## Out of scope

- Breakeven after TP1
- Applying CE/LWMA to 1h swing
- Admin toggle for scalp strategy
- Web push
