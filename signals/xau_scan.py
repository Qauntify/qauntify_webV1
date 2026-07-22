"""1-minute XAUUSD scalper.

Scans XAUUSD on the 1m timeframe with the ict_fvg super-scalp, confirms with
the spare SEA-LION keys (KEY5-7) so it never competes with the main engine's
KEY1-4, and pushes confirmed signals to the same Telegram channel + signals
table. One invocation = one scan; the per-minute loop lives in
`.github/workflows/xau-scalper.yml`.

Usage: python -m signals.xau_scan
"""
from datetime import datetime, timezone

import requests

from signals.config import load_config
from signals.llm_client import SeaLionClient
from signals.run import maybe_send_alert, scan_symbol
from signals.storage import fetch_bot_settings

XAU_SYMBOL = "XAUUSD"
XAU_TIMEFRAME = "1m"
XAU_STRATEGY = "ict_fvg"
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
    keys = scalper_keys(cfg.sealion_api_keys or (cfg.sealion_api_key,))
    llm = SeaLionClient(
        api_key=_pick_key(keys),
        model=cfg.sealion_model,
        base_url=cfg.sealion_base_url,
        session=session,
    )
    result = scan_symbol(
        XAU_SYMBOL, cfg, llm,
        strategy=XAU_STRATEGY, timeframe=XAU_TIMEFRAME,
        confluence_timeframe=None,
        skip_recency=True, log_no_setup=False,
        min_store_confidence=settings.min_store_confidence,
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


if __name__ == "__main__":
    main()
