"""Hybrid RAG retrieval for the SEA-LION confirm step.

Outcomes + prior rationales: SQL filters on existing tables.
Playbook: pgvector match when seeded; in-repo keyword fallback otherwise.
Soft-fails to an empty / partial block so RAG never blocks a scan.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from signals.rag.format import (
    OUTCOME_LIMIT,
    PLAYBOOK_LIMIT,
    RATIONALE_LIMIT,
    format_rag_block,
)
from signals.rag.playbook import PLAYBOOK_CHUNKS

OUTCOME_LOOKBACK_DAYS = 90
RATIONALE_LOOKBACK_DAYS = 14
CLOSED_STATUSES = (
    "tp_hit", "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "expired",
)


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def fetch_similar_outcomes(
    symbol: str,
    timeframe: str,
    direction: str,
    strategy: str,
    supabase_url: str,
    service_key: str,
    *,
    session=None,
    limit: int = OUTCOME_LIMIT,
) -> list:
    """Closed signals same symbol/TF/direction; prefer matching strategy."""
    session = session or requests.Session()
    since = _iso_days_ago(OUTCOME_LOOKBACK_DAYS)
    statuses = ",".join(CLOSED_STATUSES)
    response = session.get(
        f"{supabase_url}/rest/v1/signals"
        f"?symbol=eq.{quote(symbol)}"
        f"&timeframe=eq.{quote(timeframe)}"
        f"&direction=eq.{quote(direction)}"
        f"&status=in.({statuses})"
        f"&created_at=gte.{since}"
        "&select=symbol,timeframe,direction,entry,stop_loss,take_profit,"
        "confidence,indicators,status,created_at,closed_at"
        "&order=created_at.desc"
        "&limit=12",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=5,
    )
    response.raise_for_status()
    rows = response.json()
    preferred = []
    other = []
    for row in rows:
        indicators = row.get("indicators") or {}
        strat = indicators.get("strategy") if isinstance(indicators, dict) else None
        if strat == strategy:
            preferred.append(row)
        else:
            other.append(row)
    return (preferred + other)[:limit]


def fetch_similar_rationales(
    symbol: str,
    timeframe: str,
    direction: str,
    supabase_url: str,
    service_key: str,
    *,
    session=None,
    limit: int = RATIONALE_LIMIT,
) -> list:
    session = session or requests.Session()
    since = _iso_days_ago(RATIONALE_LOOKBACK_DAYS)
    response = session.get(
        f"{supabase_url}/rest/v1/ai_events"
        f"?symbol=eq.{quote(symbol)}"
        f"&timeframe=eq.{quote(timeframe)}"
        f"&direction=eq.{quote(direction)}"
        f"&kind=in.(confirm,reject)"
        f"&created_at=gte.{since}"
        "&select=kind,confidence,rationale,created_at"
        "&order=created_at.desc"
        f"&limit={int(limit)}",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def match_playbook_chunks(
    query_embedding: list,
    strategy: str,
    supabase_url: str,
    service_key: str,
    *,
    session=None,
    limit: int = PLAYBOOK_LIMIT,
) -> list:
    """RPC vector search; raises if extension/table/rpc missing."""
    session = session or requests.Session()
    response = session.post(
        f"{supabase_url}/rest/v1/rpc/match_playbook_chunks",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        json={
            "query_embedding": query_embedding,
            "match_strategy": strategy,
            "match_count": int(limit),
        },
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def local_playbook_chunks(strategy: str, query: str,
                          limit: int = PLAYBOOK_LIMIT) -> list:
    """Keyword fallback over in-repo playbook (no network)."""
    tokens = {t for t in query.lower().replace("/", " ").split() if len(t) > 2}
    scored = []
    for chunk in PLAYBOOK_CHUNKS:
        if chunk["strategy"] != strategy:
            continue
        text = f"{chunk['title']} {chunk['body']}".lower()
        score = sum(1 for t in tokens if t in text)
        # Prefer confirm-gate chunks so the reviewer sees approval cues first.
        if "confirm" in chunk["title"].lower():
            score += 2
        scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [c for _, c in scored[:limit]]


def _playbook_query(setup, strategy: str, timeframe: str) -> str:
    return (
        f"{strategy} {timeframe} {setup.direction} "
        f"confirm risk reward stop take profit"
    )


def retrieve_context(
    setup,
    *,
    strategy: str,
    timeframe: str,
    supabase_url: str,
    service_key: str,
    llm=None,
    session=None,
) -> str:
    """Build the RAG prompt block; soft-fail each bucket independently."""
    outcomes: list = []
    rationales: list = []
    playbook: list = []

    try:
        outcomes = fetch_similar_outcomes(
            setup.symbol, timeframe, setup.direction, strategy,
            supabase_url, service_key, session=session,
        )
    except Exception as exc:
        print(f"[{setup.symbol}] RAG outcomes unavailable ({type(exc).__name__})")

    try:
        rationales = fetch_similar_rationales(
            setup.symbol, timeframe, setup.direction,
            supabase_url, service_key, session=session,
        )
    except Exception as exc:
        print(f"[{setup.symbol}] RAG rationales unavailable ({type(exc).__name__})")

    query = _playbook_query(setup, strategy, timeframe)
    try:
        if llm is not None and hasattr(llm, "embed"):
            embedding = llm.embed(query)
            playbook = match_playbook_chunks(
                embedding, strategy, supabase_url, service_key, session=session,
            )
    except Exception as exc:
        print(f"[{setup.symbol}] RAG playbook vector unavailable "
              f"({type(exc).__name__}), using local rules")
        playbook = []

    if not playbook:
        playbook = local_playbook_chunks(strategy, query)

    return format_rag_block(
        outcomes=outcomes, rationales=rationales, playbook=playbook,
    )
