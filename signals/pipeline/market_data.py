"""Candle/indicator fetching, higher-timeframe trend, and gold live-price snap."""
from dataclasses import replace
from typing import NamedTuple

from signals.analysis.indicators import adx, atr, ema, macd_histogram, rsi
from signals.clients.market import fetch_candles, fetch_gold_last_price, gold_entry_live_ok
from signals.models import CandidateSetup, take_profits_from_risk
from signals.persistence.mt5 import fetch_mt5_last_tick, mt5_tick_is_fresh
from signals.pipeline.dedup import with_retry


def _latest_indicators(ema9, ema21, rsi14, macd_hist):
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1]):
        return None
    return {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }


# Just enough candles for EMA21 to warm up plus a little history — this is
# only a trend-direction read, not a full setup scan.
HTF_TREND_CANDLE_LIMIT = 30


def _fetch_htf_trend(symbol, timeframe, cfg, session=None):
    """"up"/"down" trend on a higher timeframe, from EMA9 vs EMA21.
    Returns None when EMAs are equal / still warming up.
    Raises RuntimeError when market data cannot be fetched so callers that
    require confluence can fail closed."""
    candles = with_retry(lambda: fetch_candles(
        symbol, timeframe, HTF_TREND_CANDLE_LIMIT, session=session,
        supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
    ))
    candles = candles[:-1]  # drop the still-forming candle, same as the main fetch
    closes = [c.close for c in candles]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    if fast[-1] is None or slow[-1] is None:
        return None
    if fast[-1] > slow[-1]:
        return "up"
    if fast[-1] < slow[-1]:
        return "down"
    return None


class MarketData(NamedTuple):
    candles: list
    ema9: list
    ema21: list
    rsi14: list
    macd_hist: list
    atr14: list
    adx14: list
    htf_trend: object
    h1_candles: object


# Strategies needing more history than the default scan window, and why.
#   ce_lwma   — LWMA200 on the 15m series
#   cloud_mss — LWMA200 plus the structure window. 260 fetched leaves 259
#               closed bars against a MIN_CANDLES of 230; at ce_lwma's 220 the
#               detector would be starved by its own limit and never fire.
EXTRA_HISTORY = {"ce_lwma": 220, "cloud_mss": 260}
# Strategies whose detector reads 1h candles directly, rather than only taking
# a higher-timeframe trend string.
NEEDS_H1 = ("ce_lwma", "cloud_mss")


def _candle_limit_for(strategy, cfg):
    """Bars to fetch for `strategy` on its primary timeframe."""
    return max(cfg.candle_limit, EXTRA_HISTORY.get(strategy, 0))


def _load_market_data(symbol, timeframe, strategy, cfg, *,
                      confluence_timeframe=None, session=None):
    """Fetch closed candles + indicators (+ H1 for ce_lwma / HTF trend for
    confluence). Returns (MarketData, candles) on success, (None, None) when the
    initial candle fetch fails, or (None, candles) when a required H1/HTF fetch
    fails after candles were already fetched."""
    candle_limit = _candle_limit_for(strategy, cfg)
    try:
        candles = with_retry(
            lambda: fetch_candles(
                symbol, timeframe, candle_limit, session=session,
                supabase_url=cfg.supabase_url,
                service_key=cfg.supabase_service_key,
            )
        )
    except Exception as exc:
        print(f"[{symbol}] market data unavailable, skipping: {exc}")
        return None, None

    candles = candles[:-1]
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_hist = macd_histogram(closes)
    atr14 = atr(highs, lows, closes, 14)
    adx14 = adx(highs, lows, closes, 14)
    htf_trend = None
    h1_candles = None
    if strategy in NEEDS_H1:
        try:
            h1_raw = with_retry(
                lambda: fetch_candles(
                    symbol, "1h", max(cfg.candle_limit, 80),
                    session=session,
                    supabase_url=cfg.supabase_url,
                    service_key=cfg.supabase_service_key,
                )
            )
            h1_candles = h1_raw[:-1]
        except Exception as exc:
            print(f"[{symbol}] H1 CE data unavailable ({type(exc).__name__}), "
                  "skipping")
            return None, candles
    elif confluence_timeframe:
        try:
            htf_trend = _fetch_htf_trend(symbol, confluence_timeframe, cfg,
                                         session=session)
        except Exception as exc:
            print(f"[{symbol}] HTF confluence required but unavailable "
                  f"({type(exc).__name__}), skipping")
            return None, candles

    return MarketData(candles=candles, ema9=ema9, ema21=ema21, rsi14=rsi14,
                      macd_hist=macd_hist, atr14=atr14, adx14=adx14,
                      htf_trend=htf_trend, h1_candles=h1_candles), candles


def _snap_gold_setup_to_live(setup: CandidateSetup, live: float,
                             timeframe: str, *,
                             source: str = "paxg") -> tuple[CandidateSetup | None, str]:
    """Align published gold levels to a live bid when drift is small.

    Shifts stop by the same delta as entry so R geometry stays intact when
    candle structure (PAXG) and broker mid (MT5) disagree.
    """
    atr = setup.indicators.get("atr")
    if isinstance(atr, (int, float)):
        atr_val: float | None = float(atr)
    else:
        atr_val = None
    ok, msg = gold_entry_live_ok(setup.entry, live, timeframe, atr_val)
    if not ok:
        return None, msg
    if abs(setup.entry - live) < 0.05:
        ind = dict(setup.indicators)
        ind["live_snap_source"] = source
        ind["live_snap_to"] = live
        return replace(setup, indicators=ind), ""
    delta = live - setup.entry
    new_stop = setup.stop_loss + delta
    tp_r = setup.indicators.get("tp_r")
    if isinstance(tp_r, (list, tuple)) and len(tp_r) == 3:
        tp1, tp2, tp3 = take_profits_from_risk(
            live, new_stop, setup.direction,
            r1=float(tp_r[0]), r2=float(tp_r[1]), r3=float(tp_r[2]),
        )
    else:
        tp1, tp2, tp3 = take_profits_from_risk(
            live, new_stop, setup.direction,
        )
    if setup.direction == "long" and live <= new_stop:
        return None, "Live price at or below stop — not publishing"
    if setup.direction == "short" and live >= new_stop:
        return None, "Live price at or above stop — not publishing"
    ind = dict(setup.indicators)
    ind["live_snap_from"] = setup.entry
    ind["live_snap_to"] = live
    ind["live_snap_source"] = source
    return replace(
        setup,
        entry=live,
        stop_loss=new_stop,
        take_profit=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        indicators=ind,
    ), ""


def resolve_gold_live_price(cfg, session=None, *, require_mt5: bool = True
                            ) -> tuple[float, str]:
    """Return (mid, source). Gold publish requires a fresh MT5 quote.

    When `require_mt5` is False (e.g. drift-expire housekeeping), falls back
    to Kraken PAXG if the EA tick is stale.
    """
    tick = fetch_mt5_last_tick(
        "XAUUSD", cfg.supabase_url, cfg.supabase_service_key, session=session,
    )
    if mt5_tick_is_fresh(tick):
        mid = float(tick.get("mid") or tick["price"])
        return mid, "mt5"
    if require_mt5:
        raise RuntimeError(
            "MT5 tick missing or stale — refusing gold publish "
            "(keep QauntifyTickPush EA running on XAUUSD)"
        )
    return fetch_gold_last_price(session=session), "paxg"
