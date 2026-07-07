"""On-demand pipeline: scan symbols, confirm setups via LLM, store signals.

Usage: python -m signals.run
"""
import time
from datetime import datetime, timedelta, timezone

from signals.binance_client import fetch_candles
from signals.composer import confirm_setup
from signals.config import load_config
from signals.indicators import atr, ema, macd_histogram, rsi
from signals.llm_client import SeaLionClient
from signals.models import make_signal
from signals.news_client import fetch_headlines
from signals.setup_detector import detect_setup
from signals.storage import fetch_bot_settings, latest_signal, save_signal
from signals.telegram_client import send_alert

RETRY_DELAY = 2.0

# The detector flags a crossover on any of the last CROSS_LOOKBACK (3) hourly
# bars, so runs closer together than that would re-store the same setup.
# Skip a candidate when the same symbol+direction was stored this recently.
DEDUP_WINDOW = timedelta(hours=3)


def with_retry(fn, attempts=2, delay=None):
    """Call fn; on failure wait `delay` seconds and try once more per extra attempt.

    delay=None resolves to the module-level RETRY_DELAY at call time.
    """
    if delay is None:
        delay = RETRY_DELAY
    last_error = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay)
    raise last_error


def already_signaled(setup, cfg):
    """True when the newest stored signal for this symbol duplicates the
    candidate (same direction, within DEDUP_WINDOW). On any lookup failure
    return False — better a duplicate than a missed signal."""
    try:
        row = latest_signal(setup.symbol, cfg.supabase_url,
                            cfg.supabase_service_key)
    except Exception as exc:
        print(f"[{setup.symbol}] dedup check failed "
              f"({type(exc).__name__}), proceeding")
        return False
    if row is None or row["direction"] != setup.direction:
        return False
    stored_at = datetime.fromisoformat(row["created_at"])
    return datetime.now(timezone.utc) - stored_at < DEDUP_WINDOW


def scan_symbol(symbol, cfg, llm):
    """Scan one symbol; return the stored Signal or None."""
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, cfg.timeframe, cfg.candle_limit)
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return None

    # Binance returns the current, still-forming candle last — drop it so
    # indicators and entry price are computed on closed bars only.
    candles = candles[:-1]

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    setup = detect_setup(
        symbol,
        candles,
        ema(closes, 9),
        ema(closes, 21),
        rsi(closes, 14),
        macd_histogram(closes),
        atr(highs, lows, closes, 14),
    )
    if setup is None:
        print(f"[{symbol}] no setup found")
        return None
    print(f"[{symbol}] candidate {setup.direction}: entry={setup.entry} "
          f"SL={setup.stop_loss} TP={setup.take_profit}")

    if already_signaled(setup, cfg):
        print(f"[{symbol}] same setup already stored recently, skipping")
        return None

    try:
        headlines = with_retry(lambda: fetch_headlines(symbol))
    except Exception as exc:
        # Log only the exception type, not the message — keeps log lines short
        # and guards against any future news source embedding secrets in URLs.
        print(f"[{symbol}] news unavailable ({type(exc).__name__}), proceeding without")
        headlines = []

    confirmation = confirm_setup(setup, headlines, llm)
    if confirmation.verdict != "confirm":
        print(f"[{symbol}] rejected by LLM: {confirmation.rationale}")
        return None

    signal = make_signal(setup, confirmation, headlines, timeframe=cfg.timeframe)
    try:
        with_retry(lambda: save_signal(
            signal, cfg.supabase_url, cfg.supabase_service_key,
        ))
    except Exception as exc:
        print(f"[{symbol}] failed to store signal ({type(exc).__name__}), discarding")
        return None
    print(f"[{symbol}] CONFIRMED {signal.direction.upper()} "
          f"(confidence {signal.confidence}): {signal.rationale}")
    return signal


def maybe_send_alert(signal, settings, cfg):
    """Telegram alert for a stored signal; never raises — a failed or
    skipped alert must not affect the rest of the run."""
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return
    if signal.confidence < settings.min_alert_confidence:
        print(f"[{signal.symbol}] confidence {signal.confidence} below alert "
              f"threshold {settings.min_alert_confidence}, no alert")
        return
    try:
        with_retry(lambda: send_alert(
            signal, cfg.telegram_bot_token, cfg.telegram_chat_id,
        ))
        print(f"[{signal.symbol}] Telegram alert sent")
    except Exception as exc:
        print(f"[{signal.symbol}] Telegram alert failed "
              f"({type(exc).__name__}), continuing")


def main():
    cfg = load_config()
    settings = fetch_bot_settings(cfg.supabase_url, cfg.supabase_service_key)
    llm = SeaLionClient(
        api_key=cfg.sealion_api_key,
        model=cfg.sealion_model,
        base_url=cfg.sealion_base_url,
    )
    stored = 0
    for symbol in settings.symbols:
        try:
            signal = scan_symbol(symbol, cfg, llm)
            if signal is not None:
                stored += 1
                maybe_send_alert(signal, settings, cfg)
        except Exception as exc:
            print(f"[{symbol}] unexpected error, skipping: {type(exc).__name__}: {exc}")
    print(f"Done. {stored} signal(s) stored in Supabase.")


if __name__ == "__main__":
    main()
