"""Causal feature calculation reusing production indicators and detectors."""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_SCHEMA_VERSION, validate_feature
from ml.replay.strategy_adapter import PrefixView, evaluate_strategy
from signals.session_clock import sessions_at
from signals.strategies.ict_fvg.detector import find_bearish_fvg, find_bullish_fvg
from signals.strategies.ict_smc.detector import pivot_highs, pivot_lows
from signals.strategies.sr_zone.detector import _cluster_zones


def _value(candidate, name):
    return candidate[name] if isinstance(candidate, Mapping) else getattr(candidate, name)


def _finite(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _safe_div(numerator, denominator):
    return _finite(numerator / denominator) if denominator else None


def _latest_fvg(window, bullish):
    finder = find_bullish_fvg if bullish else find_bearish_fvg
    return finder(window, max(2, len(window) - 20), len(window) - 1)


def _nearest_zone(zones, close, support):
    eligible = [zone for zone in zones if zone["high"] <= close] if support else [zone for zone in zones if zone["low"] >= close]
    if not eligible:
        return None
    return max(eligible, key=lambda z: z["high"]) if support else min(eligible, key=lambda z: z["low"])


def calculate_feature_row(
    candidate, *, candles, indicators, index: int, htf_trend: str | None,
    config, candidate_manifest: dict, candle_manifest: dict,
) -> dict:
    """Calculate one row from candles[0:index+1], never from a future candle."""
    history = PrefixView(candles, index + 1)
    bar = history[-1]
    atr_value = _finite(indicators.atr14[index])
    if atr_value is None or atr_value <= 0:
        raise ValueError(f"Candidate {_value(candidate, 'candidate_id')} lacks causal ATR")
    close = float(bar.close)
    risk = abs(float(_value(candidate, "entry_price")) - float(_value(candidate, "stop_loss")))
    if risk <= 0:
        raise ValueError("Candidate risk must be positive")

    # Detector replay is a parity assertion and supplies exact strategy context.
    setup = evaluate_strategy(
        str(_value(candidate, "strategy_name")), str(_value(candidate, "symbol")),
        history, indicators, htf_trend=htf_trend,
    )
    if setup is None or setup.direction != _value(candidate, "direction"):
        raise ValueError(f"Production detector parity failed for {_value(candidate, 'candidate_id')}")
    if abs(float(setup.entry) - float(_value(candidate, "entry_price"))) > 1e-8 or abs(float(setup.stop_loss) - float(_value(candidate, "stop_loss"))) > 1e-8:
        raise ValueError(f"Production detector geometry drift for {_value(candidate, 'candidate_id')}")

    window = list(history[-config.structure_lookback:])
    range_window = list(history[-config.range_lookback:])
    closes = np.asarray([c.close for c in history[-max(config.volatility_lookback + 1, 6):]], dtype="float64")
    returns = np.diff(closes) / closes[:-1]
    recent_high = max(c.high for c in range_window)
    recent_low = min(c.low for c in range_window)
    price_range = recent_high - recent_low
    pivots_high = pivot_highs(window)
    pivots_low = pivot_lows(window)
    support_zones = _cluster_zones(window, pivots_low, "low", atr_value)
    resistance_zones = _cluster_zones(window, pivots_high, "high", atr_value)
    support = _nearest_zone(support_zones, close, True)
    resistance = _nearest_zone(resistance_zones, close, False)
    bull_fvg = _latest_fvg(window[-config.fvg_lookback:], True)
    bear_fvg = _latest_fvg(window[-config.fvg_lookback:], False)

    def fvg_values(fvg, bullish):
        if fvg is None:
            return (None, None, None)
        fvg_i, bottom, top = fvg
        boundary = top if bullish else bottom
        return ((top - bottom) / atr_value, (close - boundary) / atr_value, len(window[-config.fvg_lookback:]) - 1 - fvg_i)

    bull_width, bull_distance, bull_age = fvg_values(bull_fvg, True)
    bear_width, bear_distance, bear_age = fvg_values(bear_fvg, False)
    ema9 = _finite(indicators.ema9[index]); ema21 = _finite(indicators.ema21[index])
    rsi14 = _finite(indicators.rsi14[index]); macd = _finite(indicators.macd_hist[index]); adx14 = _finite(indicators.adx14[index])
    trend = "up" if ema9 > ema21 else "down" if ema9 < ema21 else "flat"
    source_time = pd.Timestamp(_value(candidate, "source_candle_timestamp"))
    source_time = source_time.tz_convert("UTC") if source_time.tz else source_time.tz_localize("UTC")
    decision_time = pd.Timestamp(_value(candidate, "candidate_timestamp"))
    decision_time = decision_time.tz_convert("UTC") if decision_time.tz else decision_time.tz_localize("UTC")
    active_sessions = sessions_at(decision_time.to_pydatetime())
    hour = decision_time.hour + decision_time.minute / 60
    dow = decision_time.dayofweek
    detector = setup.indicators

    strategy_sweep = detector.get("sweep_low", detector.get("sweep_high"))
    strategy_choch = detector.get("choch_level")
    strategy_fvg_bottom = detector.get("fvg_bottom")
    strategy_fvg_top = detector.get("fvg_top")
    zone_low = detector.get("zone_low"); zone_high = detector.get("zone_high")
    zone_near = zone_high if detector.get("side") == "support" else zone_low

    row = {
        "candidate_id": str(_value(candidate, "candidate_id")),
        "candidate_timestamp": decision_time.isoformat(), "source_candle_timestamp": source_time.isoformat(),
        "symbol": str(_value(candidate, "symbol")), "strategy_name": str(_value(candidate, "strategy_name")),
        "timeframe": str(_value(candidate, "timeframe")), "direction": str(_value(candidate, "direction")),
        "feature_policy_version": FEATURE_SCHEMA_VERSION,
        "entry_price": float(_value(candidate, "entry_price")), "risk_distance": risk,
        "risk_atr": risk / atr_value,
        "tp1_r": abs(float(_value(candidate, "take_profit_1")) - close) / risk,
        "tp2_r": abs(float(_value(candidate, "take_profit_2")) - close) / risk,
        "tp3_r": abs(float(_value(candidate, "take_profit_3")) - close) / risk,
        "close": close, "ema9": ema9, "ema21": ema21, "ema_gap_atr": (ema9 - ema21) / atr_value,
        "close_ema9_atr": (close - ema9) / atr_value, "close_ema21_atr": (close - ema21) / atr_value,
        "atr14": atr_value, "atr_pct": atr_value / close, "rsi14": rsi14,
        "macd_hist": macd, "macd_hist_atr": _safe_div(macd, atr_value), "adx14": adx14,
        "return_1": float(returns[-1]), "return_5": close / closes[-6] - 1 if len(closes) >= 6 else None,
        "volatility_20": float(np.std(returns[-config.volatility_lookback:], ddof=0)),
        "range_20_atr": price_range / atr_value, "range_position_20": _safe_div(close - recent_low, price_range),
        "candle_range_atr": (bar.high - bar.low) / atr_value, "body_atr": abs(bar.close - bar.open) / atr_value,
        "upper_wick_atr": (bar.high - max(bar.open, bar.close)) / atr_value,
        "lower_wick_atr": (min(bar.open, bar.close) - bar.low) / atr_value,
        "hour_utc": hour, "day_of_week": dow, "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24), "dow_sin": math.sin(2 * math.pi * dow / 7),
        "dow_cos": math.cos(2 * math.pi * dow / 7),
        "bull_fvg_width_atr": bull_width, "bull_fvg_distance_atr": bull_distance, "bull_fvg_age": bull_age,
        "bear_fvg_width_atr": bear_width, "bear_fvg_distance_atr": bear_distance, "bear_fvg_age": bear_age,
        "support_distance_atr": (close - support["high"]) / atr_value if support else None,
        "support_width_atr": (support["high"] - support["low"]) / atr_value if support else None,
        "support_touches": support["touches"] if support else None,
        "resistance_distance_atr": (resistance["low"] - close) / atr_value if resistance else None,
        "resistance_width_atr": (resistance["high"] - resistance["low"]) / atr_value if resistance else None,
        "resistance_touches": resistance["touches"] if resistance else None,
        "pivot_high_count": len(pivots_high), "pivot_low_count": len(pivots_low),
        "distance_recent_high_atr": (recent_high - close) / atr_value,
        "distance_recent_low_atr": (close - recent_low) / atr_value,
        "strategy_sweep_distance_atr": abs(close - float(strategy_sweep)) / atr_value if strategy_sweep is not None else None,
        "strategy_choch_distance_atr": abs(close - float(strategy_choch)) / atr_value if strategy_choch is not None else None,
        "strategy_fvg_width_atr": (float(strategy_fvg_top) - float(strategy_fvg_bottom)) / atr_value if strategy_fvg_bottom is not None and strategy_fvg_top is not None else None,
        "strategy_zone_width_atr": (float(zone_high) - float(zone_low)) / atr_value if zone_low is not None and zone_high is not None else None,
        "strategy_zone_distance_atr": abs(close - float(zone_near)) / atr_value if zone_near is not None else None,
        "strategy_zone_touches": detector.get("touches"),
        "trend_up": trend == "up", "trend_down": trend == "down",
        "session_asia": "Asia" in active_sessions, "session_london": "London" in active_sessions,
        "session_new_york": "New York" in active_sessions, "session_overlap": len(active_sessions) > 1,
        "at_recent_high": close >= recent_high, "at_recent_low": close <= recent_low,
        "trend_direction": trend, "htf_trend": htf_trend or "unknown",
        "strategy_structure": str(detector.get("structure", "none")),
        "strategy_zone_side": str(detector.get("side", "none")),
        "candidate_dataset_id": candidate_manifest["candidate_dataset_id"],
        "candidate_dataset_checksum": candidate_manifest["checksum"],
        "source_dataset_id": candle_manifest["dataset_id"], "source_dataset_checksum": candle_manifest["checksum"],
        "source_commit": candidate_manifest.get("source_commit"), "schema_version": FEATURE_SCHEMA_VERSION,
    }
    validate_feature(row)
    return row
