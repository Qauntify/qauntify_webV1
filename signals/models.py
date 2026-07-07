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
    confidence: int | None = None


@dataclass(frozen=True)
class BotSettings:
    """Engine behavior controlled from the /admin page (bot_settings table)."""
    symbols: tuple = ("BTCUSDT", "ETHUSDT", "PAXGUSDT", "GBPUSDT")
    min_alert_confidence: int = 0  # gates Telegram alerts only, not storage


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


@dataclass(frozen=True)
class ScanResult:
    signal: Signal | None = None
    no_signal: NoSignalReport | None = None


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
