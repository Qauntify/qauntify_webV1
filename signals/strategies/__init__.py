"""Pluggable signal strategies — one package folder per playbook."""
from signals.strategies.router import detect_setup

__all__ = ["detect_setup"]
