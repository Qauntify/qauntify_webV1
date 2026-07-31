"""Unit tests for the deep-history archive loader.

Offline by design: every test builds its own zip in a tmp dir. The proof that
the REAL archives are genuine lives in scripts/history_provenance.py, which
checks Binance's published SHA256 and known market events.
"""
import csv
import hashlib
import io
import zipfile

import pytest

from signals.history import (
    archive_url,
    binance_symbol,
    checksum_url,
    load_month,
    months_between,
    parse_klines,
    verify_checksum,
)

# Two real BTCUSDT 1h rows from 2020-03 (millisecond timestamps).
MS_ROWS = [
    ["1583020800000", "8523.61000000", "8613.57000000", "8511.11000000",
     "8547.25000000", "1952.74052000", "1583024399999", "16737893.23371445",
     "22876", "899.85114400", "7713994.59225310", "0"],
    ["1583024400000", "8546.65000000", "8649.00000000", "8514.06000000",
     "8639.28000000", "1901.27328700", "1583027999999", "16303469.52507139",
     "24731", "957.41463900", "8212831.49098135", "0"],
]

# Two real BTCUSDT 1h rows from 2025-06 — Binance switched to MICROSECONDS.
US_ROWS = [
    ["1748736000000000", "104591.88000000", "104647.11000000", "104320.02000000",
     "104446.49000000", "293.78295000", "1748739599999999", "30688862.20908260",
     "81426", "131.48518000", "13734263.47444880", "0"],
]

HEADER = ["open_time", "open", "high", "low", "close", "volume", "close_time",
          "quote_volume", "count", "taker_buy_volume", "taker_buy_quote", "ignore"]


def _csv_bytes(rows, header=False):
    buf = io.StringIO()
    writer = csv.writer(buf)
    if header:
        writer.writerow(HEADER)
    writer.writerows(rows)
    return buf.getvalue().encode()


def _zip(tmp_path, name, rows, header=False):
    path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{name}.csv", _csv_bytes(rows, header))
    return path


# --- symbol + URL mapping ---------------------------------------------------

def test_binance_symbol_maps_usd_to_usdt():
    assert binance_symbol("BTCUSD") == "BTCUSDT"
    assert binance_symbol("ETHUSD") == "ETHUSDT"


def test_binance_symbol_passes_usdt_through():
    assert binance_symbol("BTCUSDT") == "BTCUSDT"


def test_binance_symbol_rejects_unsupported_market():
    """Gold and FX are not on Binance. Silently returning 'XAUUSDT' would 404
    at best and fetch an unrelated market at worst."""
    with pytest.raises(ValueError):
        binance_symbol("XAUUSD")
    with pytest.raises(ValueError):
        binance_symbol("GBPUSD")


def test_archive_and_checksum_urls():
    url = archive_url("BTCUSD", "1h", "2020-03")
    assert url.endswith("/BTCUSDT/1h/BTCUSDT-1h-2020-03.zip")
    assert checksum_url("BTCUSD", "1h", "2020-03") == url + ".CHECKSUM"


# --- month ranges -----------------------------------------------------------

def test_months_between_is_inclusive():
    assert months_between("2020-11", "2021-02") == [
        "2020-11", "2020-12", "2021-01", "2021-02"]


def test_months_between_single_month():
    assert months_between("2020-03", "2020-03") == ["2020-03"]


def test_months_between_rejects_reversed_range():
    with pytest.raises(ValueError):
        months_between("2021-01", "2020-01")


# --- parsing ----------------------------------------------------------------

def test_parses_millisecond_archives():
    candles = parse_klines(_csv_bytes(MS_ROWS))
    assert len(candles) == 2
    assert candles[0].open_time == 1583020800000
    assert candles[0].open == 8523.61
    assert candles[0].high == 8613.57
    assert candles[0].low == 8511.11
    assert candles[0].close == 8547.25
    assert candles[0].volume == 1952.74052


def test_parses_microsecond_archives_to_milliseconds():
    """Binance switched to microsecond timestamps in 2025. Left unnormalised,
    a multi-year series would jump 1000x forward mid-stream and every
    higher-timeframe alignment would silently break."""
    candles = parse_klines(_csv_bytes(US_ROWS))
    assert len(candles) == 1
    assert candles[0].open_time == 1748736000000       # not ...000000
    assert candles[0].close == 104446.49


def test_skips_a_header_row_when_present():
    candles = parse_klines(_csv_bytes(MS_ROWS, header=True))
    assert len(candles) == 2
    assert candles[0].open_time == 1583020800000


def test_ignores_blank_and_short_rows():
    candles = parse_klines(_csv_bytes(MS_ROWS + [[], ["1583028000000", "1.0"]]))
    assert len(candles) == 2


# --- checksum integrity -----------------------------------------------------

def test_verify_checksum_accepts_a_matching_digest(tmp_path):
    path = _zip(tmp_path, "BTCUSDT-1h-2020-03", MS_ROWS)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verify_checksum(path, f"{digest}  BTCUSDT-1h-2020-03.zip")


def test_verify_checksum_rejects_a_mismatch(tmp_path):
    """Fail closed: a backtest run on candles of unknown provenance is worse
    than no backtest at all."""
    path = _zip(tmp_path, "BTCUSDT-1h-2020-03", MS_ROWS)
    with pytest.raises(ValueError, match="checksum"):
        verify_checksum(path, "0" * 64 + "  BTCUSDT-1h-2020-03.zip")


def test_verify_checksum_rejects_an_empty_published_digest(tmp_path):
    path = _zip(tmp_path, "BTCUSDT-1h-2020-03", MS_ROWS)
    with pytest.raises(ValueError):
        verify_checksum(path, "")


# --- month loading ----------------------------------------------------------

def test_load_month_reads_the_csv_inside_the_zip(tmp_path):
    path = _zip(tmp_path, "BTCUSDT-1h-2020-03", MS_ROWS)
    candles = load_month(path)
    assert len(candles) == 2
    assert candles[0].close == 8547.25


def test_load_month_returns_candles_ascending(tmp_path):
    path = _zip(tmp_path, "BTCUSDT-1h-2020-03", list(reversed(MS_ROWS)))
    candles = load_month(path)
    assert candles[0].open_time < candles[1].open_time
