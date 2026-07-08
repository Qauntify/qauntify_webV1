# Qauntify Signals Engine

AI-confirmed crypto trading signals. Scans BTCUSDT/ETHUSDT 1h candles from
Binance, derives technical setups (EMA 9/21 crossover, RSI 14, MACD, ATR),
confirms each candidate with SEA-LION using recent news headlines from
public RSS feeds (CoinDesk, Decrypt, The Block), and stores confirmed
signals in Supabase (Postgres).

Part of the Qauntify platform rebuild (formerly FinhubKH, ThinkTrade). Spec:
`docs/superpowers/specs/2026-07-05-signals-engine-design.md`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in your API keys
```

Keys required:
- `SEALION_API_KEY` — https://playground.sea-lion.ai (free, Google sign-in)
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` — Supabase Dashboard →
  Project Settings → API

No Binance key needed (public market data), and news comes from public RSS
feeds — no news API key either.

**One-time Supabase setup:** create a free project at https://supabase.com,
then run `supabase/schema.sql` in the SQL Editor (Dashboard → SQL Editor)
to create the `signals` table with its read-only public policy.

**Gotchas:**
- Replace the placeholder value from `.env.example` with a real key — a
  placeholder like `your-sealion-key-here` passes startup validation but
  fails later with a 401 from the API.
- If your shell already exports `SEALION_API_KEY`, it wins over `.env`
  (python-dotenv does not override existing env vars).

## Run

```bash
.venv/bin/python -m signals.run
```

Confirmed signals are inserted into the Supabase `signals` table. A run
with no qualifying technical setup stores nothing — that is normal;
crossovers are infrequent by design.

## Tests

```bash
.venv/bin/pytest
```

## Web app

A Next.js front end lives in `web/`: a marketing landing page (`/`) and a
signals dashboard (`/dashboard`) that read the Supabase `signals` table
with the public anon key (row-level security allows reads only).

```bash
cd web
cp .env.local.example .env.local   # fill in your Supabase URL + anon key
npm install
npm run dev        # http://localhost:3000
npm test           # vitest
```

Pages render per-request, so refresh after an engine run to see new
signals. If the Supabase env vars are missing or the table is empty, both
pages show friendly empty states.

## Disclaimer

Signals are for educational and analysis purposes only. Not financial
advice. Trading involves risk.
