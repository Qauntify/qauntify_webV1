"""Signal CRUD / queries against the `signals` table (Supabase PostgREST)."""
from dataclasses import asdict
from urllib.parse import quote

import requests

from signals.models import Signal


def save_signal(signal: Signal, supabase_url: str, service_key: str,
                session=None, *, shadow: bool = False,
                experiment: str | None = None) -> None:
    """Insert one signal row; raises on any failure so the caller can retry.

    `shadow=True` means "record but never deliver" — it is the containment
    flag every user-facing read path filters on. `experiment` names WHICH study
    the row belongs to ("gate_ab", "sr_limit"), so unrelated trials are never
    pooled together in analysis. Ordinary delivered signals leave both unset.
    """
    session = session or requests.Session()
    payload = asdict(signal)
    # Mirror TP1 into take_profit_1 for the multi-TP schema while keeping
    # legacy `take_profit` populated for older readers.
    payload["take_profit_1"] = signal.take_profit
    payload["shadow"] = shadow
    payload["experiment"] = experiment
    response = session.post(
        f"{supabase_url}/rest/v1/signals",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()


def list_open_signals(supabase_url: str, service_key: str, session=None):
    """Signals still needing outcome polling (open / tp1 / tp2), oldest first."""
    session = session or requests.Session()
    page_size = 1000
    offset = 0
    rows: list = []
    while True:
        response = session.get(
            f"{supabase_url}/rest/v1/signals"
            "?status=in.(open,tp1_hit,tp2_hit)"
            "&closed_at=is.null"
            # `indicators` carries entry_style, which decides whether the
            # outcome tracker counts the bar the order filled on.
            "&select=id,symbol,timeframe,direction,entry,stop_loss,"
            "take_profit,take_profit_1,take_profit_2,take_profit_3,"
            "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,chart_data,"
            "indicators"
            "&order=created_at.asc",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Range": f"{offset}-{offset + page_size - 1}",
                "Prefer": "count=exact",
            },
            timeout=15,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def list_signals_missing_outcome_chart(supabase_url: str, service_key: str,
                                       limit: int = 20, session=None):
    """Closed rows with no outcome_chart_url yet, most recently closed first.

    Backfill target for realtime-closed rows (e.g. via the MT5/Vercel path,
    which never renders a chart) and for any row whose chart attach failed
    at close time in the normal cron path.
    """
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?closed_at=not.is.null"
        "&outcome_chart_url=is.null"
        "&select=id,symbol,timeframe,direction,entry,stop_loss,"
        "take_profit,take_profit_1,take_profit_2,take_profit_3,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at,status,created_at,closed_at,"
        "indicators"
        f"&order=closed_at.desc&limit={limit}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def open_symbols_for_timeframe(symbols, timeframe: str, supabase_url: str,
                               service_key: str, session=None) -> set:
    """Symbols that already have a non-terminal signal on `timeframe`."""
    if not symbols:
        return set()
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?status=in.(open,tp1_hit,tp2_hit)&closed_at=is.null"
        f"&timeframe=eq.{timeframe}"
        f"&symbol=in.({symbols_filter})&shadow=is.false&select=symbol",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return {row["symbol"] for row in response.json()}


def close_signal(signal_id: str, status: str, closed_at: str,
                 supabase_url: str, service_key: str, session=None) -> None:
    """Mark one signal terminal (tp_hit/tp3_hit/sl_hit/expired)."""
    update_signal_outcome(
        signal_id, status, closed_at, supabase_url, service_key,
        terminal=True, session=session,
    )


def update_signal_outcome(signal_id: str, status: str, at: str,
                          supabase_url: str, service_key: str, *,
                          terminal: bool, expected_status: str | None = None,
                          session=None) -> bool | None:
    """PATCH status (+ optional tpN_hit_at / closed_at).

    tp1_hit / tp2_hit can be intermediate (still open) or terminal (TP banked
    then froze with closed_at). Only stamp the first-hit timestamp when the
    trade is still advancing — a terminal freeze must not overwrite it.

    `expected_status` makes the PATCH a conditional claim (mirrors
    try_acquire_engine_lock's conditional-PATCH pattern): it only applies if
    the row is still in that status, so two writers racing on the same row
    (the slow cron and the realtime watcher) can't both "win" and double-fire
    Telegram. Returns True/False (claimed or not) when given, else None
    (existing unconditional behavior, unchanged).
    """
    session = session or requests.Session()
    payload: dict = {"status": status}
    if status == "tp1_hit" and not terminal:
        payload["tp1_hit_at"] = at
    elif status == "tp2_hit" and not terminal:
        payload["tp2_hit_at"] = at
    elif status in ("tp3_hit", "tp_hit"):
        payload["tp3_hit_at"] = at
        # Legacy tp_hit also stamps closed_at.
        terminal = True
    if terminal:
        payload["closed_at"] = at

    url = f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}"
    prefer = "return=minimal"
    if expected_status is not None:
        url += f"&status=eq.{expected_status}"
        prefer = "return=representation"

    response = session.patch(
        url,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    if expected_status is not None:
        return bool(response.json())
    return None


def set_outcome_chart_url(signal_id: str, url: str, supabase_url: str,
                          service_key: str, session=None) -> None:
    """PATCH just the outcome_chart_url on one signal row."""
    session = session or requests.Session()
    response = session.patch(
        f"{supabase_url}/rest/v1/signals?id=eq.{signal_id}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"outcome_chart_url": url},
        timeout=15,
    )
    response.raise_for_status()


def latest_signal(symbol: str, supabase_url: str, service_key: str,
                  timeframe: str | None = None, session=None):
    """Newest stored signal for `symbol` as {"direction", "created_at"},
    or None when the symbol has no signals. `timeframe` scopes the lookup
    to one session's stream so scalp and swing never dedup each other.
    Raises on any failure."""
    session = session or requests.Session()
    timeframe_filter = f"&timeframe=eq.{timeframe}" if timeframe else ""
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{symbol}{timeframe_filter}&shadow=is.false"
        "&select=direction,created_at"
        "&order=created_at.desc&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def latest_signals_since(symbols, timeframe: str, since: str,
                         supabase_url: str, service_key: str,
                         session=None) -> dict:
    """{"direction", "created_at"} of the newest signal for each symbol in
    `symbols` at `timeframe`, restricted to rows at/after `since` — the
    only rows a dedup check ever needs. One query replaces what would
    otherwise be one `latest_signal` call per symbol. Symbols with no
    qualifying row are absent from the result. Raises on any failure."""
    if not symbols:
        return {}
    session = session or requests.Session()
    symbols_filter = ",".join(symbols)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=in.({symbols_filter})&timeframe=eq.{timeframe}"
        f"&created_at=gte.{quote(since, safe='')}&shadow=is.false"
        "&select=symbol,direction,created_at&order=symbol.asc,created_at.desc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    latest: dict = {}
    for row in response.json():
        latest.setdefault(row["symbol"], row)
    return latest


def list_closed_signals(supabase_url: str, service_key: str, session=None,
                        *, include_shadow: bool = False):
    """Every signal that has reached a terminal status (tp_hit/sl_hit/
    expired), for calibration reporting — win rate and expectancy can only
    be computed once an outcome is known. Raises on any failure.

    Shadow rows (LLM-rejected setups recorded for the gate A/B) are excluded by
    default, so existing calibration reporting is unaffected by them. The gate
    report passes `include_shadow=True` because it needs both arms.
    """
    session = session or requests.Session()
    shadow_filter = "" if include_shadow else "&shadow=is.false"
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        "?or=(status.in.(tp_hit,tp3_hit,sl_hit,expired),"
        "and(status.in.(tp1_hit,tp2_hit),closed_at.not.is.null))"
        f"{shadow_filter}"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "take_profit_1,take_profit_2,take_profit_3,confidence,indicators,"
        "status,created_at,closed_at,shadow,experiment,"
        "tp1_hit_at,tp2_hit_at,tp3_hit_at"
        "&order=created_at.asc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def open_signals_same_direction(symbol: str, direction: str, *,
                                exclude_strategy: str,
                                supabase_url: str, service_key: str,
                                session=None) -> list:
    """Open (non-shadow) signals for `symbol`+`direction` from a strategy
    other than `exclude_strategy` -- the confluence pass's "does an
    independent strategy already agree" check.

    `timeframe=neq.confluence` keeps an already-published confluence row
    from ever counting toward a later confluence check (no chaining). The
    strategy filter itself happens in Python: PostgREST can't easily filter
    JSONB `indicators->>strategy` alongside these other conditions in one
    readable query here.
    """
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{quote(symbol)}&direction=eq.{quote(direction)}"
        "&status=in.(open,tp1_hit,tp2_hit)&shadow=is.false"
        "&timeframe=neq.confluence"
        "&select=timeframe,indicators"
        "&order=created_at.desc",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return [
        row for row in rows
        if (row.get("indicators") or {}).get("strategy") != exclude_strategy
    ]


def has_open_confluence_signal(symbol: str, supabase_url: str,
                               service_key: str, session=None) -> bool:
    """Whether `symbol` already has an open confluence signal -- guards
    against publishing a second one while the first is still live."""
    session = session or requests.Session()
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{quote(symbol)}&timeframe=eq.confluence"
        "&status=in.(open,tp1_hit,tp2_hit)&shadow=is.false"
        "&select=id&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    response.raise_for_status()
    return bool(response.json())
