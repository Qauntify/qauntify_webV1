# AI War Room — 3-agent debate (showcase layer)

## Goal

A gamified UI where three robot agents "debate" a trade and a Manager decides —
purely as a **showcase**. It does NOT gate real signals: the live engine stays
technical-only. The debate runs alongside to generate transcripts the UI plays
back as a robot conversation.

## Approved decisions

- **Showcase, not gatekeeper.** Real signals are still decided by the existing
  technical-only `confirm_setup`. The debate is a separate, additive feature.
- **Real multi-agent debate** — three actual SEA-LION calls per debate.
- **Fundamentals return for the show only.** The Fundamental agent re-uses the
  dormant `news_client` / `calendar_client`; this never touches live signals.

## The three agents

Run per triggering signal, results stored as a transcript:

1. **🤖 Technical Analyst** — input: the setup (entry/stop/TPs) + indicators.
   Argues the technical case (bull/bear, structure, R:R).
2. **🤖 Fundamental Analyst** — input: recent news headlines + nearby economic
   calendar events (dormant clients re-enabled here only). Argues the macro case.
3. **🧑‍💼 Manager** — input: the setup + BOTH analyses. Produces the final
   verdict (agree/caution/reject), a confidence 0–100, and a short rationale.

Order: Technical + Fundamental (independent), then Manager synthesises both.
Fail-soft: any agent error → that agent "abstains"; the Manager still decides.
Keys: round-robin the full SEA-LION key set (bounded volume — only on confirmed
signals / on-demand), independent of the scalper's KEY5-7.

## Trigger

When the engine **stores a confirmed signal**, spawn a debate about it (async /
best-effort, never blocks or alters the signal). Plus an on-demand trigger for
XAUUSD so the "gold war room" always has fresh content.

## Storage

New Supabase table `agent_debates`:
`id, signal_id (nullable), symbol, timeframe, direction, transcript jsonb
(list of {agent, avatar, message}), manager_verdict, manager_confidence,
created_at`. Public read-only RLS (same pattern as `signals`).

## UI — `/war-room`

A gamified page (reviving the removed "trading floor" — old `GoldFloorBoard`
lives in git history at `d83712a^`, adapt it):
- Robot avatars for Technical / Fundamental / Manager with chat bubbles that
  reveal in sequence (typing animation) for the latest debates.
- The Manager's verdict shown as a decision card (verdict + confidence meter +
  rationale), styled with the existing design tokens, light/dark aware.
- Reads recent `agent_debates` from Supabase (per-request or short poll).
- Clear "AI analysis for illustration — not financial advice" note.

## Build sequence (separate, focused chunks)

1. **Backend orchestration** — `signals/debate.py` (build the 3 prompts, call the
   LLM, parse, assemble transcript) + hook on confirmed-signal storage. TDD.
2. **Schema + storage** — `agent_debates` table + `save_debate` / `fetch_debates`.
3. **UI** — `/war-room` page + components, reading debates. Vitest + tsc.

## Out of scope (v1)

Agents replying to each other over multiple rounds (single round for v1);
the debate influencing real signals; real-time websockets (poll/refresh is fine).

## Honest notes

Three LLM calls per confirmed signal — bounded because it runs only on stored
signals, not every scan. Re-introduces news/calendar in the showcase path only.
Best-effort: a debate failure never affects the real signal.
