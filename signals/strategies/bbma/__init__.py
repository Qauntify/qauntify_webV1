"""BBMA (Bollinger Bands + Moving Average) — Oma Ally playbook.

Standalone detectors (`extreme`, `reentry`) plus taught MTF doctrine in
`taught` (H4 Mid+EMA50 bias, H1 re-entry primary, Extreme→MHV secondary).
"""
from signals.strategies.bbma.extreme import detect_setup as detect_extreme
from signals.strategies.bbma.reentry import detect_setup as detect_reentry
from signals.strategies.bbma.taught import detect_setup as detect_taught

__all__ = ["detect_extreme", "detect_reentry", "detect_taught"]
