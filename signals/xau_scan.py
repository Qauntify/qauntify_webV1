"""1-minute XAUUSD scalper.

Scans XAUUSD on the 1m timeframe with the ict_fvg super-scalp, confirms with
the spare SEA-LION keys (KEY5-7) so it never competes with the main engine's
KEY1-4, and pushes confirmed signals to the same Telegram channel + signals
table. One invocation = one scan; the per-minute loop lives in
`.github/workflows/xau-scalper.yml`.

Usage: python -m signals.xau_scan
"""
import uuid
from datetime import datetime, timezone

import requests

from signals.config import load_config
from signals.clients.llm import SeaLionClient
from signals.models import ScanResult
from signals.run import (
    maybe_send_alert,
    resolve_gold_live_price,
    scan_symbol,
)
from signals.session_clock import scalp_session_active, sessions_at
from signals.storage import (
    expire_drifted_open_gold_signals,
    fetch_bot_settings,
    save_xau_scan_run,
)

XAU_SYMBOL = "XAUUSD"
XAU_TIMEFRAME = "1m"
XAU_STRATEGY = "ict_fvg"
# Floor on top of admin min_store_confidence — 1m needs a higher bar.
XAU_MIN_STORE_CONFIDENCE = 65
# Reserve keys from this index on (KEY5, KEY6, KEY7) for the scalper.
SCALPER_KEY_START = 4


def scalper_keys(all_keys) -> tuple:
    """The keys reserved for the scalper (KEY5+); all keys if fewer than 5 set."""
    keys = tuple(all_keys)
    return keys[SCALPER_KEY_START:] or keys


def _pick_key(keys, minute=None):
    """Round-robin across the scalper keys by the wall-clock minute."""
    if minute is None:
        minute = datetime.now(timezone.utc).minute
    return keys[minute % len(keys)]


def scan_once(cfg, settings, session=None) -> "object":
    """Run one XAUUSD 1m scan; store + alert on a confirmed signal."""
    session = session or requests.Session()

    if not scalp_session_active():
        active = sessions_at() or ("off-hours",)
        print(f"[XAUUSD] skip 1m scalp outside London/NY (now: {', '.join(active)})")
        return ScanResult()

    try:
        live, source = resolve_gold_live_price(
            cfg, session=session, require_mt5=False,
        )
        n = expire_drifted_open_gold_signals(
            live, cfg.supabase_url, cfg.supabase_service_key, session=session,
        )
        if n:
            print(f"[XAUUSD] expired {n} drifted open signal(s) vs {source} {live:.2f}")
    except Exception as exc:
        print(f"[XAUUSD] drift expire skipped ({type(exc).__name__})")

    keys = scalper_keys(cfg.sealion_api_keys or (cfg.sealion_api_key,))
    llm = SeaLionClient(
        api_key=_pick_key(keys),
        model=cfg.sealion_model,
        base_url=cfg.sealion_base_url,
        session=session,
    )
    min_conf = max(settings.min_store_confidence, XAU_MIN_STORE_CONFIDENCE)
    result = scan_symbol(
        XAU_SYMBOL, cfg, llm,
        strategy=XAU_STRATEGY, timeframe=XAU_TIMEFRAME,
        confluence_timeframe=None,
        skip_recency=True, log_no_setup=False,
        min_store_confidence=min_conf,
        session=session,
    )
    if result.signal is not None:
        maybe_send_alert(result.signal, settings, cfg)
    return result


def main() -> None:
    cfg = load_config()
    settings = fetch_bot_settings(cfg.supabase_url, cfg.supabase_service_key)
    result = scan_once(cfg, settings, session=requests.Session())
    if result.signal is not None:
        sig = result.signal
        print(f"[XAUUSD] 1m signal stored + alerted: {sig.direction} "
              f"@ {sig.entry} (confidence {sig.confidence}%)")
    else:
        print("[XAUUSD] 1m scan: no confirmed signal this minute.")

    try:
        save_xau_scan_run(
            {
                "id": str(uuid.uuid4()),
                "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "signal_found": result.signal is not None,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
            cfg.supabase_url,
            cfg.supabase_service_key,
        )
    except Exception as exc:
        print(f"Failed to store xau_scan heartbeat ({type(exc).__name__}), continuing")


if __name__ == "__main__":
    main()
