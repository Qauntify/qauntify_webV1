"""Read-only verification helpers for historical replay execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ml.data.validate_dataset import TIMEFRAME_SECONDS
from ml.replay.candidate_builder import signal_reason
from ml.replay.replay_engine import StrategyConfig, frame_to_candles
from ml.replay.strategy_adapter import PrefixView, calculate_causal_indicators, evaluate_strategy
from signals.backtest import htf_trend_series
from signals.strategies import detect_setup as production_detect_setup


@dataclass(frozen=True)
class ParityResult:
    strategy: str
    timeframe: str
    evaluations: int
    candidates: int
    mismatches: int
    mismatch_samples: tuple[dict, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def verify_production_parity(frame, strategy: StrategyConfig, *, htf_frame=None) -> ParityResult:
    """Compare the replay adapter and production router on identical prefixes."""
    candles = frame_to_candles(frame)
    indicators = calculate_causal_indicators(candles)
    trends = [None] * len(candles)
    if strategy.confluence_timeframe:
        if htf_frame is None or htf_frame.empty:
            raise ValueError("Parity verification requires confluence candles")
        htf_seconds = TIMEFRAME_SECONDS[strategy.confluence_timeframe]
        trends = htf_trend_series(
            candles, frame_to_candles(htf_frame), htf_seconds // 60,
        )

    mismatches = []
    candidates = evaluations = 0
    for index in range(strategy.minimum_history - 1, len(candles)):
        history = PrefixView(candles, index + 1)
        replay_setup = evaluate_strategy(
            strategy.name,
            str(frame.iloc[index]["symbol"]),
            history,
            indicators,
            htf_trend=trends[index],
        )
        ema9, ema21, rsi14, macd_hist, atr14, adx14 = indicators.through(index + 1)
        production_setup = production_detect_setup(
            strategy.name,
            str(frame.iloc[index]["symbol"]),
            history,
            ema9,
            ema21,
            rsi14,
            macd_hist,
            atr14,
            adx14=adx14,
            htf_trend=trends[index],
            h1_candles=None,
        )
        evaluations += 1
        if replay_setup is not None:
            candidates += 1
        if replay_setup != production_setup:
            mismatches.append({
                "source_candle_timestamp": frame.iloc[index]["timestamp"].isoformat(),
                "replay": _setup_summary(replay_setup),
                "production": _setup_summary(production_setup),
            })
    return ParityResult(
        strategy=strategy.name,
        timeframe=strategy.timeframe,
        evaluations=evaluations,
        candidates=candidates,
        mismatches=len(mismatches),
        mismatch_samples=tuple(mismatches[:10]),
    )


def _setup_summary(setup) -> dict | None:
    if setup is None:
        return None
    tp1, tp2, tp3 = setup.resolved_take_profits()
    return {
        "strategy": setup.indicators.get("strategy") or "ema_cross",
        "direction": setup.direction,
        "entry": setup.entry,
        "stop_loss": setup.stop_loss,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
        "signal_reason": signal_reason(setup.indicators),
    }
