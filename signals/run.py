"""On-demand pipeline: scan symbols, confirm setups via LLM, store signals.

Usage: python -m signals.run
"""
import time

from signals.binance_client import fetch_candles
from signals.composer import confirm_setup
from signals.config import load_config
from signals.indicators import atr, ema, macd_histogram, rsi
from signals.llm_client import SeaLionClient
from signals.models import make_signal
from signals.news_client import fetch_headlines
from signals.setup_detector import detect_setup
from signals.storage import save_signal

RETRY_DELAY = 2.0


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


def scan_symbol(symbol, cfg, llm):
    """Scan one symbol; return the stored Signal or None."""
    try:
        candles = with_retry(
            lambda: fetch_candles(symbol, cfg.timeframe, cfg.candle_limit)
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return None

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

    try:
        headlines = with_retry(
            lambda: fetch_headlines(symbol, cfg.cryptopanic_api_key)
        )
    except Exception as exc:
        # Log only the exception type: HTTPError strings embed the request URL,
        # which contains the CryptoPanic auth_token.
        print(f"[{symbol}] news unavailable ({type(exc).__name__}), proceeding without")
        headlines = []

    confirmation = confirm_setup(setup, headlines, llm)
    if confirmation.verdict != "confirm":
        print(f"[{symbol}] rejected by LLM: {confirmation.rationale}")
        return None

    signal = make_signal(setup, confirmation, headlines, timeframe=cfg.timeframe)
    save_signal(signal, db_path=cfg.db_path, json_path=cfg.json_path)
    print(f"[{symbol}] CONFIRMED {signal.direction.upper()} "
          f"(confidence {signal.confidence}): {signal.rationale}")
    return signal


def main():
    cfg = load_config()
    llm = SeaLionClient(
        api_key=cfg.sealion_api_key,
        model=cfg.sealion_model,
        base_url=cfg.sealion_base_url,
    )
    stored = 0
    for symbol in cfg.symbols:
        try:
            if scan_symbol(symbol, cfg, llm) is not None:
                stored += 1
        except Exception as exc:
            print(f"[{symbol}] unexpected error, skipping: {type(exc).__name__}: {exc}")
    print(f"Done. {stored} signal(s) stored in {cfg.db_path} / {cfg.json_path}")


if __name__ == "__main__":
    main()
