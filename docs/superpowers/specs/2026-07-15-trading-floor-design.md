# Trading Floor Design

Date: 2026-07-15  
Branch: `feature/trading-floor`

## Goal

Add a hedge-fund-style **Trading Floor** on the member dashboard: an ambient multi-desk board plus floor chat. Uses a **separate LLM API** from the existing SEA-LION signal confirmer. Does **not** modify detectors, confirm/reject, RAG, storage of signals, or Telegram.

## Decisions (approved)

- **Placement**: member dashboard tab (`/dashboard?tab=floor`), not admin-only.
- **Mode**: board + chat (ambient desk posts + on-demand Q&A).
- **Desk count (v1)**: **4** — Macro/Session, Technical, News, PM/Risk.
- **Retrieval style**: board notes are stored and reused as chat context (approach B). Chat does not fan out to all desks every message in v1.
- **Hard boundary**: floor may **read** signals / calendar / headlines / session clock; floor must **never** write signals, veto confirms, or send Telegram.
- **LLM**: new env vars only (`FLOOR_LLM_*`); leave `SEALION_*` confirm path untouched.
- **Cadence**: independent floor cron (target 15–30 min), not the signals engine cron.

## Desk roles

| Role | Board job | Primary read-only inputs |
|------|-----------|---------------------------|
| `macro` | Session + calendar risk tone | Session clock; High/Medium calendar for watched symbols |
| `technical` | Bias notes by stream/symbol cluster | Latest open + recent closed signals (levels/status only); no candle recompute in v1 |
| `news` | Catalyst summary vs symbols | Symbol-filtered RSS headlines (same sources style as engine, floor-owned fetch OK) |
| `pm` | Floor brief: agreement, conflict, size caution | Latest notes from the other three desks + open-book snapshot |

Tone tags for cards: `bullish` | `neutral` | `cautious` (stored + shown as a chip).

## Product UI

1. Dashboard nav gains **Trading Floor** alongside Super scalp / Scalping / Swing / All.
2. Floor page composition:
   - Top: four desk cards (role, tone, brief excerpt, timestamp).
   - Bottom: chat thread + input (PM answers).
3. Empty board: “Desks warming up” until first successful floor cron.
4. Do not clone signal-card layout into the hero of this tab; board cards are interaction containers for reading desk notes.

## Data model (new tables only)

### `floor_briefs`

- `id` uuid PK  
- `desk` text check in (`macro`, `technical`, `news`, `pm`)  
- `tone` text check in (`bullish`, `neutral`, `cautious`)  
- `body` text not null (short brief)  
- `run_id` text not null (groups one floor cron cycle)  
- `created_at` timestamptz not null  

Indexes: `(desk, created_at desc)`, `(run_id)`.  
RLS: authenticated members **select**; service role **insert**. No member writes.

### `floor_chat_messages`

- `id` uuid PK  
- `user_id` uuid not null references auth.users  
- `role` text check in (`user`, `assistant`)  
- `content` text not null  
- `created_at` timestamptz not null  

Indexes: `(user_id, created_at desc)`.  
RLS: members select/insert where `user_id = auth.uid()`.

Board “latest” = newest row per `desk` (or newest complete `run_id` with all four desks).

## API / server

| Route | Auth | Behavior |
|-------|------|----------|
| `POST /api/cron/floor` | Cron secret (query or Bearer, same pattern as engine trigger) | Fetch context → call floor LLM once per desk → insert `floor_briefs` under one `run_id`. Soft-fail per desk. |
| `GET /api/floor/board` | Member session | Latest brief per desk. |
| `GET /api/floor/chat` | Member session | Recent messages for current user. |
| `POST /api/floor/chat` | Member session | Persist user message; call PM with question + board pack + open-signals summary; persist assistant reply; rate-limit. |

Floor LLM client lives under something like `web/src/lib/floor/` or a small `signals/floor/` package — **must not** reuse `confirm_setup` / `SeaLionClient` as the production confirm path. Separate client wired to `FLOOR_LLM_BASE_URL` / `FLOOR_LLM_API_KEY` / `FLOOR_LLM_MODEL`.

## Config

```
FLOOR_LLM_API_KEY=
FLOOR_LLM_BASE_URL=
FLOOR_LLM_MODEL=
FLOOR_CRON_SECRET=   # or reuse CRON_SECRET if already shared for engined triggers — document choice at implementation
```

Prefer dedicated `FLOOR_CRON_SECRET` if secrets already differ; otherwise document reusing the existing engine cron secret for ops simplicity.

## Security & cost

- Browser never holds service-role or floor API keys.
- Chat: rate limit per user (implementation default: ~6 messages / minute).
- Cap brief and chat completion lengths.
- Soft-fail: missing calendar/news/LLM for one desk still returns partial board.

## Out of scope (v1)

- Changing signal detectors, composer confirm, RAG, Telegram, or `ai_events` semantics.
- Fifth skeptic / compliance desk.
- @mention routing to a single desk in chat.
- Candle re-fetch / re-run of ICT detectors inside Technical desk.
- Auto floor veto of setups.
- Admin desk config UI (hardcoded four roles is enough).

## Success criteria

1. Logged-in member opens `/dashboard?tab=floor`, sees four desk cards after cron has run.
2. Member can chat and get a PM reply that references current board notes.
3. Existing Super scalp / Scalping / Swing signal flow behaves identically to pre-floor.
4. Floor LLM failures do not break dashboard signal tabs.
