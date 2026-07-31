"""BBMA (Bollinger Bands + Moving Average) — two setups from the Oma Ally
playbook, registered as separate strategies because they are opposite trades:
`extreme` fades a move, `reentry` follows it.
"""
from signals.strategies.bbma.extreme import detect_setup as detect_extreme
from signals.strategies.bbma.reentry import detect_setup as detect_reentry

__all__ = ["detect_extreme", "detect_reentry"]
