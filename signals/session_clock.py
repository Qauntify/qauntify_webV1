"""FX market session clock (Asia / London / New York) in UTC.

Fixed UTC windows — traders use these widely; we skip DST shifting so the
label stays stable for the LLM without depending on country-specific rules.
"""
from datetime import datetime, timezone

# Inclusive start hour, exclusive end hour (UTC).
SESSION_WINDOWS = (
    ("Asia", 0, 9),
    ("London", 7, 16),
    ("New York", 12, 21),
)


def sessions_at(now: datetime | None = None) -> tuple[str, ...]:
    """Active major FX sessions at `now` (UTC)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    hour = now.hour + now.minute / 60.0
    active = []
    for name, start, end in SESSION_WINDOWS:
        if start <= hour < end:
            active.append(name)
    return tuple(active)


def describe_market_session(now: datetime | None = None) -> str:
    """One-line session context for the AI confirmation prompt."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    active = sessions_at(now)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    if not active:
        return f"Market session at {stamp}: off-hours (no major FX session)"
    if len(active) == 1:
        return f"Market session at {stamp}: {active[0]}"
    return (
        f"Market session at {stamp}: {' / '.join(active)} overlap "
        f"(active: {', '.join(active)})"
    )
