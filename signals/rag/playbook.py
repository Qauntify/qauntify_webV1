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
            "Super-scalp ict_fvg: confirm when any valid path printed — "
            "(1) liquidity sweep + CHoCH + FVG retest, (2) sweep + CHoCH "
            "without FVG, or (3) sweep reclaim alone. Prefer 15m HTF "
            "agreement but soft disagreement is not a hard veto. Tight "
            "targets (0.5R/1R/1.5R) — reject if stop is invalid vs entry or "
            "targets sit on the wrong side. No session killzone requirement; "
            "structure quality matters more than clock. Missing FVG alone is "
            "not a reject when CHoCH or reclaim is present. When borderline "
            "but technically valid, lean confirm with moderate confidence."
        ),
    },
    {
        "strategy": "ict_fvg",
        "title": "5m ICT FVG reject cues",
        "body": (
            "Reject ict_fvg when stop is already invalid vs entry, when "
            "targets are on the wrong side of entry, when there is no "
            "sweep and no CHoCH and no reclaim at all, or when the structure "
            "label is stale/nonsensical. Do not reject solely for missing "
            "FVG or soft 15m HTF disagreement on 5m."
        ),
    },
    {
        "strategy": "ce_lwma",
        "title": "15m CE+LWMA confirm gate",
        "body": (
            "Scalp ce_lwma: need a fresh H1 Chandelier Exit flip into the "
            "matching M15 LWMA200 zone (long in discount / short in premium). "
            "Entry is last closed M15; SL is the active CE trail. Confirm when "
            "zone + flip align and R:R to 1R/2R/3R stays sensible. When "
            "borderline but technically valid, lean confirm with moderate "
            "confidence."
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
            "is clear and stop sits beyond the swept liquidity. When borderline "
            "but technically valid, lean confirm with moderate confidence."
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
        "strategy": "sr_zone",
        "title": "S/R bounce confirm gate",
        "body": (
            "Support/Resistance sr_zone: trade a bounce only when price reaches "
            "a tested zone (>=2 touches) AND a confirmation candle rejects it — "
            "a rejection wick that closes back inside the range (bullish at "
            "support, bearish at resistance). Prefer the 1st-2nd touch; each "
            "retest weakens the level. Best in ranging conditions; stop sits "
            "beyond the zone, targets 1R/2R/3R. When borderline but technically "
            "valid, lean confirm with moderate confidence."
        ),
    },
    {
        "strategy": "sr_zone",
        "title": "S/R bounce reject cues",
        "body": (
            "Reject sr_zone on a mere touch with no rejection close, on a "
            "strong trend (high ADX) that runs levels over, when HTF trend "
            "opposes the bounce, on a heavily-retested level about to break, "
            "or when the wick pierced deep through the zone (a breakdown, not "
            "a rejection)."
        ),
    },
    {
        "strategy": "ema_cross",
        "title": "EMA cross confirm gate",
        "body": (
            "Swing ema_cross: EMA9/21 crossover with RSI and MACD histogram "
            "filters. Prefer HTF trend agreement when provided. Confirm when "
            "momentum agrees and stop placement leaves workable 1R/2R/3R. "
            "When borderline but technically valid, lean confirm with moderate "
            "confidence."
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
