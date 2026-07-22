# 1-minute XAUUSD scalper

## Goal

A standalone feature that scans **XAUUSD only, on the 1m timeframe, every
minute**, confirms setups with SEA-LION using **only the 3 otherwise-idle keys
(`KEY5`/`KEY6`/`KEY7`)**, and pushes confirmed signals to the same Telegram
channel + `signals` table as the main engine. Separate from the 10-minute
multi-symbol engine.

## Decisions (approved)

- **Strategy:** `ict_fvg` (ICT FVG super-scalp, tight 0.5R/1R/1.5R targets).
- **Scheduling:** a self-looping GitHub Actions workflow (repo is public → CI
  minutes are free). No new infrastructure.
- **AI keys:** `KEY5`–`KEY7`, round-robined by minute, kept off the main
  engine's `KEY1`–`KEY4`.

## Honest caveats (documented, not hidden)

- 1m is the noisiest timeframe and no strategy is validated there; the LLM
  confirm gate is the main quality filter. Exploratory.
- Yahoo 1m gold data is thin (last few days), rate-limited if hammered, and
  **absent on weekends** (COMEX gold closed) — the scanner simply finds nothing
  then.

## Architecture

### Data — `market_client.py`
Add `"1m": ("1m", "1d")` to `YAHOO_INTERVAL` so XAUUSD 1m resolves to real 1m
gold bars instead of the 60m fallback.

### Scan — reuse `scan_symbol` with two new params
- `skip_recency=False` → when True, bypass `_recently_evaluated` (that throttle
  is what would block a 1-minute cadence). Scalper passes True.
- `log_no_setup=True` → when False, don't write a `no_setup` ai_event (avoids
  ~60 rows/hour of noise). Scalper passes False.

Open-signal dedup (`already_signaled`) and LLM confirm stay on, so we never emit
60 duplicate alerts for the same setup, and unconfirmed setups are never stored.

### Entrypoint — `signals/xau_scan.py`
`main()` does ONE scan per invocation (the per-minute loop lives in the
workflow):
1. `load_config()`, `fetch_bot_settings()` for the confidence bars.
2. Build `SeaLionClient` with a scalper key: `keys[4:] or keys`, rotated by
   `datetime.utcnow().minute % n`.
3. `scan_symbol("XAUUSD", cfg, llm, strategy="ict_fvg", timeframe="1m",
   confluence_timeframe=None, skip_recency=True, log_no_setup=False,
   min_store_confidence=settings.min_store_confidence)` — stores on confirm.
4. On `result.signal`, `maybe_send_alert(result.signal, settings, cfg)`.

No engine lock (single symbol, own workflow concurrency group); `already_signaled`
prevents duplicate stores if two invocations overlap.

### Scheduling — `.github/workflows/xau-scalper.yml`
- `workflow_dispatch` + `repository_dispatch: [run-xau-scalper]`.
- One job: checkout, setup-python, `pip install`, then a bash loop
  `for i in $(seq 1 50); do python -m signals.xau_scan || true; sleep 60; done`,
  then re-dispatch itself (via the existing dispatch PAT) for continuous cover.
- `env`: `SEALION_API_KEY5/6/7`, `SUPABASE_*`, `TELEGRAM_*`. Own concurrency
  group `xau-scalper`.

### Exits
Tracked by the main engine's `outcome_tracker` (it back-fills from 1m candles,
so TP/SL **status is accurate**; the alert may lag up to ~10 min). A per-minute
XAU outcome poll is a possible v2.

## Testing
- `market_client`: 1m gold maps to Yahoo `("1m","1d")`, not the 60m fallback.
- `scan_symbol`: `skip_recency=True` bypasses the recency guard; `log_no_setup=
  False` writes no ai_event on a no-setup scan.
- `xau_scan`: builds the LLM from KEY5–7, calls scan for XAUUSD/1m/ict_fvg, and
  alerts on a stored signal (fakes for network/DB).

## Out of scope (v1)
Per-minute outcome tracking; a dedicated always-on worker; multi-symbol scalping.
