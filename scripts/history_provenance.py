"""Prove the backtest history is real market data, not simulated.

A backtest is only worth the data under it, and "I downloaded a file" is not
evidence of authenticity. This script establishes provenance two independent
ways, and fails loudly if either does not hold.

1. CRYPTOGRAPHIC. Every monthly archive is verified against the SHA256 digest
   Binance publishes beside it (see signals/history.download_month). A mismatch
   raises before the file is ever parsed.

2. HISTORICAL. Checksums prove a file is unmodified, not that its contents are
   real prices — a self-consistent fake would pass. So this script also locates
   well-known market events in the data and checks that they appear at the
   right dates and magnitudes. Simulated or randomly-generated candles do not
   reproduce Black Thursday to the hour, or put BTC's all-time high in the
   correct month.

Landmarks are stated as date windows and price ranges rather than exact values,
because Binance's prints differ slightly from other venues' and the point is
provenance, not tick-accuracy.

Usage: .venv/bin/python -m scripts.history_provenance
"""
import datetime as dt

import requests

from signals.analysis.history import EARLIEST_MONTH, load_history

# (label, expected UTC date window, expected price window, what to find)
LANDMARKS = (
    ("2017 blow-off top", "2017-12-01", "2017-12-31", 17_000, 21_000, "high"),
    ("2018 bear-market low", "2018-12-01", "2018-12-31", 3_000, 3_600, "low"),
    ("COVID crash (Black Thursday)", "2020-03-11", "2020-03-14", 3_500, 4_500, "low"),
    ("2021 all-time high", "2021-11-01", "2021-11-30", 66_000, 71_000, "high"),
    ("FTX collapse low", "2022-11-01", "2022-11-30", 15_000, 16_500, "low"),
)


def _utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def _window(candles, start, end):
    lo = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC).timestamp() * 1000
    hi = (dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC).timestamp()
          + 86400) * 1000
    return [c for c in candles if lo <= c.open_time < hi]


def check_landmarks(candles):
    """Return (label, ok, detail) for each known market event."""
    results = []
    for label, start, end, low, high, kind in LANDMARKS:
        window = _window(candles, start, end)
        if not window:
            results.append((label, False, "no candles in window"))
            continue
        if kind == "high":
            bar = max(window, key=lambda c: c.high)
            price = bar.high
        else:
            bar = min(window, key=lambda c: c.low)
            price = bar.low
        ok = low <= price <= high
        detail = (f"{kind} ${price:,.0f} on {_utc(bar.open_time):%Y-%m-%d %H:%M} "
                  f"UTC (expected ${low:,.0f}-${high:,.0f})")
        results.append((label, ok, detail))
    return results


def worst_hour(candles):
    bar = min(candles, key=lambda c: (c.close - c.open) / c.open)
    return bar, (bar.close - bar.open) / bar.open * 100


def gap_report(candles, interval_ms):
    gaps = [(a, b) for a, b in zip(candles, candles[1:])
            if b.open_time - a.open_time != interval_ms]
    missing = sum((b.open_time - a.open_time) // interval_ms - 1 for a, b in gaps)
    return len(gaps), missing


def main():
    session = requests.Session()
    verified = []

    def progress(month, count):
        verified.append((month, count))
        if count:
            print(f"  verified {month}: {count:5d} bars", flush=True)

    print("Downloading and SHA256-verifying Binance monthly archives "
          f"from {EARLIEST_MONTH}. Cached under .cache/binance.\n")
    candles = load_history("BTCUSD", "1h", session=session, on_month=progress)

    months_with_data = [m for m, n in verified if n]
    print(f"\n{'=' * 70}\nCRYPTOGRAPHIC PROVENANCE")
    print(f"  archives verified against Binance's published SHA256: "
          f"{len(months_with_data)}")
    print(f"  a mismatch would have raised before parsing — none did")

    print(f"\nDATA SPAN")
    print(f"  bars      : {len(candles):,}")
    print(f"  from      : {_utc(candles[0].open_time):%Y-%m-%d %H:%M} UTC")
    print(f"  to        : {_utc(candles[-1].open_time):%Y-%m-%d %H:%M} UTC")
    years = (candles[-1].open_time - candles[0].open_time) / 1000 / 86400 / 365.25
    print(f"  span      : {years:.2f} years")
    runs, missing = gap_report(candles, 3_600_000)
    print(f"  gaps      : {runs} discontinuities, {missing} missing hours "
          f"(real exchange outages; synthetic series have none)")

    print(f"\nHISTORICAL PROVENANCE")
    results = check_landmarks(candles)
    for label, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:32} {detail}")

    bar, pct = worst_hour(candles)
    print(f"\n  worst single hour in {years:.1f} years: {pct:+.1f}% on "
          f"{_utc(bar.open_time):%Y-%m-%d %H:%M} UTC")

    failed = [label for label, ok, _ in results if not ok]
    print(f"\n{'=' * 70}")
    if failed:
        print(f"PROVENANCE FAILED for: {', '.join(failed)}")
        raise SystemExit(1)
    print("PROVENANCE ESTABLISHED — checksums verified and every landmark "
          "market event appears at the correct date and price.")


if __name__ == "__main__":
    main()
