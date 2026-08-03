# Public access and an "educational only" disclaimer

## Goal

Make the whole product readable without an account, and frame it unambiguously
as a development project for education rather than as trading advice.

The data half is already done: migration `20260803120000_public_signals_read`
dropped the 24-hour anon preview window, so every non-shadow signal is readable
by a logged-out visitor. What remains is the front end — retiring the
login-gated pages that now duplicate the public ones, and making the framing
impossible to miss.

## Decisions (approved)

- **Permanent top bar**, site-wide, **not dismissible**. Chosen over a
  dismissible banner because a dismissed banner is invisible to exactly the
  returning visitor most likely to act on a signal, and over a first-visit modal
  because that reads as a sales pattern and fires once per browser.
- **Bar wording** — desktop: `Development project · Educational use only · Not
  financial advice`. Below the `sm` breakpoint: `Educational only · Not
  financial advice`.
- **Sticky stacking:** bar sticky at `top-0`, `Nav` sticky directly beneath it.
  Both stay pinned while the page scrolls.
- **Bar lives in the root layout**, not inside `Nav`, so it also covers
  `/login` and `/admin`, which do not render `Nav`.
- **`/disclaimer` page** carries the full picture; the bar links to it.
- **Dashboard retired.** `/dashboard`, `/dashboard/markets` and
  `/dashboard/war-room` become permanent redirects to their public equivalents.
- **`/signup` removed.** With nothing behind login but `/admin`, public
  registration grants nothing.
- **Context-specific disclaimers stay.** Only the generic wording is
  centralised.

## Out of scope (YAGNI)

- Deleting the now-unrendered `Faq`, `Features`, `Markets` and `Pricing` landing
  components. They are dead but harmless; removing them is separate tidy-up.
- Any change to Telegram alert copy or rendered chart annotations.
- Any change to RLS, the engine, or the R model.
- Cookie/consent tooling. The bar is informational and stores nothing, so it is
  not a consent mechanism.

## Architecture

### `web/src/lib/disclaimer.ts` (new)

Single source of truth for the generic wording, so it cannot drift across files
again. Exports the long form, the short (mobile) form, and the footer sentence.
Consumed by `DisclaimerBar`, `Footer`, and the `layout.tsx` metadata
description — which today carries its own fourth copy of the same idea.

### `web/src/components/shared/DisclaimerBar.tsx` (new, server component)

No client JS: there is nothing to dismiss and no state to hold.

Renders a warning glyph, the wording, and a "What this means ›" link to
`/disclaimer`. Two spans handle the breakpoint — long form `hidden sm:inline`,
short form `sm:hidden`.

**Fixed height, never wraps.** This is load-bearing, not cosmetic: the height is
published as a CSS token that three pages subtract from `100svh`. A bar that
wraps to two lines on a narrow screen makes that token wrong, and `/war-room` is
`overflow-hidden`, so it would clip content rather than fail visibly. The mobile
wording is short enough to hold one line at 320px.

Colour is a colder amber than the `#c9a227` brand accent. The accent already
marks buttons, links and confidence badges; a warning in the same colour reads
as more branding and stops registering.

### `web/src/app/layout.tsx`

Renders `<DisclaimerBar />` as the first child of `<body>`, above `{children}`.

Metadata description sources its disclaimer clause from `lib/disclaimer.ts`.

### `web/src/app/globals.css`

Three new tokens: `--disclaimer-h`, `--nav-h`, and `--chrome-h` as their sum.

`--nav-h` replaces the `4rem` currently duplicated across three page files with
no link back to the `h-16` in `Nav.tsx` that defines it. That duplication is why
adding any chrome silently breaks the same three pages.

### `web/src/components/shared/Nav.tsx`

`sticky top-0 z-40` becomes sticky at an offset equal to `--disclaimer-h`, with
a `z-index` strictly lower than the bar's, so the two stack rather than overlap
and the bar always wins if they ever meet.

On `/admin` the bar appears with no `Nav` beneath it, because admin pages never
rendered one. Accepted — the framing applies there too, and the offset is a
no-op when nothing else is sticky.

### Pages sizing against the viewport

`/signals`, `/markets` and `/war-room` replace `calc(100svh-4rem)` with
`calc(100svh - var(--chrome-h))`.

### Retired routes

`app/dashboard/page.tsx`, `app/dashboard/markets/page.tsx` and
`app/dashboard/war-room/page.tsx` become permanent redirects to `/signals`,
`/markets` and `/war-room`, so existing links and bookmarks keep working.

`DashboardShell` and `DashboardNav` fall out of use and are deleted.
`app/signup/page.tsx` and the `signUp` action in `app/auth/actions.ts` are
removed. `proxy.ts` continues to gate `/admin` unchanged.

### `web/src/app/disclaimer/page.tsx` (new)

Public, renders `Nav`, seven sections:

1. **What this is** — a development project built in the open, not a product.
2. **Not advice** — educational and analysis only; nothing is a recommendation.
3. **How signals are made** — deterministic detectors plus an LLM confirmation
   gate. No accuracy claim.
4. **How outcomes are measured** — the scale-out R model: a third booked at each
   of TP1/TP2/TP3, breakeven after TP1, so a full run is +2R and not +3R. Stated
   plainly so the track record's numbers can be checked rather than trusted.
5. **Costs are estimates** — the `COST_BPS` assumptions (20bps crypto, 2bps
   gold, 1.5bps GBPUSD), named as assumptions, not as achieved fills.
6. **Data caveats** — XAUUSD prices are COMEX `GC=F` futures, not spot. Basis
   and contract roll are not adjusted for, which matters most on the 1m scalper.
7. **Risk, and strategies run despite negative backtests** — `bbma_reentry`
   (−0.137R) and `bbma_extreme` (−0.153R) over 8.87 years are admin-selectable
   for live delivery. Disclosed deliberately: a transparency page that omits a
   known-negative strategy is weaker than one that names it and says forward
   data is the only way to confirm it.

## Testing

- `DisclaimerBar` renders both breakpoint wordings and links to `/disclaimer`.
- The bar is present in the root layout — guards against it being dropped later.
- All three retired dashboard routes redirect to their public equivalents.
- `/disclaimer` renders each of its seven sections.
- `lib/disclaimer.ts` is the only place the generic wording is spelled out: a
  test greps `Footer`, `DisclaimerBar` and `layout.tsx` for hardcoded copies.
- Existing suite stays green, and `npm run lint` runs before pushing. Lint is a
  CI step that was missed last time and broke the build.

## Rough build order

1. `lib/disclaimer.ts` + tests.
2. `DisclaimerBar` + tests.
3. CSS tokens; `Nav` offset; the three viewport calcs.
4. Mount the bar in the root layout; point the metadata at the shared strings.
5. `/disclaimer` page + tests.
6. Retire the dashboard routes and `/signup`; delete the orphaned components.
7. Point `Footer` at the shared strings.
