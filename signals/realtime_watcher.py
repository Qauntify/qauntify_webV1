"""Real-time SL/TP outcome tracking — fed by Kraken WS ticks (BTCUSD, ETHUSD,
GBPUSD) and an MT5 EA pushing XAUUSD ticks over localhost HTTP.

A tick is just a degenerate one-point candle, so this reuses
check_outcome_events / apply_events (signals/outcome_tracker.py) completely
unchanged from the slow ~10-min cron path (signals/run.py -> track_open_
signals). The two paths can never diverge on the TP-ladder / breakeven /
partial-win-reclassification rules because they're the same code — this
process is purely a faster, tick-driven way to feed it events. The cron path
stays on as a safety net for when this process (or the VPS) is down.

Usage: python -m signals.realtime_watcher
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from signals.config import Config
from signals.market_client import fetch_candles
from signals.models import Candle
from signals.outcome_tracker import apply_events, check_outcome_events
from signals.storage import list_open_signals

CACHE_REFRESH_SECONDS = 10
HISTORY_LIMIT = 1000
TICK_HTTP_PORT = int(os.environ.get("MT5_TICK_PORT", "8787"))

# App symbol -> Kraken WebSocket v2 ticker symbol. REST OHLC uses a different
# naming convention (signals/market_client.py:kraken_pair, e.g. "XBTUSD") --
# confirm this against Kraken's current WS v2 docs before relying on it live,
# it is not exercised by anything network-dependent in this repo's tests.
KRAKEN_WS_PAIR_BY_SYMBOL = {
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "GBPUSD": "GBP/USD",
}
KRAKEN_WS_URL = "wss://ws.kraken.com/v2"


def load_watcher_config() -> Config:
    """Env-only config for this standalone process.

    Deliberately not signals.config.load_config(): that hard-SystemExits
    without a SEA-LION key, which this process never needs.
    """
    from dotenv import load_dotenv
    load_dotenv()  # no-op under systemd (EnvironmentFile already set these);
                   # picks up a local .env for manual/VPS-shell runs.
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not supabase_service_key:
        raise SystemExit(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return Config(
        sealion_api_key="",
        supabase_url=supabase_url,
        supabase_service_key=supabase_service_key,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_channel_id=(
            os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
            or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        ),
    )


class RealtimeWatcher:
    """Holds the open-signals cache and applies incoming ticks against it."""

    def __init__(self, cfg: Config, session=None):
        self.cfg = cfg
        self.session = session or requests.Session()
        self.cache: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def refresh_cache(self) -> None:
        rows = list_open_signals(self.cfg.supabase_url,
                                 self.cfg.supabase_service_key,
                                 session=self.session)
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["symbol"], []).append(row)
        with self._lock:
            self.cache = grouped

    def handle_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        """Check every open signal on `symbol` against this one price."""
        with self._lock:
            rows = list(self.cache.get(symbol, []))
        if not rows:
            return

        candle = Candle(open_time=ts_ms, open=price, high=price, low=price,
                        close=price, volume=0.0)
        for row in rows:
            events = check_outcome_events(row, [candle])
            if not events:
                continue

            timeframe = row.get("timeframe") or "1h"
            try:
                # Real history for the outcome chart -- a single tick can't
                # render one. Only fetched on an actual hit, not per tick.
                window = fetch_candles(symbol, timeframe, HISTORY_LIMIT,
                                       session=self.session)[:-1]
            except Exception as exc:
                print(f"[{symbol}] realtime chart fetch failed "
                      f"({type(exc).__name__}), applying without a chart window")
                window = []

            final_row, latest = apply_events(row, events, window, self.cfg,
                                             session=self.session)
            if latest is None:
                continue  # claim lost the race against the slow cron path

            with self._lock:
                bucket = [r for r in self.cache.get(symbol, [])
                         if r["id"] != row["id"]]
                if final_row.get("closed_at") is None:
                    bucket.append(final_row)  # still open (e.g. tp1_hit only)
                self.cache[symbol] = bucket


class _TickHandler(BaseHTTPRequestHandler):
    """POST /tick {"symbol": "XAUUSD", "price": ..., "time": ...} from the
    MT5 EA. Bound to 127.0.0.1 only by the server below -- never internet-
    facing, but still secret-gated for defense in depth."""

    watcher: RealtimeWatcher = None  # set by serve_mt5_tick_receiver
    secret: str = ""

    def log_message(self, *args):  # quiet the default stderr access log
        pass

    def do_POST(self):
        if self.path != "/tick":
            self.send_response(404)
            self.end_headers()
            return
        if self.headers.get("Authorization") != f"Bearer {self.secret}":
            self.send_response(401)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            symbol = str(body["symbol"])
            price = float(body["price"])
            ts_ms = int(float(body["time"]) * 1000)
        except (KeyError, ValueError, json.JSONDecodeError):
            self.send_response(400)
            self.end_headers()
            return
        # WebRequest() in MQL5 is synchronous and blocks the terminal until
        # this responds -- respond immediately and do the actual outcome
        # check (Supabase + Telegram on a real hit, can take a second-plus)
        # in the background so a TP/SL hit never stalls the EA.
        threading.Thread(target=self.watcher.handle_tick,
                         args=(symbol, price, ts_ms), daemon=True).start()
        self.send_response(200)
        self.end_headers()


def serve_mt5_tick_receiver(watcher: RealtimeWatcher, secret: str,
                            port: int = TICK_HTTP_PORT) -> ThreadingHTTPServer:
    """Starts the localhost-only MT5 tick receiver in a background thread."""
    handler = type("_BoundTickHandler", (_TickHandler,),
                   {"watcher": watcher, "secret": secret})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"MT5 tick receiver listening on http://127.0.0.1:{port}/tick")
    return server


async def run_kraken_ws(watcher: RealtimeWatcher) -> None:
    """Subscribes to BTCUSD/ETHUSD/GBPUSD tickers, reconnecting on drop."""
    import websockets  # imported lazily: only this coroutine needs it

    pairs = list(KRAKEN_WS_PAIR_BY_SYMBOL.values())
    symbol_by_pair = {v: k for k, v in KRAKEN_WS_PAIR_BY_SYMBOL.items()}
    backoff = 1
    while True:
        try:
            async with websockets.connect(KRAKEN_WS_URL) as ws:
                await ws.send(json.dumps({
                    "method": "subscribe",
                    "params": {"channel": "ticker", "symbol": pairs},
                }))
                backoff = 1
                async for raw in ws:
                    message = json.loads(raw)
                    if message.get("channel") != "ticker":
                        continue
                    for tick in message.get("data", []):
                        pair = tick.get("symbol")
                        symbol = symbol_by_pair.get(pair)
                        price = tick.get("last")
                        if symbol is None or price is None:
                            continue
                        ts_ms = int(asyncio.get_event_loop().time() * 1000)
                        await asyncio.to_thread(
                            watcher.handle_tick, symbol, float(price), ts_ms)
        except Exception as exc:
            print(f"Kraken WS disconnected ({type(exc).__name__}: {exc}), "
                  f"reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def _refresh_cache_loop(watcher: RealtimeWatcher) -> None:
    while True:
        try:
            await asyncio.to_thread(watcher.refresh_cache)
        except Exception as exc:
            print(f"cache refresh failed ({type(exc).__name__}), retrying")
        await asyncio.sleep(CACHE_REFRESH_SECONDS)


async def _main_async() -> None:
    cfg = load_watcher_config()
    secret = os.environ.get("MT5_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise SystemExit("MT5_WEBHOOK_SECRET must be set")

    watcher = RealtimeWatcher(cfg)
    watcher.refresh_cache()
    serve_mt5_tick_receiver(watcher, secret)

    await asyncio.gather(
        run_kraken_ws(watcher),
        _refresh_cache_loop(watcher),
    )


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
