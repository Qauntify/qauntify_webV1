"""Format retrieved rows into a compact prompt block."""

OUTCOME_LIMIT = 3
RATIONALE_LIMIT = 3
PLAYBOOK_LIMIT = 2
RATIONALE_MAX_CHARS = 220


def _short(text: str, limit: int = RATIONALE_MAX_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_outcomes(rows: list) -> str:
    if not rows:
        return ""
    lines = ["Similar past outcomes:"]
    for row in rows[:OUTCOME_LIMIT]:
        strat = ""
        indicators = row.get("indicators") or {}
        if isinstance(indicators, dict) and indicators.get("strategy"):
            strat = f" strategy={indicators['strategy']}"
        lines.append(
            f"- {row.get('status')} {row.get('direction')} "
            f"entry={row.get('entry')} conf={row.get('confidence')} "
            f"closed={row.get('closed_at') or row.get('created_at')}"
            f"{strat}"
        )
    return "\n".join(lines)


def format_rationales(rows: list) -> str:
    if not rows:
        return ""
    lines = ["Recent AI decisions on similar setups:"]
    for row in rows[:RATIONALE_LIMIT]:
        lines.append(
            f"- {row.get('kind')} conf={row.get('confidence')}: "
            f"{_short(row.get('rationale', ''))}"
        )
    return "\n".join(lines)


def format_playbook(chunks: list) -> str:
    if not chunks:
        return ""
    lines = ["Playbook (strategy rules):"]
    for chunk in chunks[:PLAYBOOK_LIMIT]:
        title = chunk.get("title") or "rule"
        body = _short(chunk.get("body", ""), limit=500)
        lines.append(f"- {title}: {body}")
    return "\n".join(lines)


def format_rag_block(*, outcomes=None, rationales=None, playbook=None) -> str:
    """Join non-empty sections; empty inputs yield '' (omit from prompt)."""
    parts = [
        format_outcomes(outcomes or []),
        format_rationales(rationales or []),
        format_playbook(playbook or []),
    ]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return "Retrieved context (use as evidence, not a hard veto):\n" + "\n\n".join(parts)
