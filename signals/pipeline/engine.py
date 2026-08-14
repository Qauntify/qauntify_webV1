"""Engine orchestration: run every due session's scans and settle outcomes."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from signals.clients.llm import SeaLionClient
from signals.config import load_config
from signals.models import TRADING_SESSIONS, session_scans
from signals.outcomes.tracker import backfill_missing_outcome_charts, track_open_signals
from signals.persistence.events import save_engine_run
from signals.persistence.locks import release_engine_lock, try_acquire_engine_lock
from signals.persistence.mt5 import expire_drifted_open_gold_signals
from signals.persistence.settings import fetch_bot_settings
from signals.pipeline.dedup import (
    _prefetch_open_symbols,
    _prefetch_recent_events,
    _prefetch_recent_signals,
    with_retry,
)
from signals.pipeline.confluence import detect_confluence
from signals.pipeline.deliver import maybe_send_alert
from signals.pipeline.market_data import resolve_gold_live_price
from signals.pipeline.scan import effective_min_store_confidence, scan_symbol
from signals.retention import run_retention_cleanup

# Scans are I/O-bound (Binance, SEA-LION, Supabase), so symbols run in
# parallel. Each worker gets its own requests.Session and LLM client —
# neither is thread-safe to share.
MAX_SCAN_WORKERS = 4

OUTCOME_LABELS = {
    "tp_hit": "TP HIT",
    "tp1_hit": "TP1 HIT",
    "tp2_hit": "TP2 HIT",
    "tp3_hit": "TP3 HIT",
    "sl_hit": "SL HIT",
    "expired": "EXPIRED",
}


def main(sessions=None):
    """Run the signal engine once.

    `sessions` defaults to every TRADING_SESSION. The live bar-close scanner
    passes only the sessions whose candle just closed.
    """
    cfg = load_config()
    # Main-thread session for Supabase reads/writes outside the scan workers.
    db_session = requests.Session()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not try_acquire_engine_lock(
        run_id, cfg.supabase_url, cfg.supabase_service_key, session=db_session,
    ):
        print(f"Another engine run holds the lock; skipping this trigger ({run_id}).")
        return

    trading_sessions = tuple(sessions) if sessions is not None else TRADING_SESSIONS
    if not trading_sessions:
        print(f"No sessions due; skipping ({run_id}).")
        release_engine_lock(
            run_id, cfg.supabase_url, cfg.supabase_service_key, session=db_session,
        )
        return

    stored = 0
    outcomes: list[dict] = []
    candles_by_symbol: dict = {}
    newly_confirmed_signals: list = []
    session_label = "+".join(s.timeframe for s in trading_sessions)
    try:
        # Housekeeping before scans so drifted gold opens free the unique slot.
        try:
            live, source = resolve_gold_live_price(
                cfg, session=db_session, require_mt5=False,
            )
            n = expire_drifted_open_gold_signals(
                live, cfg.supabase_url, cfg.supabase_service_key,
                session=db_session,
            )
            if n:
                print(f"[XAUUSD] expired {n} drifted open signal(s) "
                      f"vs {source} {live:.2f}")
        except Exception as exc:
            print(f"[XAUUSD] drift expire skipped ({type(exc).__name__})")

        settings = fetch_bot_settings(cfg.supabase_url, cfg.supabase_service_key,
                                      session=db_session)
        keys = cfg.sealion_api_keys or (cfg.sealion_api_key,)
        print(f"Using {len(keys)} SEA-LION API key(s) across "
              f"{len(settings.symbols)} symbol(s) in {len(trading_sessions)} "
              f"session(s) ({session_label}), "
              f"swing=msnr, "
              f"scalp=cloud_mss, super_scalp=ict_fvg.")

        def scan_one(item):
            """(index, symbol, TradingSession, recent_events, recent_signals, open_symbols)
            -> (ScanResult | None, error | None)."""
            (index, symbol, trading_session, recent_events, recent_signals,
             open_symbols) = item
            # Symbols round-robin across keys so a full scan never concentrates
            # its LLM calls on a single key's rate limit.
            llm = SeaLionClient(
                api_key=keys[index % len(keys)],
                model=cfg.sealion_model,
                base_url=cfg.sealion_base_url,
            )
            session_strategy = (
                trading_session.strategy or settings.signal_strategy
            )
            try:
                return scan_symbol(
                    symbol, cfg, llm, strategy=session_strategy,
                    timeframe=trading_session.timeframe,
                    session=requests.Session(),
                    recent_events=recent_events, recent_signals=recent_signals,
                    open_symbols=open_symbols,
                    confluence_timeframe=trading_session.confluence_timeframe,
                    min_store_confidence=effective_min_store_confidence(
                        session_strategy, settings.min_store_confidence,
                    ),
                ), None
            except Exception as exc:
                return None, exc
        workers = max(1, min(len(settings.symbols), MAX_SCAN_WORKERS))

        # Each session (scalp, swing) scans all symbols in parallel, one session
        # at a time — so a run's outcomes group by session for a clear summary.
        for trading_session in trading_sessions:
            # Not every symbol belongs on every session — see SESSION_SYMBOLS.
            # Filtered once here so the prefetches, the scan tasks and the
            # result pairing below all agree on the same list; querying for a
            # symbol this session will not scan would also waste a round trip.
            session_symbols = [
                symbol for symbol in settings.symbols
                if session_scans(trading_session.name, symbol)
            ]
            if not session_symbols:
                continue
            # One query each for the whole session's symbol list, instead of
            # every symbol hitting Supabase individually before its scan even
            # starts — collapses up to 3*len(symbols) round trips into 3.
            recent_events = _prefetch_recent_events(
                session_symbols, trading_session.timeframe, cfg, session=db_session)
            recent_signals = _prefetch_recent_signals(
                session_symbols, trading_session.timeframe, cfg, session=db_session)
            open_symbols = _prefetch_open_symbols(
                session_symbols, trading_session.timeframe, cfg, session=db_session)
            tasks = [
                (i, symbol, trading_session, recent_events, recent_signals, open_symbols)
                for i, symbol in enumerate(session_symbols)
            ]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(scan_one, tasks))

            # Alerts go out from the main thread, in symbol order, after the
            # session's scans finish.
            for symbol, (result, error) in zip(session_symbols, results):
                if error is not None:
                    print(f"[{symbol}] unexpected error, skipping: "
                          f"{type(error).__name__}: {error}")
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "ERROR",
                        "extra": f"{type(error).__name__}",
                    })
                    continue
                if result.candles:
                    candles_by_symbol[(symbol, trading_session.timeframe)] = result.candles
                if result.signal is not None:
                    stored += 1
                    newly_confirmed_signals.append(result.signal)
                    maybe_send_alert(result.signal, settings, cfg)
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "CONFIRMED",
                        "extra": f"{result.signal.direction.upper()} {result.signal.confidence}%",
                    })
                elif result.no_signal is not None:
                    # No Telegram for no-setup / rejected — only confirmed
                    # signals and SL/TP hits get pushed.
                    if result.no_signal.kind == "rejected":
                        outcomes.append({
                            "symbol": symbol,
                            "timeframe": trading_session.timeframe,
                            "status": "REJECTED",
                            "extra": (result.no_signal.rationale or "")[:140],
                        })
                    else:
                        outcomes.append({
                            "symbol": symbol,
                            "timeframe": trading_session.timeframe,
                            "status": "NO SIGNAL",
                            "extra": (result.no_signal.rationale or "")[:140],
                        })
                else:
                    outcomes.append({
                        "symbol": symbol,
                        "timeframe": trading_session.timeframe,
                        "status": "SKIPPED",
                        "extra": "No change (dedup) or missing indicators/data",
                    })

        # Cross-strategy confirmation: runs once, after every session has
        # scanned, so it sees the full picture of what just got confirmed.
        # Never allowed to block the three real sessions' delivery, which
        # has already completed by this point.
        try:
            for confluence_signal in detect_confluence(
                newly_confirmed_signals, candles_by_symbol, settings, cfg,
                session=db_session,
            ):
                stored += 1
                outcomes.append({
                    "symbol": confluence_signal.symbol,
                    "timeframe": "confluence",
                    "status": "CONFIRMED",
                    "extra": f"{confluence_signal.direction.upper()} "
                             f"{confluence_signal.confidence}% (confluence)",
                })
        except Exception as exc:
            print(f"confluence detection failed ({type(exc).__name__}), continuing")

        # After scanning both sessions, settle open signals whose TP or SL has
        # been hit and expire stale ones (per-session window), reusing this
        # run's candles where they already cover a signal's life.
        for row, outcome in track_open_signals(cfg, prefetched=candles_by_symbol,
                                               session=db_session):
            entry = {
                "symbol": row["symbol"],
                "status": OUTCOME_LABELS.get(outcome, outcome.upper()),
                "extra": f"{row['direction'].upper()} closed",
            }
            if row.get("timeframe"):
                entry["timeframe"] = row["timeframe"]
            outcomes.append(entry)

        # Backfills outcome charts for rows closed without one -- notably
        # every realtime MT5/Vercel close, which never renders a chart.
        try:
            backfill_missing_outcome_charts(cfg, session=db_session)
        except Exception as exc:
            print(f"chart backfill failed ({type(exc).__name__}), continuing")

        # Prunes unbounded log tables (ai_events/engine_runs/xau_scan_runs).
        # Cheap even as a no-op: each table's date column is indexed, so a
        # DELETE that matches nothing after the first cleanup is a fast
        # index range scan, not a full scan -- fine to run every cycle.
        run_retention_cleanup(cfg, session=db_session)
        try:
            with_retry(lambda: save_engine_run(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "timeframe": session_label,
                    "stored_count": stored,
                    "outcomes": outcomes,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
                cfg.supabase_url,
                cfg.supabase_service_key,
                session=db_session,
            ))
        except Exception as exc:
            print(f"Failed to store engine run heartbeat ({type(exc).__name__}), continuing")
        # Run summary stays in Supabase / logs only — not pushed to Telegram.
        print(f"Done. {stored} signal(s) stored in Supabase.")
    finally:
        release_engine_lock(
            run_id, cfg.supabase_url, cfg.supabase_service_key, session=db_session,
        )
