# ThinkTrade Signals Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An on-demand Python script that scans BTCUSDT/ETHUSDT 1h candles from Binance, derives technical setups (EMA/RSI/MACD/ATR), confirms them via SEA-LION with CryptoPanic news context, and stores confirmed signals in SQLite + JSON.

**Architecture:** Five independently testable modules — market data fetcher (Binance public API), pure-function indicator engine, news fetcher (CryptoPanic), signal composer (SEA-LION confirm/reject gate, fail-closed), and storage (SQLite + append-only JSON). A thin `run.py` pipeline wires them together with retry-once-then-skip error handling per symbol.

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`, `pytest`. No pandas — indicator math is pure Python over ~200 floats. SQLite via stdlib `sqlite3`. SEA-LION called via plain HTTPS (OpenAI-compatible endpoint `https://api.sea-lion.ai/v1/chat/completions`, model `aisingapore/Qwen-SEA-LION-v4.5-27B-IT`).

**Spec:** `docs/superpowers/specs/2026-07-05-signals-engine-design.md`

## File Structure

```
signals/
  __init__.py          # empty package marker
  config.py            # Config dataclass + load_config() from env/.env
  models.py            # Candle, CandidateSetup, Confirmation, Signal, make_signal()
  indicators.py        # ema(), rsi(), macd_histogram(), atr() — pure functions
  setup_detector.py    # crossed_above/below_within(), detect_setup()
  binance_client.py    # fetch_candles()
  news_client.py       # fetch_headlines() from CryptoPanic
  llm_client.py        # SeaLionClient.chat()
  composer.py          # build_messages(), parse_confirmation(), confirm_setup()
  storage.py           # init_db(), save_signal() → SQLite + JSON
  run.py               # with_retry(), scan_symbol(), main()
tests/
  test_config.py
  test_indicators.py
  test_setup_detector.py
  test_binance_client.py
  test_news_client.py
  test_llm_client.py
  test_composer.py
  test_storage.py
  test_pipeline.py
pyproject.toml         # pytest config only (pythonpath = ["."])
requirements.txt
.env.example
.gitignore
README.md
```

All indicator functions return lists aligned 1:1 with their input, padded with `None` during the warm-up window. `detect_setup()` takes precomputed indicator series as arguments (not raw candles only) so unit tests can feed handcrafted values deterministically; `run.py` computes the series and passes them in.

---

### Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`, `requirements.txt`, `pyproject.toml`, `.env.example`, `signals/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.env
signals.db
signals.json
.pytest_cache/
```

- [ ] **Step 2: Create `requirements.txt`**

```
requests>=2.31
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 3: Create `pyproject.toml`** (pytest config so `tests/` can import the `signals` package from repo root)

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 4: Create `.env.example`**

```
# SEA-LION API key — get one at https://playground.sea-lion.ai (Google sign-in)
SEALION_API_KEY=your-sealion-key-here

# CryptoPanic API key — https://cryptopanic.com/developers/api/keys
CRYPTOPANIC_API_KEY=your-cryptopanic-key-here
```

- [ ] **Step 5: Create empty `signals/__init__.py` and `tests/` directory**

```bash
touch signals/__init__.py
mkdir -p tests
```

- [ ] **Step 6: Create venv and install deps**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: installs requests, python-dotenv, pytest without errors.

- [ ] **Step 7: Commit**

```bash
git add .gitignore requirements.txt pyproject.toml .env.example signals/__init__.py
git commit -m "chore: scaffold signals engine project"
```

---

### Task 2: Models and config

**Files:**
- Create: `signals/models.py`, `signals/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write `signals/models.py`** (pure dataclasses — no test file needed beyond usage in later tasks)

```python
"""Core data types for the signals engine."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    open_time: int  # epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class CandidateSetup:
    symbol: str
    direction: str  # "long" | "short"
    entry: float
    stop_loss: float
    take_profit: float
    indicators: dict  # {"ema9":, "ema21":, "rsi":, "macd_hist":}


@dataclass(frozen=True)
class Confirmation:
    verdict: str  # "confirm" | "reject"
    confidence: int  # 0-100
    rationale: str


@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    timeframe: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    confidence: int
    rationale: str
    indicators: dict
    news_headlines: list
    created_at: str


def make_signal(setup: CandidateSetup, confirmation: Confirmation,
                headlines: list, timeframe: str = "1h") -> Signal:
    return Signal(
        id=str(uuid.uuid4()),
        symbol=setup.symbol,
        timeframe=timeframe,
        direction=setup.direction,
        entry=setup.entry,
        stop_loss=setup.stop_loss,
        take_profit=setup.take_profit,
        confidence=confirmation.confidence,
        rationale=confirmation.rationale,
        indicators=setup.indicators,
        news_headlines=list(headlines),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 2: Write the failing test** — `tests/test_config.py`

```python
import pytest

from signals.config import Config, load_config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    monkeypatch.setenv("CRYPTOPANIC_API_KEY", "cp-test")
    cfg = load_config()
    assert cfg.sealion_api_key == "sk-test"
    assert cfg.cryptopanic_api_key == "cp-test"
    assert cfg.symbols == ("BTCUSDT", "ETHUSDT")
    assert cfg.timeframe == "1h"


def test_load_config_missing_sealion_key_exits(monkeypatch):
    monkeypatch.delenv("SEALION_API_KEY", raising=False)
    monkeypatch.setenv("CRYPTOPANIC_API_KEY", "cp-test")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_missing_cryptopanic_key_exits(monkeypatch):
    monkeypatch.setenv("SEALION_API_KEY", "sk-test")
    monkeypatch.delenv("CRYPTOPANIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.config'`

- [ ] **Step 4: Write `signals/config.py`**

```python
"""Configuration loaded from environment / .env file."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    sealion_api_key: str
    cryptopanic_api_key: str
    symbols: tuple = ("BTCUSDT", "ETHUSDT")
    timeframe: str = "1h"
    candle_limit: int = 200
    db_path: str = "signals.db"
    json_path: str = "signals.json"
    sealion_base_url: str = "https://api.sea-lion.ai/v1"
    sealion_model: str = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


def load_config() -> Config:
    load_dotenv()
    sealion_key = os.environ.get("SEALION_API_KEY", "")
    cryptopanic_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
    if not sealion_key:
        raise SystemExit("SEALION_API_KEY is not set (copy .env.example to .env)")
    if not cryptopanic_key:
        raise SystemExit("CRYPTOPANIC_API_KEY is not set (copy .env.example to .env)")
    return Config(sealion_api_key=sealion_key, cryptopanic_api_key=cryptopanic_key)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add signals/models.py signals/config.py tests/test_config.py
git commit -m "feat: add core models and env config loader"
```

---

### Task 3: Indicator engine

**Files:**
- Create: `signals/indicators.py`
- Test: `tests/test_indicators.py`

All functions take a list of floats (closes, or highs/lows/closes for ATR) and return a list of the same length, with `None` for warm-up positions.

- [ ] **Step 1: Write the failing tests** — `tests/test_indicators.py`

```python
from signals.indicators import atr, ema, macd_histogram, rsi


def test_ema_constant_series_equals_constant():
    values = [50.0] * 30
    result = ema(values, 9)
    assert result[:8] == [None] * 8
    for v in result[8:]:
        assert abs(v - 50.0) < 1e-9


def test_ema_shorter_than_period_is_all_none():
    assert ema([1.0, 2.0, 3.0], 9) == [None, None, None]


def test_ema_tracks_rising_trend_below_price():
    values = [float(i) for i in range(1, 31)]  # 1..30 rising
    result = ema(values, 9)
    assert result[-1] is not None
    assert result[-1] < values[-1]  # EMA lags a rising price
    assert result[-1] > result[-2]  # but is itself rising


def test_rsi_all_gains_is_100():
    values = [float(i) for i in range(1, 31)]
    result = rsi(values, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert abs(v - 100.0) < 1e-9


def test_rsi_all_losses_is_0():
    values = [float(i) for i in range(31, 1, -1)]
    result = rsi(values, 14)
    for v in result[14:]:
        assert abs(v - 0.0) < 1e-9


def test_rsi_flat_series_is_50():
    values = [50.0] * 30
    result = rsi(values, 14)
    for v in result[14:]:
        assert abs(v - 50.0) < 1e-9


def test_macd_histogram_constant_series_is_zero():
    values = [50.0] * 60
    result = macd_histogram(values)
    assert result[-1] is not None
    assert abs(result[-1]) < 1e-9


def test_macd_histogram_length_matches_input():
    values = [float(i) for i in range(60)]
    assert len(macd_histogram(values)) == 60


def test_atr_constant_range_candles():
    n = 30
    highs = [102.0] * n
    lows = [98.0] * n
    closes = [100.0] * n
    result = atr(highs, lows, closes, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert abs(v - 4.0) < 1e-9  # high-low = 4 every bar


def test_atr_too_short_is_all_none():
    assert atr([1.0] * 5, [0.5] * 5, [0.8] * 5, 14) == [None] * 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.indicators'`

- [ ] **Step 3: Write `signals/indicators.py`**

```python
"""Pure-function technical indicators.

All functions return lists aligned 1:1 with their input, with None
padding during the indicator's warm-up window.
"""


def ema(values, period):
    """Exponential moving average seeded with the SMA of the first `period` values."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    if n < period:
        return [None] * n
    out = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    k = 2.0 / (period + 1)
    for v in values[period:]:
        prev = (v - prev) * k + prev
        out.append(prev)
    return out


def rsi(values, period=14):
    """Wilder-smoothed RSI. Flat series (no gains, no losses) is defined as 50."""
    n = len(values)
    if n < period + 1:
        return [None] * n
    out = [None] * period
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out.append(_rsi_value(avg_gain, avg_loss))
    for i in range(period + 1, n):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        out.append(_rsi_value(avg_gain, avg_loss))
    return out


def _rsi_value(avg_gain, avg_loss):
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd_histogram(values, fast=12, slow=26, signal=9):
    """MACD histogram: (EMA_fast - EMA_slow) minus its EMA_signal smoothing."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [
        f - s if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    start = next((i for i, v in enumerate(macd_line) if v is not None), len(macd_line))
    signal_line = [None] * start + ema(macd_line[start:], signal)
    return [
        m - s if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]


def atr(highs, lows, closes, period=14):
    """Wilder-smoothed Average True Range."""
    n = len(closes)
    if n < period + 1:
        return [None] * n
    true_ranges = [None]
    for i in range(1, n):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    out = [None] * period
    prev = sum(true_ranges[1:period + 1]) / period
    out.append(prev)
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + true_ranges[i]) / period
        out.append(prev)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add signals/indicators.py tests/test_indicators.py
git commit -m "feat: add EMA, RSI, MACD histogram, and ATR indicators"
```

---

### Task 4: Setup detector

**Files:**
- Create: `signals/setup_detector.py`
- Test: `tests/test_setup_detector.py`

`detect_setup()` receives candles plus precomputed indicator series so tests can hand-craft exact values. Long rule: EMA9 crossed above EMA21 within the last 3 bars AND RSI < 70 AND MACD hist > 0. Short rule is the mirror (cross below, RSI > 30, hist < 0). Stop = swing low/high of last 10 candles ± 0.5×ATR; TP at 1:2 risk-reward.

- [ ] **Step 1: Write the failing tests** — `tests/test_setup_detector.py`

```python
from signals.models import Candle
from signals.setup_detector import (
    crossed_above_within,
    crossed_below_within,
    detect_setup,
)


def _candles(prices, low_offset=1.0, high_offset=1.0):
    return [
        Candle(open_time=i, open=p, high=p + high_offset,
               low=p - low_offset, close=p, volume=1.0)
        for i, p in enumerate(prices)
    ]


def _flat(value, n):
    return [value] * n


def test_crossed_above_within_detects_recent_cross():
    fast = [1.0, 1.0, 1.0, 2.0, 3.0]
    slow = [2.0, 2.0, 2.0, 2.0, 2.0]  # fast crosses above at index 4
    assert crossed_above_within(fast, slow, lookback=3) is True


def test_crossed_above_within_ignores_old_cross():
    fast = [1.0, 3.0, 3.0, 3.0, 3.0, 3.0]  # crossed at index 1, too old
    slow = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
    assert crossed_above_within(fast, slow, lookback=3) is False


def test_crossed_above_within_handles_none_padding():
    fast = [None, None, 1.0, 2.5]
    slow = [None, None, 2.0, 2.0]
    assert crossed_above_within(fast, slow, lookback=3) is True


def test_crossed_below_within_detects_recent_cross():
    fast = [3.0, 3.0, 3.0, 3.0, 1.0]
    slow = [2.0, 2.0, 2.0, 2.0, 2.0]
    assert crossed_below_within(fast, slow, lookback=3) is True


def test_detect_setup_long():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]   # crosses above ema21 on last bar
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    setup = detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.entry == 100.0
    # swing low = 99.0 (price 100 - low_offset 1), stop = 99 - 0.5*2 = 98
    assert setup.stop_loss == 98.0
    # risk = 2.0 → TP = 100 + 2*2 = 104
    assert setup.take_profit == 104.0
    assert setup.indicators["rsi"] == 55.0


def test_detect_setup_long_blocked_by_overbought_rsi():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]
    ema21 = _flat(100.0, n)
    rsi14 = _flat(75.0, n)  # >= 70 blocks the long
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_long_blocked_by_negative_macd():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n - 1) + [101.0]
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(-0.5, n)  # negative momentum blocks the long
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_short():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(101.0, n - 1) + [99.0]   # crosses below ema21 on last bar
    ema21 = _flat(100.0, n)
    rsi14 = _flat(45.0, n)
    macd_hist = _flat(-0.5, n)
    atr14 = _flat(2.0, n)
    setup = detect_setup("ETHUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.entry == 100.0
    # swing high = 101.0, stop = 101 + 0.5*2 = 102, risk = 2 → TP = 96
    assert setup.stop_loss == 102.0
    assert setup.take_profit == 96.0


def test_detect_setup_no_cross_returns_none():
    n = 20
    candles = _candles([100.0] * n)
    ema9 = _flat(99.0, n)   # always below, never crosses
    ema21 = _flat(100.0, n)
    rsi14 = _flat(55.0, n)
    macd_hist = _flat(0.5, n)
    atr14 = _flat(2.0, n)
    assert detect_setup("BTCUSDT", candles, ema9, ema21, rsi14, macd_hist, atr14) is None


def test_detect_setup_warmup_none_returns_none():
    n = 5
    candles = _candles([100.0] * n)
    none_series = [None] * n
    assert detect_setup("BTCUSDT", candles, none_series, none_series,
                        none_series, none_series, none_series) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_setup_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.setup_detector'`

- [ ] **Step 3: Write `signals/setup_detector.py`**

```python
"""Derives a candidate trade setup from candles + precomputed indicators."""
from signals.models import CandidateSetup

CROSS_LOOKBACK = 3
SWING_WINDOW = 10
ATR_STOP_BUFFER = 0.5
RISK_REWARD = 2.0
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0


def crossed_above_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed above `slow` on any of the last `lookback` bars."""
    n = len(fast)
    for i in range(max(1, n - lookback), n):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            return True
    return False


def crossed_below_within(fast, slow, lookback=CROSS_LOOKBACK):
    """True if `fast` crossed below `slow` on any of the last `lookback` bars."""
    n = len(fast)
    for i in range(max(1, n - lookback), n):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            return True
    return False


def detect_setup(symbol, candles, ema9, ema21, rsi14, macd_hist, atr14):
    """Return a CandidateSetup if indicators align, else None."""
    if None in (ema9[-1], ema21[-1], rsi14[-1], macd_hist[-1], atr14[-1]):
        return None
    entry = candles[-1].close
    indicators = {
        "ema9": ema9[-1],
        "ema21": ema21[-1],
        "rsi": rsi14[-1],
        "macd_hist": macd_hist[-1],
    }
    recent = candles[-SWING_WINDOW:]

    if (crossed_above_within(ema9, ema21)
            and rsi14[-1] < RSI_OVERBOUGHT
            and macd_hist[-1] > 0):
        swing_low = min(c.low for c in recent)
        stop = swing_low - ATR_STOP_BUFFER * atr14[-1]
        if stop >= entry:
            return None
        take_profit = entry + RISK_REWARD * (entry - stop)
        return CandidateSetup(symbol, "long", entry, stop, take_profit, indicators)

    if (crossed_below_within(ema9, ema21)
            and rsi14[-1] > RSI_OVERSOLD
            and macd_hist[-1] < 0):
        swing_high = max(c.high for c in recent)
        stop = swing_high + ATR_STOP_BUFFER * atr14[-1]
        if stop <= entry:
            return None
        take_profit = entry - RISK_REWARD * (stop - entry)
        return CandidateSetup(symbol, "short", entry, stop, take_profit, indicators)

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_setup_detector.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add signals/setup_detector.py tests/test_setup_detector.py
git commit -m "feat: add candidate setup detector with crossover rules"
```

---

### Task 5: Binance market data client

**Files:**
- Create: `signals/binance_client.py`
- Test: `tests/test_binance_client.py`

Binance public klines endpoint (no API key): `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=200`. Each row is a 12-element array: `[open_time, open, high, low, close, volume, close_time, ...]` with prices as strings.

- [ ] **Step 1: Write the failing tests** — `tests/test_binance_client.py`

```python
import pytest

from signals.binance_client import fetch_candles


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.last_url = None
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        return FakeResponse(self._payload, self._status)


KLINE_ROWS = [
    [1720000000000, "100.0", "102.0", "99.0", "101.0", "1500.5",
     1720003599999, "0", 0, "0", "0", "0"],
    [1720003600000, "101.0", "103.0", "100.5", "102.5", "1200.0",
     1720007199999, "0", 0, "0", "0", "0"],
]


def test_fetch_candles_parses_klines():
    session = FakeSession(KLINE_ROWS)
    candles = fetch_candles("BTCUSDT", session=session)
    assert len(candles) == 2
    first = candles[0]
    assert first.open_time == 1720000000000
    assert first.open == 100.0
    assert first.high == 102.0
    assert first.low == 99.0
    assert first.close == 101.0
    assert first.volume == 1500.5


def test_fetch_candles_sends_correct_params():
    session = FakeSession(KLINE_ROWS)
    fetch_candles("ETHUSDT", interval="1h", limit=200, session=session)
    assert session.last_url == "https://api.binance.com/api/v3/klines"
    assert session.last_params == {"symbol": "ETHUSDT", "interval": "1h", "limit": 200}


def test_fetch_candles_raises_on_http_error():
    session = FakeSession([], status=500)
    with pytest.raises(RuntimeError):
        fetch_candles("BTCUSDT", session=session)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_binance_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.binance_client'`

- [ ] **Step 3: Write `signals/binance_client.py`**

```python
"""Fetches OHLCV candles from Binance's public REST API (no key required)."""
import requests

from signals.models import Candle

KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_candles(symbol, interval="1h", limit=200, session=None):
    session = session or requests.Session()
    response = session.get(
        KLINES_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=10,
    )
    response.raise_for_status()
    return [
        Candle(
            open_time=row[0],
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in response.json()
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_binance_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add signals/binance_client.py tests/test_binance_client.py
git commit -m "feat: add Binance klines client"
```

---

### Task 6: CryptoPanic news client

**Files:**
- Create: `signals/news_client.py`
- Test: `tests/test_news_client.py`

CryptoPanic developer v2 endpoint: `GET https://cryptopanic.com/api/developer/v2/posts/?auth_token=KEY&currencies=BTC&public=true`. Response JSON has a `results` array of posts, each with a `title` field. Trading symbols map to currency codes (BTCUSDT → BTC).

- [ ] **Step 1: Write the failing tests** — `tests/test_news_client.py`

```python
from signals.news_client import fetch_headlines


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        return FakeResponse(self._payload, self._status)


def test_fetch_headlines_returns_titles():
    payload = {"results": [
        {"title": "Bitcoin breaks resistance"},
        {"title": "ETF inflows surge"},
        {"title": None},
        {"no_title_key": True},
    ]}
    session = FakeSession(payload)
    headlines = fetch_headlines("BTCUSDT", api_key="cp-key", session=session)
    assert headlines == ["Bitcoin breaks resistance", "ETF inflows surge"]
    assert session.last_params["currencies"] == "BTC"
    assert session.last_params["auth_token"] == "cp-key"


def test_fetch_headlines_respects_limit():
    payload = {"results": [{"title": f"headline {i}"} for i in range(20)]}
    session = FakeSession(payload)
    headlines = fetch_headlines("ETHUSDT", api_key="cp-key", limit=10, session=session)
    assert len(headlines) == 10
    assert session.last_params["currencies"] == "ETH"


def test_fetch_headlines_unknown_symbol_returns_empty():
    session = FakeSession({"results": []})
    assert fetch_headlines("DOGEUSDT", api_key="cp-key", session=session) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_news_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.news_client'`

- [ ] **Step 3: Write `signals/news_client.py`**

```python
"""Fetches recent news headlines from the CryptoPanic developer API."""
import requests

POSTS_URL = "https://cryptopanic.com/api/developer/v2/posts/"

SYMBOL_TO_CURRENCY = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
}


def fetch_headlines(symbol, api_key, limit=10, session=None):
    currency = SYMBOL_TO_CURRENCY.get(symbol)
    if currency is None:
        return []
    session = session or requests.Session()
    response = session.get(
        POSTS_URL,
        params={"auth_token": api_key, "currencies": currency, "public": "true"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    titles = [post.get("title") for post in results]
    return [t for t in titles if t][:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_news_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add signals/news_client.py tests/test_news_client.py
git commit -m "feat: add CryptoPanic headlines client"
```

---

### Task 7: SEA-LION LLM client

**Files:**
- Create: `signals/llm_client.py`
- Test: `tests/test_llm_client.py`

SEA-LION is OpenAI-compatible: `POST https://api.sea-lion.ai/v1/chat/completions` with `Authorization: Bearer <key>`. Rate limit is 10 requests/minute — fine for 2 symbols per run.

- [ ] **Step 1: Write the failing tests** — `tests/test_llm_client.py`

```python
import pytest

from signals.llm_client import SeaLionClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeResponse(self._payload, self._status)


COMPLETION = {"choices": [{"message": {"content": '{"verdict": "confirm"}'}}]}


def test_chat_returns_message_content():
    session = FakeSession(COMPLETION)
    client = SeaLionClient(api_key="sk-test", session=session)
    result = client.chat([{"role": "user", "content": "hello"}])
    assert result == '{"verdict": "confirm"}'


def test_chat_sends_auth_and_model():
    session = FakeSession(COMPLETION)
    client = SeaLionClient(api_key="sk-test", session=session)
    client.chat([{"role": "user", "content": "hello"}])
    assert session.last_url == "https://api.sea-lion.ai/v1/chat/completions"
    assert session.last_headers["Authorization"] == "Bearer sk-test"
    assert session.last_json["model"] == "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
    assert session.last_json["messages"] == [{"role": "user", "content": "hello"}]


def test_chat_raises_on_http_error():
    session = FakeSession({}, status=429)
    client = SeaLionClient(api_key="sk-test", session=session)
    with pytest.raises(RuntimeError):
        client.chat([{"role": "user", "content": "hello"}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.llm_client'`

- [ ] **Step 3: Write `signals/llm_client.py`**

```python
"""Client for the SEA-LION chat completions API (OpenAI-compatible)."""
import requests

DEFAULT_BASE_URL = "https://api.sea-lion.ai/v1"
DEFAULT_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"


class SeaLionClient:
    def __init__(self, api_key, model=DEFAULT_MODEL,
                 base_url=DEFAULT_BASE_URL, session=None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()

    def chat(self, messages, temperature=0.2):
        response = self._session.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add signals/llm_client.py tests/test_llm_client.py
git commit -m "feat: add SEA-LION chat client"
```

---

### Task 8: Signal composer (LLM confirm/reject gate)

**Files:**
- Create: `signals/composer.py`
- Test: `tests/test_composer.py`

The composer builds the prompt, calls the LLM, and parses the verdict. **Fail closed:** any LLM error or unparseable response becomes a reject — an unconfirmed signal is never stored.

- [ ] **Step 1: Write the failing tests** — `tests/test_composer.py`

```python
from signals.composer import build_messages, confirm_setup, parse_confirmation
from signals.models import CandidateSetup

SETUP = CandidateSetup(
    symbol="BTCUSDT",
    direction="long",
    entry=100.0,
    stop_loss=98.0,
    take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)

HEADLINES = ["Bitcoin breaks resistance", "ETF inflows surge"]


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error
        self.last_messages = None

    def chat(self, messages, temperature=0.2):
        self.last_messages = messages
        if self._error:
            raise self._error
        return self._reply


def test_build_messages_includes_setup_and_news():
    messages = build_messages(SETUP, HEADLINES)
    assert messages[0]["role"] == "system"
    user_content = messages[1]["content"]
    assert "BTCUSDT" in user_content
    assert "long" in user_content
    assert "100.0" in user_content       # entry
    assert "98.0" in user_content        # stop loss
    assert "Bitcoin breaks resistance" in user_content


def test_build_messages_handles_no_headlines():
    messages = build_messages(SETUP, [])
    assert "No recent headlines available" in messages[1]["content"]


def test_parse_confirmation_valid_json():
    text = '{"verdict": "confirm", "confidence": 78, "rationale": "Momentum aligns."}'
    result = parse_confirmation(text)
    assert result.verdict == "confirm"
    assert result.confidence == 78
    assert result.rationale == "Momentum aligns."


def test_parse_confirmation_json_wrapped_in_prose():
    text = 'Sure! Here is my analysis:\n```json\n{"verdict": "reject", "confidence": 30, "rationale": "News is bearish."}\n```\nHope that helps.'
    result = parse_confirmation(text)
    assert result.verdict == "reject"
    assert result.confidence == 30


def test_parse_confirmation_malformed_is_reject():
    result = parse_confirmation("I think this trade looks great, go for it!")
    assert result.verdict == "reject"
    assert result.confidence == 0


def test_parse_confirmation_bad_verdict_is_reject():
    result = parse_confirmation('{"verdict": "maybe", "confidence": 50, "rationale": "hmm"}')
    assert result.verdict == "reject"


def test_parse_confirmation_clamps_confidence():
    result = parse_confirmation('{"verdict": "confirm", "confidence": 150, "rationale": "very sure"}')
    assert result.confidence == 100


def test_confirm_setup_happy_path():
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 80, "rationale": "ok"}')
    result = confirm_setup(SETUP, HEADLINES, llm)
    assert result.verdict == "confirm"
    assert llm.last_messages is not None


def test_confirm_setup_llm_error_is_reject():
    llm = FakeLLM(error=RuntimeError("HTTP 429"))
    result = confirm_setup(SETUP, HEADLINES, llm)
    assert result.verdict == "reject"
    assert result.confidence == 0
    assert "HTTP 429" in result.rationale
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_composer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.composer'`

- [ ] **Step 3: Write `signals/composer.py`**

```python
"""Builds the confirmation prompt, calls the LLM, and parses the verdict.

Fail-closed: any LLM failure or unparseable reply becomes a reject so an
unconfirmed signal is never stored.
"""
import json

from signals.models import CandidateSetup, Confirmation

SYSTEM_PROMPT = (
    "You are a disciplined trading-signal reviewer. You receive a candidate "
    "trade setup derived from technical indicators, plus recent news "
    "headlines. Decide whether the setup is worth taking.\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"verdict": "confirm" or "reject", "confidence": <integer 0-100>, '
    '"rationale": "<one short paragraph explaining your decision>"}'
)


def build_messages(setup: CandidateSetup, headlines: list) -> list:
    if headlines:
        news_block = "\n".join(f"- {h}" for h in headlines)
    else:
        news_block = "No recent headlines available."
    ind = setup.indicators
    user_content = (
        f"Candidate setup:\n"
        f"- Symbol: {setup.symbol}\n"
        f"- Direction: {setup.direction}\n"
        f"- Entry: {setup.entry}\n"
        f"- Stop loss: {setup.stop_loss}\n"
        f"- Take profit: {setup.take_profit}\n"
        f"- Indicators: EMA9={ind['ema9']:.2f}, EMA21={ind['ema21']:.2f}, "
        f"RSI={ind['rsi']:.1f}, MACD hist={ind['macd_hist']:.4f}\n\n"
        f"Recent news headlines:\n{news_block}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_confirmation(text: str) -> Confirmation:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return Confirmation("reject", 0, f"Unparseable LLM reply: {text[:200]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return Confirmation("reject", 0, f"Invalid JSON in LLM reply: {text[:200]}")
    verdict = data.get("verdict")
    if verdict not in ("confirm", "reject"):
        return Confirmation("reject", 0, f"Invalid verdict in LLM reply: {verdict!r}")
    try:
        confidence = max(0, min(100, int(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    rationale = str(data.get("rationale", ""))
    return Confirmation(verdict, confidence, rationale)


def confirm_setup(setup: CandidateSetup, headlines: list, llm) -> Confirmation:
    try:
        reply = llm.chat(build_messages(setup, headlines))
    except Exception as exc:
        return Confirmation("reject", 0, f"LLM call failed: {exc}")
    return parse_confirmation(reply)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_composer.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add signals/composer.py tests/test_composer.py
git commit -m "feat: add fail-closed LLM confirmation composer"
```

---

### Task 9: Storage layer

**Files:**
- Create: `signals/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_storage.py`

```python
import json
import sqlite3

from signals.models import CandidateSetup, Confirmation, make_signal
from signals.storage import save_signal


def _signal():
    setup = CandidateSetup(
        symbol="BTCUSDT", direction="long", entry=100.0,
        stop_loss=98.0, take_profit=104.0,
        indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
    )
    confirmation = Confirmation("confirm", 80, "Looks good.")
    return make_signal(setup, confirmation, ["headline one"])


def test_save_signal_writes_sqlite_row(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    signal = _signal()
    save_signal(signal, db_path=db, json_path=js)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM signals").fetchone()
    conn.close()
    assert row["id"] == signal.id
    assert row["symbol"] == "BTCUSDT"
    assert row["direction"] == "long"
    assert row["entry"] == 100.0
    assert row["confidence"] == 80
    assert json.loads(row["indicators"])["rsi"] == 55.0
    assert json.loads(row["news_headlines"]) == ["headline one"]


def test_save_signal_appends_to_json(tmp_path):
    db = str(tmp_path / "signals.db")
    js = str(tmp_path / "signals.json")
    first = _signal()
    second = _signal()
    save_signal(first, db_path=db, json_path=js)
    save_signal(second, db_path=db, json_path=js)

    with open(js) as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["id"] == first.id
    assert data[1]["id"] == second.id
    assert data[0]["news_headlines"] == ["headline one"]


def test_save_signal_creates_table_if_missing(tmp_path):
    db = str(tmp_path / "fresh.db")
    js = str(tmp_path / "fresh.json")
    save_signal(_signal(), db_path=db, json_path=js)
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.storage'`

- [ ] **Step 3: Write `signals/storage.py`**

```python
"""Persists confirmed signals to SQLite and an append-only JSON file."""
import json
import os
import sqlite3
from dataclasses import asdict

from signals.models import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    confidence INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    indicators TEXT NOT NULL,
    news_headlines TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def save_signal(signal: Signal, db_path: str, json_path: str) -> None:
    _save_sqlite(signal, db_path)
    _append_json(signal, json_path)


def _save_sqlite(signal: Signal, db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signal.id,
                signal.symbol,
                signal.timeframe,
                signal.direction,
                signal.entry,
                signal.stop_loss,
                signal.take_profit,
                signal.confidence,
                signal.rationale,
                json.dumps(signal.indicators),
                json.dumps(signal.news_headlines),
                signal.created_at,
            ),
        )


def _append_json(signal: Signal, json_path: str) -> None:
    records = []
    if os.path.exists(json_path):
        with open(json_path) as f:
            records = json.load(f)
    records.append(asdict(signal))
    with open(json_path, "w") as f:
        json.dump(records, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add signals/storage.py tests/test_storage.py
git commit -m "feat: add SQLite + JSON signal storage"
```

---

### Task 10: Pipeline (`run.py`)

**Files:**
- Create: `signals/run.py`
- Test: `tests/test_pipeline.py`

Wires everything together. Error policy per spec: Binance failure → retry once with backoff → skip symbol; news failure → retry once → proceed with empty headlines (news is enrichment, not a hard dependency); LLM failure → handled fail-closed inside `confirm_setup`. One symbol's failure never kills the run.

The pipeline tests mock at the network boundary (`fetch_candles`, `fetch_headlines`, the LLM client). The detector is exercised through its own unit tests (Task 4); here, `detect_setup` is patched where noted so the confirmed-signal path is deterministic without hand-tuning candle fixtures to trigger real crossovers.

- [ ] **Step 1: Write the failing tests** — `tests/test_pipeline.py`

```python
import json
import sqlite3

from signals import run as run_module
from signals.config import Config
from signals.models import Candle, CandidateSetup
from signals.run import scan_symbol, with_retry


def _flat_candles(n=200, price=100.0):
    return [
        Candle(open_time=i, open=price, high=price + 1.0,
               low=price - 1.0, close=price, volume=1.0)
        for i in range(n)
    ]


def _config(tmp_path):
    return Config(
        sealion_api_key="sk-test",
        cryptopanic_api_key="cp-test",
        db_path=str(tmp_path / "signals.db"),
        json_path=str(tmp_path / "signals.json"),
    )


SETUP = CandidateSetup(
    symbol="BTCUSDT", direction="long", entry=100.0,
    stop_loss=98.0, take_profit=104.0,
    indicators={"ema9": 101.0, "ema21": 100.0, "rsi": 55.0, "macd_hist": 0.5},
)


class FakeLLM:
    def __init__(self, reply):
        self._reply = reply

    def chat(self, messages, temperature=0.2):
        return self._reply


def test_with_retry_returns_after_transient_failure():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "ok"

    assert with_retry(flaky, delay=0.0) == "ok"
    assert len(calls) == 2


def test_with_retry_raises_after_exhausting_attempts():
    def always_fails():
        raise RuntimeError("down")

    try:
        with_retry(always_fails, delay=0.0)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_scan_symbol_no_setup_stores_nothing(tmp_path, monkeypatch):
    # Flat prices produce no crossover → real detector returns None.
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 90, "rationale": "x"}')
    result = scan_symbol("BTCUSDT", cfg, llm)
    assert result is None
    assert not (tmp_path / "signals.json").exists()


def test_scan_symbol_confirmed_signal_is_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, api_key: ["BTC rally continues"])
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 82, "rationale": "Aligned."}')

    signal = scan_symbol("BTCUSDT", cfg, llm)

    assert signal is not None
    assert signal.confidence == 82
    conn = sqlite3.connect(cfg.db_path)
    count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    assert count == 1
    with open(cfg.json_path) as f:
        data = json.load(f)
    assert data[0]["symbol"] == "BTCUSDT"
    assert data[0]["news_headlines"] == ["BTC rally continues"]


def test_scan_symbol_rejected_signal_not_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)
    monkeypatch.setattr(run_module, "fetch_headlines",
                        lambda symbol, api_key: [])
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "reject", "confidence": 25, "rationale": "Bearish news."}')

    result = scan_symbol("BTCUSDT", cfg, llm)

    assert result is None
    assert not (tmp_path / "signals.json").exists()


def test_scan_symbol_news_failure_proceeds_with_empty_headlines(tmp_path, monkeypatch):
    monkeypatch.setattr(run_module, "fetch_candles",
                        lambda symbol, interval, limit: _flat_candles())
    monkeypatch.setattr(run_module, "detect_setup",
                        lambda *args, **kwargs: SETUP)

    def broken_news(symbol, api_key):
        raise RuntimeError("cryptopanic down")

    monkeypatch.setattr(run_module, "fetch_headlines", broken_news)
    cfg = _config(tmp_path)
    llm = FakeLLM(reply='{"verdict": "confirm", "confidence": 70, "rationale": "ok"}')

    signal = scan_symbol("BTCUSDT", cfg, llm)

    assert signal is not None
    assert signal.news_headlines == []


def test_scan_symbol_binance_failure_returns_none(tmp_path, monkeypatch):
    def broken_candles(symbol, interval, limit):
        raise RuntimeError("binance down")

    monkeypatch.setattr(run_module, "fetch_candles", broken_candles)
    monkeypatch.setattr(run_module, "RETRY_DELAY", 0.0)
    cfg = _config(tmp_path)
    llm = FakeLLM(reply="{}")

    assert scan_symbol("BTCUSDT", cfg, llm) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signals.run'`

- [ ] **Step 3: Write `signals/run.py`**

```python
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


def with_retry(fn, attempts=2, delay=RETRY_DELAY):
    """Call fn; on failure wait `delay` seconds and try once more per extra attempt."""
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
            lambda: fetch_candles(symbol, cfg.timeframe, cfg.candle_limit),
            delay=RETRY_DELAY,
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
            lambda: fetch_headlines(symbol, cfg.cryptopanic_api_key),
            delay=RETRY_DELAY,
        )
    except Exception as exc:
        print(f"[{symbol}] news unavailable, proceeding without: {exc}")
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
            print(f"[{symbol}] unexpected error, skipping: {exc}")
    print(f"Done. {stored} signal(s) stored in {cfg.db_path} / {cfg.json_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (config 3, indicators 10, detector 10, binance 3, news 3, llm 3, composer 9, storage 3, pipeline 7 = 51)

- [ ] **Step 6: Commit**

```bash
git add signals/run.py tests/test_pipeline.py
git commit -m "feat: wire pipeline with retry and per-symbol error isolation"
```

---

### Task 11: README and live smoke run

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# ThinkTrade Signals Engine

AI-confirmed crypto trading signals. Scans BTCUSDT/ETHUSDT 1h candles from
Binance, derives technical setups (EMA 9/21 crossover, RSI 14, MACD, ATR),
confirms each candidate with SEA-LION using recent CryptoPanic headlines,
and stores confirmed signals in SQLite + JSON.

Part of the ThinkTrade platform rebuild. Spec:
`docs/superpowers/specs/2026-07-05-signals-engine-design.md`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in your API keys
```

Keys required:
- `SEALION_API_KEY` — https://playground.sea-lion.ai (free, Google sign-in)
- `CRYPTOPANIC_API_KEY` — https://cryptopanic.com/developers/api/keys

No Binance key needed (public market data).

## Run

```bash
.venv/bin/python -m signals.run
```

Confirmed signals are appended to `signals.json` and inserted into
`signals.db` (table `signals`). A run with no qualifying technical setup
stores nothing — that is normal; crossovers are infrequent by design.

## Tests

```bash
.venv/bin/pytest
```

## Disclaimer

Signals are for educational and analysis purposes only. Not financial
advice. Trading involves risk.
```

- [ ] **Step 2: Verify the full test suite still passes**

Run: `.venv/bin/pytest`
Expected: all tests pass

- [ ] **Step 3: Live smoke run (requires real keys in `.env`)**

If the user has provided `SEALION_API_KEY` and `CRYPTOPANIC_API_KEY` in `.env`:

Run: `.venv/bin/python -m signals.run`
Expected: per-symbol output lines; most runs print `no setup found` for both symbols (crossovers are infrequent). Any confirmed signal appears in `signals.db` and `signals.json`. If keys are missing, the script exits with the clear message from `load_config()` — report this to the user and ask them to fill in `.env` rather than treating it as a bug.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, run, and test instructions"
```

---

## Verification checklist (post-implementation)

- [ ] `.venv/bin/pytest` — full suite green
- [ ] `python -m signals.run` with missing `.env` exits with a clear key-missing message
- [ ] With real keys: script completes without traceback, prints per-symbol status
- [ ] `signals.json` / `signals.db` are git-ignored (never committed)
