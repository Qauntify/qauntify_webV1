"""Admin-configured bot settings (single row in bot_settings)."""
import requests

from signals.clients.market import canonical_symbol
from signals.models import ADMIN_SELECTABLE_STRATEGIES, BotSettings, DEFAULT_SIGNAL_STRATEGY


def fetch_bot_settings(supabase_url: str, service_key: str,
                       session=None) -> BotSettings:
    """Read the single bot_settings row; fall back to defaults on any failure.

    Settings must never break a scan, so every error path (network, missing
    table, malformed row) returns BotSettings() and logs one short line.
    """
    session = session or requests.Session()
    try:
        response = session.get(
            f"{supabase_url}/rest/v1/bot_settings"
            "?id=eq.1&select=symbols,min_alert_confidence,min_store_confidence,signal_strategy",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()
        row = rows[0]
        symbols = tuple(
            canonical_symbol(s)
            for s in row["symbols"]
            if isinstance(s, str) and s.strip()
        )
        alert_confidence = int(row["min_alert_confidence"])
        store_raw = row.get("min_store_confidence", 0)
        store_confidence = int(store_raw if store_raw is not None else 0)
        strategy = row.get("signal_strategy", DEFAULT_SIGNAL_STRATEGY)
        if strategy not in ADMIN_SELECTABLE_STRATEGIES:
            strategy = DEFAULT_SIGNAL_STRATEGY
        if not symbols or not 0 <= alert_confidence <= 100:
            raise ValueError("empty symbols or confidence out of range")
        if not 0 <= store_confidence <= 100:
            store_confidence = 0
        return BotSettings(
            symbols=symbols,
            min_alert_confidence=alert_confidence,
            min_store_confidence=store_confidence,
            signal_strategy=strategy,
        )
    except Exception as exc:
        print(f"bot_settings unavailable ({type(exc).__name__}), using defaults")
        return BotSettings()
