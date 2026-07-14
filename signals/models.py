"""Core data types for the signals engine."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


# Staged take-profit R-multiples off |entry - stop|.
TP1_R = 1.0
TP2_R = 2.0
TP3_R = 3.0
# Super-scalp (5m ICT+FVG): shorter targets for quicker exits.
SUPER_SCALP_TP1_R = 0.5
SUPER_SCALP_TP2_R = 1.0
SUPER_SCALP_TP3_R = 1.5


def take_profits_from_risk(
    entry: float,
    stop: float,
    direction: str,
    *,
    r1: float = TP1_R,
    r2: float = TP2_R,
    r3: float = TP3_R,
) -> tuple[float, float, float]:
    """TP1/TP2/TP3 prices for a long or short given entry and stop."""
    risk = abs(entry - stop)
    if direction == "long":
        return (
            entry + r1 * risk,
            entry + r2 * risk,
            entry + r3 * risk,
        )
    return (
        entry - r1 * risk,
        entry - r2 * risk,
        entry - r3 * risk,
    )


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
    take_profit: float  # TP1 — kept name for call-site compatibility
    indicators: dict
    take_profit_2: float | None = None
    take_profit_3: float | None = None

    @property
    def take_profit_1(self) -> float:
        return self.take_profit

    def resolved_take_profits(self) -> tuple[float, float, float]:
        """Fill missing TP2/TP3 from R-multiples when a detector only set TP1."""
        if self.take_profit_2 is not None and self.take_profit_3 is not None:
            return self.take_profit, self.take_profit_2, self.take_profit_3
        tp1, tp2, tp3 = take_profits_from_risk(
            self.entry, self.stop_loss, self.direction,
        )
        return (
            self.take_profit,
            self.take_profit_2 if self.take_profit_2 is not None else tp2,
            self.take_profit_3 if self.take_profit_3 is not None else tp3,
        )


@dataclass(frozen=True)
class Confirmation:
    verdict: str  # "confirm" | "reject"
    confidence: int  # 0-100
    rationale: str


@dataclass(frozen=True)
class NoSignalReport:
    """AI explanation for a scan that produced no stored signal."""
    symbol: str
    timeframe: str
    kind: str  # "no_setup" | "rejected"
    rationale: str
    indicators: dict
    direction: str | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    take_profit_2: float | None = None
    take_profit_3: float | None = None
    confidence: int | None = None


SIGNAL_STRATEGIES = ("ema_cross", "ict_smc", "ce_lwma", "ict_fvg")
DEFAULT_SIGNAL_STRATEGY = "ema_cross"

TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60}

# Terminal win statuses (legacy tp_hit + multi-TP final).
WIN_STATUSES = frozenset({"tp_hit", "tp3_hit"})
# Still polled by the outcome tracker.
OPEN_POLL_STATUSES = frozenset({"open", "tp1_hit", "tp2_hit"})


@dataclass(frozen=True)
class TradingSession:
    """One signal stream: a name, the timeframe it scans, and how long its
    signals stay meaningful before expiring."""
    name: str        # "scalp" | "swing"
    timeframe: str   # Binance kline interval
    max_open_days: int
    # When set, a setup on this session's timeframe only fires if it agrees
    # with the EMA9/21 trend direction on this higher timeframe — a faster
    # session confirming against a slower one, to cut whipsaws that go
    # against the larger trend. None skips the check (no slower reference).
    confluence_timeframe: str | None = None
    # When set, this session always uses this strategy (ignores admin toggle).
    strategy: str | None = None


# Super scalp = 5m ICT+FVG (tight R); scalp = 15m CE+LWMA; swing = admin strategy.
TRADING_SESSIONS = (
    TradingSession(
        name="super_scalp", timeframe="5m", max_open_days=1,
        confluence_timeframe="15m", strategy="ict_fvg",
    ),
    TradingSession(
        name="scalp", timeframe="15m", max_open_days=2,
        confluence_timeframe=None, strategy="ce_lwma",
    ),
    TradingSession(
        name="swing", timeframe="1h", max_open_days=14,
        confluence_timeframe="4h",
    ),
)


@dataclass(frozen=True)
class BotSettings:
    """Engine behavior controlled from the /admin page (bot_settings table)."""
    symbols: tuple = ("BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT")
    min_alert_confidence: int = 0  # Telegram floor only
    min_store_confidence: int = 0  # storage floor for LLM confirms
    signal_strategy: str = DEFAULT_SIGNAL_STRATEGY


@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    timeframe: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float  # TP1 (also written as take_profit for legacy column)
    confidence: int
    rationale: str
    indicators: dict
    news_headlines: list
    created_at: str
    take_profit_2: float | None = None
    take_profit_3: float | None = None

    @property
    def take_profit_1(self) -> float:
        return self.take_profit


@dataclass(frozen=True)
class ScanResult:
    signal: Signal | None = None
    no_signal: NoSignalReport | None = None
    # Closed candles the scan fetched, reused by the outcome tracker so the
    # same symbol isn't fetched twice per run. None when the fetch failed.
    candles: list | None = None


def make_signal(setup: CandidateSetup, confirmation: Confirmation,
                headlines: list, timeframe: str = "1h") -> Signal:
    tp1, tp2, tp3 = setup.resolved_take_profits()
    return Signal(
        id=str(uuid.uuid4()),
        symbol=setup.symbol,
        timeframe=timeframe,
        direction=setup.direction,
        entry=setup.entry,
        stop_loss=setup.stop_loss,
        take_profit=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        confidence=confirmation.confidence,
        rationale=confirmation.rationale,
        indicators=setup.indicators,
        news_headlines=list(headlines),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
