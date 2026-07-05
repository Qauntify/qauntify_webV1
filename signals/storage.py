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
    conn = sqlite3.connect(db_path)
    try:
        with conn:
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
    finally:
        conn.close()


def _append_json(signal: Signal, json_path: str) -> None:
    records = []
    if os.path.exists(json_path):
        try:
            with open(json_path) as f:
                records = json.load(f)
        except (json.JSONDecodeError, ValueError):
            records = []  # unreadable mirror file: start fresh, SQLite stays authoritative
        if not isinstance(records, list):
            records = []
    records.append(asdict(signal))
    with open(json_path, "w") as f:
        json.dump(records, f, indent=2)
