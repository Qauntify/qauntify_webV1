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
            "targets (0.5R/1R/2R) — reject if stop is invalid vs entry or "
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
    {
        "strategy": "msnr",
        "title": "1h MSNR confirm gate",
        "body": (
            "Swing msnr (Malaysian body-zone S/R): zones are candle bodies "
            "(open/close), not wick tips. Prefer fresh zones. Entry modes: "
            "(1) rejection wick at support/resistance closing back out of the "
            "zone, or (2) RBS/SBR — break then retest of flipped resistance/"
            "support. Respect 4H storyline: up→longs only, down→shorts only, "
            "None→either edge. Stop beyond the zone + ATR buffer; targets "
            "1R/2R/3R. Confirm when zone quality, entry mode, and HTF agree. "
            "When borderline but technically valid, lean confirm with moderate "
            "confidence."
        ),
    },
    {
        "strategy": "msnr",
        "title": "1h MSNR reject cues",
        "body": (
            "Reject msnr when the wick never reaches the body zone, when the "
            "close stays inside the zone (no rejection), when HTF 4h fights "
            "the proposed side, when an RBS/SBR retest fails (close back "
            "through the flipped zone), when the zone is chewed up by many "
            "body touches, or when stop distance is extreme vs ATR."
        ),
    },
    {
        "strategy": "orb_rvol",
        "title": "15m Opening Range Breakout confirm gate",
        "body": (
            "orb_rvol: trades the first breakout of a session opening range "
            "(Asia 00:00 / London 07:00 / NY 13:30 UTC, first 30 minutes), "
            "in the direction the range itself moved -- a bullish range only "
            "permits longs, bearish only shorts, a doji range no trade. "
            "Fires only when the opening range traded on relative volume "
            ">= 1.0x its own anchor's recent history; this filter is the "
            "entire source of the strategy's edge (SSRN 4729284) -- plain "
            "ORB without it underperforms buy-and-hold. Stop sits at the "
            "opposite edge of the range plus an ATR buffer; wide 2R/4R/6R "
            "targets since the edge depends on runners. Confirm when "
            "direction, RVOL and the breakout close all agree."
        ),
    },
    {
        "strategy": "orb_rvol",
        "title": "15m Opening Range Breakout reject cues",
        "body": (
            "Reject orb_rvol when relative volume is at or below its own "
            "anchor's recent average (the headline gate), when the proposed "
            "direction contradicts the opening range's own bullish/bearish "
            "read, when the range itself was a doji, or when the stop is "
            "farther than 2.5 ATR from entry. Do not reject solely for "
            "missing higher-timeframe agreement -- this strategy takes no "
            "HTF gate by design (the opening range is its own thesis)."
        ),
    },
)
