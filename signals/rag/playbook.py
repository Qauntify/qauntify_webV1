"""In-repo playbook chunks — source of truth for strategy RAG text.

Seeded into `playbook_chunks` (with embeddings) when available; used as a
keyword fallback when the vector table is empty or unreachable.
"""

# Each chunk: strategy key, short title, body (kept tight for prompt budget).
PLAYBOOK_CHUNKS = (
    {
        "strategy": "ict_fvg",
        "title": "5m ICT FVG confirm gate",
        "body": (
            "Super-scalp ict_fvg: confirm only when liquidity sweep, CHoCH, "
            "and Fair Value Gap retest all printed recently. Prefer 15m HTF "
            "agreement. Tight targets (0.5R/1R/1.5R) — reject if stop is wide "
            "vs ATR or the retest is stale. No session killzone requirement; "
            "structure quality matters more than clock."
        ),
    },
    {
        "strategy": "ict_fvg",
        "title": "5m ICT FVG reject cues",
        "body": (
            "Reject ict_fvg when news/calendar clearly fights the direction, "
            "when HTF 15m trend opposes, when FVG was already filled through, "
            "or when entry sits mid-range with no clear displacement. Do not "
            "stretch confidence on noisy Asia-only ranges if London/NY are "
            "about to reprice the level."
        ),
    },
    {
        "strategy": "ce_lwma",
        "title": "15m CE+LWMA confirm gate",
        "body": (
            "Scalp ce_lwma: need a fresh H1 Chandelier Exit flip into the "
            "matching M15 LWMA200 zone (long in discount / short in premium). "
            "Entry is last closed M15; SL is the active CE trail. Confirm when "
            "zone + flip align and R:R to 1R/2R/3R stays sensible."
        ),
    },
    {
        "strategy": "ce_lwma",
        "title": "15m CE+LWMA reject cues",
        "body": (
            "Reject ce_lwma on stale CE flips, when price is on the wrong side "
            "of LWMA200 for the proposed direction, when stop distance is "
            "extreme vs recent range, or when high-impact news for the pair's "
            "currencies is imminent and conflicts with the idea."
        ),
    },
    {
        "strategy": "ict_smc",
        "title": "1h ICT/SMC confirm gate",
        "body": (
            "Swing ict_smc: liquidity sweep then structure shift / CHoCH. "
            "Prefer HTF 4h trend agreement and healthy ADX when provided. "
            "Targets are 1R/2R/3R. Confirm when displacement after the sweep "
            "is clear and stop sits beyond the swept liquidity."
        ),
    },
    {
        "strategy": "ict_smc",
        "title": "1h ICT/SMC reject cues",
        "body": (
            "Reject ict_smc on weak ADX / chop, HTF conflict, sweep without "
            "follow-through CHoCH, or calendar shocks that invalidate the "
            "liquidity grab narrative."
        ),
    },
    {
        "strategy": "ema_cross",
        "title": "EMA cross confirm gate",
        "body": (
            "Swing ema_cross: EMA9/21 crossover with RSI and MACD histogram "
            "filters. Prefer HTF trend agreement when provided. Confirm when "
            "momentum agrees and stop placement leaves workable 1R/2R/3R."
        ),
    },
    {
        "strategy": "ema_cross",
        "title": "EMA cross reject cues",
        "body": (
            "Reject ema_cross on late stretched crosses, RSI extremes against "
            "continuation without pullback, MACD already fading, or HTF trend "
            "fighting the cross."
        ),
    },
)
