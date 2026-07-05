# ThinkTrade Signals Engine — Design

## Context

ThinkTrade is a rebuild of zoqira.pro (an AI-powered trading signals platform for
gold/forex/crypto/stocks). The full platform is a large project spanning a marketing
site, auth, dashboard, billing, and a signals engine. This spec covers the **first
sub-project only: the signals engine** — the core logic that generates AI-confirmed
crypto trading signals. Other subsystems (marketing site, auth, dashboard, billing,
Telegram alerts) are out of scope and will get their own specs later.

## Goal

An on-demand Python script that scans BTCUSDT and ETHUSDT on 1h candles, finds
technical setups, confirms them with an LLM (SEA-LION) using price action + news
context, and stores confirmed signals to SQLite + JSON.

## Scope for this iteration

- Markets: BTCUSDT and ETHUSDT only (crypto, via Binance public API — no key needed)
- Timeframe: 1-hour candles
- LLM: SEA-LION via api.sea-lion.ai (API key required)
- News: CryptoPanic API (API key required), filtered per symbol
- Run mode: on-demand script (`python run.py`), no scheduler/daemon
- Storage: SQLite (queryable) + append-only JSON file

Explicitly out of scope for this iteration: other asset classes (forex/gold/stocks/
indices/oil), scheduling/automation, Telegram delivery, a UI/dashboard, and any
production deployment concerns.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Binance Client  │     │ CryptoPanic Client│    │  SEA-LION Client│
│ (OHLCV candles)  │     │ (news headlines)  │    │ (LLM confirm)   │
└────────┬─────────┘     └────────┬──────────┘    └────────┬────────┘
         │                        │                         │
         ▼                        ▼                         │
┌──────────────────┐     ┌──────────────────┐               │
│ Indicator Engine  │     │  News Filter     │               │
│ (EMA/RSI/MACD →   │     │ (relevant to     │               │
│  candidate setup) │     │  BTC/ETH)        │               │
└────────┬──────────┘     └────────┬─────────┘               │
         │                         │                         │
         └───────────┬─────────────┘                         │
                      ▼                                      │
             ┌──────────────────┐                            │
             │ Signal Composer  │◄───────────────────────────┘
             │ (builds prompt,  │
             │  calls SEA-LION, │
             │  parses verdict) │
             └────────┬─────────┘
                      ▼
             ┌──────────────────┐
             │  Storage Layer   │
             │ (SQLite + JSON)  │
             └──────────────────┘
```

Five independently testable components:

- **Market data fetcher** — pulls the last ~200 1h candles for BTCUSDT/ETHUSDT from
  Binance's public REST API (no key required).
- **Indicator engine** — pure functions that turn candles into a candidate setup
  (direction, entry, stop-loss, take-profit) or "no setup found."
- **News fetcher** — pulls recent CryptoPanic headlines filtered to the relevant
  symbol.
- **Signal composer** — sends the candidate setup + headlines to SEA-LION, asks it
  to confirm/reject with a confidence score and rationale.
- **Storage layer** — writes confirmed signals to SQLite and appends to a JSON file.

## Data flow

1. **Fetch candles**: last ~200 1h candles for BTCUSDT and ETHUSDT.
2. **Compute indicators**: EMA(9)/EMA(21) crossover for trend direction, RSI(14) for
   overbought/oversold, MACD for momentum confirmation.
3. **Derive candidate setup**: if indicators align (e.g., EMA9 crosses above EMA21,
   RSI < 70, MACD histogram turning positive) → candidate long setup with
   entry = current price, stop-loss = recent swing low (ATR-based buffer),
   take-profit = risk-reward multiple (1:2 default). If indicators don't align →
   no setup, skip symbol for this run.
4. **Fetch news**: last 10 CryptoPanic headlines tagged for that symbol.
5. **LLM confirmation**: send SEA-LION a structured prompt containing the candidate
   setup (direction/entry/SL/TP + indicator values) and headlines. SEA-LION returns
   JSON: `{verdict: "confirm"|"reject", confidence: 0-100, rationale: string}`.
6. **Compose final signal**: if confirmed, merge into a final signal record. If
   rejected, discard — log the reason, do not store as a live signal.
7. **Store**: write confirmed signals to SQLite and append to `signals.json`.

The LLM's role in this iteration is **confirm/reject gate only** — it does not
originate setups from scratch; the indicator engine always proposes the candidate
first.

## Signal schema

```python
{
  "id": "uuid",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "direction": "long" | "short",
  "entry": float,
  "stop_loss": float,
  "take_profit": float,
  "confidence": int,        # 0-100, from SEA-LION
  "rationale": str,         # SEA-LION's explanation
  "indicators": {"ema9": float, "ema21": float, "rsi": float, "macd_hist": float},
  "news_headlines": [str],
  "created_at": "ISO timestamp"
}
```

SQLite table `signals` mirrors this schema (flattened columns). `signals.json` is an
append-only array of the same records, for easy inspection/export without a DB
client.

## Error handling

- **Binance/CryptoPanic API failures** → retry once with backoff, then skip that
  symbol for this run. Log the failure; do not crash the whole script.
- **SEA-LION call failures or malformed JSON response** → treat as "reject" (fail
  closed — never store an unconfirmed signal). Log the raw response for debugging.

## Testing

- Unit tests for the indicator engine: pure functions fed known candle sequences,
  asserting expected EMA/RSI/MACD crossover behavior.
- Mocked HTTP layer for Binance, CryptoPanic, and SEA-LION so the composer's
  confirm/reject/storage logic is testable without live network calls.
- One end-to-end smoke test using recorded fixture data (candles + headlines +
  a canned SEA-LION response) verifying a signal is correctly composed and stored.

## Configuration / secrets

Required environment variables (`.env`, not committed):
- `SEALION_API_KEY` — for api.sea-lion.ai
- `CRYPTOPANIC_API_KEY`

No Binance key required (public market data endpoints).

## Out of scope (future sub-projects)

- Marketing site (branded as ThinkTrade, modeled on zoqira.pro's structure)
- Auth & accounts
- Dashboard / trade journal UI
- Billing & subscriptions
- Telegram alert delivery
- Scheduling/automation (cron/daemon) for continuous signal generation
- Additional asset classes: forex, gold, stocks, indices, oil
