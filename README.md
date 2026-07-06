# FinhubKH Signals Engine

AI-confirmed crypto trading signals. Scans BTCUSDT/ETHUSDT 1h candles from
Binance, derives technical setups (EMA 9/21 crossover, RSI 14, MACD, ATR),
confirms each candidate with SEA-LION using recent CryptoPanic headlines,
and stores confirmed signals in SQLite + JSON.

Part of the FinhubKH platform rebuild (formerly ThinkTrade). Spec:
`docs/superpowers/specs/2026-07-05-signals-engine-design.md`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in your API keys
```

Keys required:
- `SEALION_API_KEY` — https://playground.sea-lion.ai (free, Google sign-in)
- `CRYPTOPANIC_API_KEY` — https://cryptopanic.com/developers/api/keys

No Binance key needed (public market data).

**Gotchas:**
- Replace the placeholder values from `.env.example` with real keys — a
  placeholder like `your-sealion-key-here` passes startup validation but
  fails later with a 401 from the API.
- If your shell already exports `SEALION_API_KEY`/`CRYPTOPANIC_API_KEY`,
  those win over `.env` (python-dotenv does not override existing env vars).

## Run

```bash
.venv/bin/python -m signals.run
```

Confirmed signals are appended to `signals.json` and inserted into
`signals.db` (table `signals`). A run with no qualifying technical setup
stores nothing — that is normal; crossovers are infrequent by design.

## Tests

```bash
.venv/bin/pytest
```

## Web app

A Next.js front end lives in `web/`: a marketing landing page (`/`) and a
signals dashboard (`/dashboard`) that read `signals.db` directly (read-only).

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm test           # vitest
```

Pages render per-request, so refresh after an engine run to see new
signals. If `signals.db` doesn't exist yet, both pages show friendly empty
states. To point at a different database, set `SIGNALS_DB_PATH`.

## Disclaimer

Signals are for educational and analysis purposes only. Not financial
advice. Trading involves risk.
