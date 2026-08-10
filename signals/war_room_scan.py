"""Independent Trading Floor / War Room signal pipeline.

Scans BTCUSD / ETHUSD / XAUUSD on 15m (cloud_mss candidates), then Structure +
Momentum + Manager on FLOOR_LLM_* keys decide whether to publish. Stored rows
use timeframe="floor" + indicators.channel="war_room" so they never appear in
Super Scalp / Scalp / Swing tabs and never collide with 15m scalp uniqueness.

Usage: python -m signals.war_room_scan
"""
from dataclasses import replace

import requests

from signals.chart.pipeline import attach_chart
from signals.config import Config, load_floor_config
from signals.debate import FloorAgents, run_debate
from signals.llm_client import SeaLionClient
from signals.market_client import is_gold_symbol, setup_stop_risk_ok
from signals.models import Confirmation, make_signal
from signals.run import (
    _load_market_data,
    _snap_gold_setup_to_live,
    already_signaled,
    resolve_gold_live_price,
    with_retry,
)
from signals.storage import (
    fetch_mt5_last_tick,
    save_debate,
    save_signal,
)
from signals.strategies import detect_setup
from signals.telegram_client import send_alert

CANDLE_TIMEFRAME = "15m"
STORE_TIMEFRAME = "floor"
STRATEGY = "cloud_mss"
CHANNEL = "war_room"


def _floor_agents(floor, session=None) -> FloorAgents:
    kw = dict(
        model=floor.model, base_url=floor.base_url, session=session,
    )
    return FloorAgents(
        structure=SeaLionClient(api_key=floor.structure_key, **kw),
        momentum=SeaLionClient(api_key=floor.momentum_key, **kw),
        manager=SeaLionClient(api_key=floor.manager_key, **kw),
    )


def _as_engine_cfg(floor) -> Config:
    """Minimal Config so gold snap / chart helpers can reuse run.py paths."""
    return Config(
        sealion_api_key=floor.manager_key,
        sealion_api_keys=(floor.structure_key, floor.momentum_key, floor.manager_key),
        supabase_url=floor.supabase_url,
        supabase_service_key=floor.supabase_service_key,
        telegram_bot_token=floor.telegram_bot_token,
        telegram_channel_id=floor.telegram_channel_id,
        sealion_base_url=floor.base_url,
        sealion_model=floor.model,
    )


def scan_symbol_floor(symbol, floor, agents, *, session=None):
    """One symbol: candidate on 15m → Floor debate → optional War Room store."""
    session = session or requests.Session()
    cfg = _as_engine_cfg(floor)

    market, candles = _load_market_data(
        symbol, CANDLE_TIMEFRAME, STRATEGY, cfg,
        confluence_timeframe=None, session=session,
    )
    if market is None:
        return None

    setup = detect_setup(
        STRATEGY, symbol, market.candles,
        market.ema9, market.ema21, market.rsi14, market.macd_hist, market.atr14,
        adx14=market.adx14, htf_trend=market.htf_trend,
        h1_candles=market.h1_candles,
    )
    if setup is None:
        print(f"[{symbol}] war-room: no {STRATEGY} candidate on {CANDLE_TIMEFRAME}")
        return None

    if already_signaled(setup, cfg, timeframe=STORE_TIMEFRAME, session=session):
        print(f"[{symbol}] war-room: open/recent floor signal, skipping")
        return None

    tp1, tp2, tp3 = setup.resolved_take_profits()
    print(f"[{symbol}] war-room candidate {setup.direction}: "
          f"entry={setup.entry} SL={setup.stop_loss} "
          f"TP1={tp1} TP2={tp2} TP3={tp3}")

    debate = run_debate(
        setup, agents=agents, timeframe=CANDLE_TIMEFRAME, gate=True,
    )
    verdict = debate["manager_verdict"]
    confidence = debate["manager_confidence"]
    print(f"[{symbol}] war-room manager: {verdict} {confidence}%")
    if verdict != "agree":
        return None

    ind = dict(setup.indicators)
    ind["channel"] = CHANNEL
    ind["candle_timeframe"] = CANDLE_TIMEFRAME
    ind["floor"] = True
    setup = replace(setup, indicators=ind)

    if is_gold_symbol(symbol):
        try:
            live, live_source = resolve_gold_live_price(
                cfg, session=session, require_mt5=True,
            )
            pre = setup
            setup, note = _snap_gold_setup_to_live(
                setup, live, CANDLE_TIMEFRAME, source=live_source,
            )
            if setup is None:
                print(f"[{symbol}] war-room live gate blocked: {note}")
                return None
            if setup.entry != pre.entry:
                print(f"[{symbol}] war-room snapped {pre.entry:.2f} "
                      f"-> {live_source} {setup.entry:.2f}")
            tick = fetch_mt5_last_tick(
                "XAUUSD", cfg.supabase_url, cfg.supabase_service_key,
                session=session,
            )
            if tick:
                ind = dict(setup.indicators)
                ind["mt5_bid"] = tick.get("bid")
                ind["mt5_ask"] = tick.get("ask")
                ind["mt5_mid"] = tick.get("mid") or live
                setup = replace(setup, indicators=ind)
        except Exception as exc:
            print(f"[{symbol}] war-room gold gate blocked: {exc}")
            return None

    ok, stop_note = setup_stop_risk_ok(setup.entry, setup.stop_loss)
    if not ok:
        print(f"[{symbol}] war-room {stop_note}")
        return None

    confirmation = Confirmation(
        "confirm", confidence, debate["transcript"][-1]["message"],
    )
    signal = make_signal(setup, confirmation, [], timeframe=STORE_TIMEFRAME)
    signal = attach_chart(
        signal, market.candles,
        supabase_url=cfg.supabase_url, service_key=cfg.supabase_service_key,
        session=session, h1_candles=market.h1_candles,
    )
    try:
        with_retry(lambda: save_signal(
            signal, cfg.supabase_url, cfg.supabase_service_key, session=session,
        ))
    except Exception as exc:
        print(f"[{symbol}] war-room store failed ({type(exc).__name__})")
        return None

    debate["signal_id"] = signal.id
    debate["timeframe"] = STORE_TIMEFRAME
    try:
        save_debate(
            debate, cfg.supabase_url, cfg.supabase_service_key, session=session,
        )
    except Exception as exc:
        print(f"[{symbol}] war-room debate save skipped ({type(exc).__name__})")

    if cfg.telegram_bot_token and cfg.telegram_channel_id:
        try:
            with_retry(lambda: send_alert(
                signal, cfg.telegram_bot_token, cfg.telegram_channel_id,
            ))
            print(f"[{symbol}] war-room Telegram alert sent")
        except Exception as exc:
            print(f"[{symbol}] war-room Telegram failed ({type(exc).__name__})")

    print(f"[{symbol}] WAR ROOM CONFIRMED {signal.direction.upper()} "
          f"(confidence {signal.confidence})")
    return signal


def main():
    floor = load_floor_config()
    session = requests.Session()
    agents = _floor_agents(floor, session=session)
    print(f"War Room Floor scanning {', '.join(floor.symbols)} "
          f"on {CANDLE_TIMEFRAME} ({STRATEGY}) → store as {STORE_TIMEFRAME}")
    stored = 0
    for symbol in floor.symbols:
        try:
            signal = scan_symbol_floor(symbol, floor, agents, session=session)
            if signal is not None:
                stored += 1
        except Exception as exc:
            print(f"[{symbol}] war-room error: {type(exc).__name__}: {exc}")
    print(f"Done. {stored} War Room signal(s) stored.")


if __name__ == "__main__":
    main()
