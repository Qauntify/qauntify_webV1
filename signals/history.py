"""Deep historical candles for backtesting — NOT the live engine's data path.

`signals/market_client.py` serves the live scans, and both of its sources cap
hard: Kraken returns at most 721 OHLC bars whatever you ask for, and offers no
deeper history, which is roughly 30 days at 1h. That is far too little to
decide whether a strategy has an edge — it covers a single market regime.

This module reads Binance's published monthly kline archives instead, which
reach back to 2017-08 for BTCUSDT and ETHUSDT. Nine years spans the 2018 bear
market, the March 2020 liquidity crash, the 2021 bull run, the 2022
LUNA/FTX collapse and the recovery since — the regime diversity a four-month
sample cannot provide.

INTEGRITY IS ENFORCED, NOT ASSUMED. Binance publishes a SHA256 beside every
archive, and `download_month` verifies it before the file is parsed. A mismatch
raises rather than returning candles of unknown provenance: a backtest run on
corrupted or substituted data is worse than no backtest, because it produces a
number that looks authoritative and is not.

Two format changes across the archive's lifetime are handled here, because
missing either silently corrupts a long series rather than failing loudly:

  * Timestamps switched from MILLIseconds to MICROseconds during 2025. Mixed
    unnormalised, a series jumps 1000x forward mid-stream.
  * Some archives carry a CSV header row and others do not.

This is a backtest-only path. Nothing in the live engine imports it.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

from signals.models import Candle

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

# App symbol -> Binance spot pair. Only USDT pairs exist for these; gold and FX
# are not listed on Binance at all, so they are rejected rather than guessed.
BINANCE_PAIR = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
}

# Earliest month each pair is published for.
EARLIEST_MONTH = "2017-08"

DEFAULT_CACHE = Path(".cache/binance")

# A millisecond epoch for any plausible date is 13 digits; microseconds are 16.
# Anything at or above this threshold is microseconds.
_MICROSECOND_FLOOR = 10 ** 14


def binance_symbol(symbol: str) -> str:
    """Map an app symbol to its Binance spot pair.

    Raises for markets Binance does not list. Returning a guessed "XAUUSDT"
    would 404 at best, and at worst fetch an unrelated market that happens to
    exist — a silent data substitution in a backtest.
    """
    pair = BINANCE_PAIR.get((symbol or "").strip().upper())
    if pair is None:
        raise ValueError(
            f"{symbol!r} is not available from the Binance archives "
            f"(supported: {', '.join(sorted(set(BINANCE_PAIR.values())))})"
        )
    return pair


def archive_url(symbol: str, interval: str, month: str) -> str:
    pair = binance_symbol(symbol)
    return f"{BASE_URL}/{pair}/{interval}/{pair}-{interval}-{month}.zip"


def checksum_url(symbol: str, interval: str, month: str) -> str:
    return archive_url(symbol, interval, month) + ".CHECKSUM"


def months_between(start: str, end: str) -> list[str]:
    """Inclusive list of "YYYY-MM" strings from `start` to `end`."""
    start_year, start_month = (int(p) for p in start.split("-"))
    end_year, end_month = (int(p) for p in end.split("-"))
    first = start_year * 12 + (start_month - 1)
    last = end_year * 12 + (end_month - 1)
    if last < first:
        raise ValueError(f"end {end!r} is before start {start!r}")
    return [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(first, last + 1)]


def verify_checksum(path: Path, published: str) -> None:
    """Raise unless `path` hashes to the digest in Binance's .CHECKSUM body.

    The published file is of the form "<sha256>  <filename>".
    """
    expected = (published or "").strip().split()
    if not expected:
        raise ValueError(f"empty checksum published for {path.name}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected[0]:
        raise ValueError(
            f"checksum mismatch for {path.name}: "
            f"published {expected[0]}, computed {actual}"
        )


def _normalize_epoch_ms(raw: int) -> int:
    """Binance switched kline timestamps to microseconds during 2025."""
    return raw // 1000 if raw >= _MICROSECOND_FLOOR else raw


def parse_klines(payload: bytes) -> list[Candle]:
    """Parse a Binance kline CSV body into Candles, ascending by open time.

    Rows that are blank, short, or a header are skipped rather than raising:
    the archive format has varied over nine years, and one stray row should not
    discard a whole month.
    """
    candles: list[Candle] = []
    for row in csv.reader(io.StringIO(payload.decode())):
        if len(row) < 6:
            continue
        try:
            open_time = _normalize_epoch_ms(int(row[0]))
            candles.append(Candle(
                open_time=open_time,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            ))
        except ValueError:
            continue  # header row, or a malformed line
    candles.sort(key=lambda c: c.open_time)
    return candles


def load_month(path: Path) -> list[Candle]:
    """Read the single CSV inside a downloaded monthly archive."""
    with zipfile.ZipFile(path) as archive:
        name = archive.namelist()[0]
        return parse_klines(archive.read(name))


def download_month(symbol, interval, month, session, cache_dir=DEFAULT_CACHE):
    """Fetch one verified monthly archive, caching it on disk.

    A cached file is trusted without re-downloading its checksum — it was
    verified when it was written, and re-verifying every run would make a
    nine-year sweep pay for hundreds of extra requests. Delete the cache to
    force a re-fetch.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pair = binance_symbol(symbol)
    path = cache_dir / f"{pair}-{interval}-{month}.zip"
    if path.exists():
        return path

    response = session.get(archive_url(symbol, interval, month), timeout=60)
    response.raise_for_status()
    published = session.get(checksum_url(symbol, interval, month), timeout=30)
    published.raise_for_status()

    tmp = path.with_suffix(".zip.part")
    tmp.write_bytes(response.content)
    try:
        verify_checksum(tmp, published.text)
    except ValueError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.rename(path)
    return path


def load_history(symbol, interval, start=EARLIEST_MONTH, end=None,
                 session=None, cache_dir=DEFAULT_CACHE, on_month=None):
    """Every verified candle for `symbol` between `start` and `end` months.

    Months that 404 are skipped — the current month has no monthly archive yet,
    and a pair's listing date may fall inside the requested range. Any other
    error, including a checksum mismatch, propagates.

    `on_month(month, count)` is called after each month for progress reporting.
    """
    import requests

    session = session or requests.Session()
    if end is None:
        import datetime as dt
        today = dt.datetime.now(dt.UTC)
        end = f"{today.year:04d}-{today.month:02d}"

    candles: list[Candle] = []
    for month in months_between(start, end):
        try:
            path = download_month(symbol, interval, month, session, cache_dir)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 404:
                if on_month:
                    on_month(month, 0)
                continue
            raise
        month_candles = load_month(path)
        candles.extend(month_candles)
        if on_month:
            on_month(month, len(month_candles))

    candles.sort(key=lambda c: c.open_time)
    # Archive boundaries can repeat a bar; keep the first of any duplicate.
    deduped: list[Candle] = []
    for candle in candles:
        if deduped and candle.open_time == deduped[-1].open_time:
            continue
        deduped.append(candle)
    return deduped
