"""Post-store delivery: the ad-hoc showcase debate and the Telegram alert."""
from datetime import datetime, timezone

from signals.clients.llm import SeaLionClient
from signals.clients.telegram import send_alert
from signals.models import CandidateSetup
from signals.persistence.events import save_debate
from signals.pipeline.debate import run_debate
from signals.pipeline.dedup import with_retry


def maybe_run_debate(signal, cfg, session=None):
    """Optional showcase debate about an already-stored signal.

    Not called from `main()` — the live War Room Floor is `war_room_scan`
    (separate workflow). Kept for tests / ad-hoc ops; never gates delivery.
    """
    if not cfg.supabase_url or not cfg.supabase_service_key:
        return
    try:
        keys = cfg.sealion_api_keys or (cfg.sealion_api_key,)
        llm = SeaLionClient(
            api_key=keys[datetime.now(timezone.utc).minute % len(keys)],
            model=cfg.sealion_model, base_url=cfg.sealion_base_url,
            session=session,
        )
        setup = CandidateSetup(
            signal.symbol, signal.direction, signal.entry, signal.stop_loss,
            signal.take_profit, signal.indicators,
            take_profit_2=signal.take_profit_2, take_profit_3=signal.take_profit_3,
        )
        debate = run_debate(setup, llm, timeframe=signal.timeframe)
        debate["signal_id"] = signal.id
        save_debate(debate, cfg.supabase_url, cfg.supabase_service_key,
                    session=session)
        print(f"[{signal.symbol}] war-room: {debate['manager_verdict']} "
              f"{debate['manager_confidence']}%")
    except Exception as exc:
        print(f"[{signal.symbol}] war-room debate skipped ({type(exc).__name__})")


def maybe_send_alert(signal, settings, cfg):
    """Telegram alert for a stored signal; never raises — a failed or
    skipped alert must not affect the rest of the run.
    """
    if not cfg.telegram_bot_token or not cfg.telegram_channel_id:
        return
    if signal.confidence < settings.min_alert_confidence:
        print(f"[{signal.symbol}] confidence {signal.confidence} below alert "
              f"threshold {settings.min_alert_confidence}, no alert")
        return
    try:
        with_retry(lambda: send_alert(
            signal, cfg.telegram_bot_token, cfg.telegram_channel_id,
        ))
        print(f"[{signal.symbol}] Telegram alert sent")
    except Exception as exc:
        print(f"[{signal.symbol}] Telegram alert failed "
              f"({type(exc).__name__}), continuing")


# Telegram carries confirmed signals and TP/SL outcomes only. No-signal and
# rejected scans, and per-run summaries, stay in Supabase and the logs — they
# are noise in a channel people act on. The formatters for both still exist in
# signals.clients.telegram for ad-hoc use; this module deliberately never calls
# them, and tests/core/test_telegram.py asserts that.
