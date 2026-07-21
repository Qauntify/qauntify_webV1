"""Free economic calendar from Fair Economy's public ForexFactory feed.

No API key. Soft-fail at the call site if the CDN is down — same pattern
as RSS news. Source: https://nfs.faireconomy.media/ff_calendar_thisweek.json
"""
from datetime import datetime, timedelta, timezone

import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Country field on the feed is the affected currency (USD, GBP, EUR, ...).
SYMBOL_CURRENCIES = {
    "BTCUSD": ("USD",),
    "ETHUSD": ("USD",),
    "XAUUSD": ("USD",),
    "GBPUSD": ("GBP", "USD"),
    "BTCUSDT": ("USD",),
    "ETHUSDT": ("USD",),
    "PAXGUSDT": ("USD",),
    "PAXGUSD": ("USD",),
    "GBPUSDT": ("GBP", "USD"),
}

RELEVANT_IMPACTS = frozenset({"High", "Medium"})


def currencies_for_symbol(symbol: str) -> tuple[str, ...]:
    known = SYMBOL_CURRENCIES.get(symbol.upper())
    if known is not None:
        return known
    # Unknown USDT pairs default to USD macro sensitivity.
    return ("USD",)


def _parse_when(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        # Feed uses ISO-8601 with offset, e.g. 2026-07-14T08:30:00-04:00
        when = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def fetch_calendar_events(session=None) -> list[dict]:
    """Normalized events for this week. Raises on total fetch failure."""
    session = session or requests.Session()
    response = session.get(
        CALENDAR_URL,
        timeout=10,
        headers={"User-Agent": "QauntifySignals/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("economic calendar payload is not a list")

    events = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        when = _parse_when(str(row.get("date") or ""))
        if when is None:
            continue
        impact = str(row.get("impact") or "").strip()
        currency = str(row.get("country") or "").strip().upper()
        title = str(row.get("title") or "").strip()
        if not title or not currency:
            continue
        events.append({
            "title": title,
            "currency": currency,
            "impact": impact,
            "when": when,
            "forecast": str(row.get("forecast") or "").strip(),
            "previous": str(row.get("previous") or "").strip(),
            "actual": str(row.get("actual") or "").strip(),
        })
    events.sort(key=lambda e: e["when"])
    return events


def filter_events_for_symbol(
    events: list[dict],
    symbol: str,
    *,
    now: datetime | None = None,
    past_hours: float = 6,
    ahead_hours: float = 24,
) -> list[dict]:
    """High/Medium events for this symbol's currencies in a nearby window."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    currencies = set(currencies_for_symbol(symbol))
    start = now - timedelta(hours=past_hours)
    end = now + timedelta(hours=ahead_hours)
    out = []
    for event in events:
        if event["impact"] not in RELEVANT_IMPACTS:
            continue
        if event["currency"] not in currencies:
            continue
        when = event["when"]
        if when < start or when > end:
            continue
        out.append(event)
    return out


def format_event_line(event: dict) -> str:
    when = event["when"].strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        when,
        event["currency"],
        event["impact"],
        event["title"],
    ]
    extras = []
    if event.get("forecast"):
        extras.append(f"forecast {event['forecast']}")
    if event.get("previous"):
        extras.append(f"previous {event['previous']}")
    if event.get("actual"):
        extras.append(f"actual {event['actual']}")
    line = " | ".join(parts)
    if extras:
        line += " | " + ", ".join(extras)
    return line


def calendar_block_for_symbol(
    events: list[dict],
    symbol: str,
    *,
    now: datetime | None = None,
) -> str:
    filtered = filter_events_for_symbol(events, symbol, now=now)
    if not filtered:
        return (
            "No nearby high/medium-impact economic events for this symbol's "
            "currencies in the next 24h / past 6h."
        )
    lines = [format_event_line(e) for e in filtered]
    return "\n".join(f"- {line}" for line in lines)
