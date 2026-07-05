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
