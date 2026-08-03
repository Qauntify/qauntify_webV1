# Public Access and Educational-Only Disclaimer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Frame the whole site as a development/educational project with a permanent non-dismissible disclaimer bar and a `/disclaimer` page, and retire the login-gated pages that now duplicate the public ones.

**Architecture:** A sticky amber bar mounts in the root layout above everything, so it covers every route including `/login` and `/admin`. `Nav` sticks directly beneath it at an offset. Chrome heights become CSS tokens, because three pages currently subtract a hardcoded `4rem` from `100svh` with no link to the `h-16` that defines it. Disclaimer wording moves to one module consumed by the bar, the footer and the page metadata.

**Tech Stack:** Next.js 16 (App Router, RSC), React 19, Tailwind v4, TypeScript, Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-03-public-access-and-disclaimer-design.md`

**Working directory:** All paths below are relative to the repo root. Run `npm` commands from `web/`.

---

## Task 1: Canonical disclaimer strings

**Files:**
- Create: `web/src/lib/disclaimer.ts`
- Test: `web/tests/lib/disclaimer.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/lib/disclaimer.test.ts
import { describe, expect, it } from "vitest";

import {
  DISCLAIMER_BAR_LONG,
  DISCLAIMER_BAR_SHORT,
  DISCLAIMER_FOOTER,
  DISCLAIMER_META,
} from "@/lib/disclaimer";

describe("disclaimer strings", () => {
  it("every variant refuses to be read as advice", () => {
    for (const s of [
      DISCLAIMER_BAR_LONG,
      DISCLAIMER_BAR_SHORT,
      DISCLAIMER_FOOTER,
      DISCLAIMER_META,
    ]) {
      expect(s.toLowerCase()).toContain("not financial advice");
    }
  });

  it("the long bar names the project as under development", () => {
    expect(DISCLAIMER_BAR_LONG.toLowerCase()).toContain("development");
  });

  it("both bar variants say educational", () => {
    expect(DISCLAIMER_BAR_LONG.toLowerCase()).toContain("educational");
    expect(DISCLAIMER_BAR_SHORT.toLowerCase()).toContain("educational");
  });

  // The bar is fixed-height and never wraps, so the short form has to survive
  // a 320px viewport next to a glyph and a "What this means" link.
  it("the short bar stays short enough not to wrap on a small phone", () => {
    expect(DISCLAIMER_BAR_SHORT.length).toBeLessThanOrEqual(44);
  });

  it("the short bar is shorter than the long one", () => {
    expect(DISCLAIMER_BAR_SHORT.length).toBeLessThan(DISCLAIMER_BAR_LONG.length);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/lib/disclaimer.test.ts`
Expected: FAIL — `Failed to resolve import "@/lib/disclaimer"`

- [ ] **Step 3: Write the implementation**

```ts
// web/src/lib/disclaimer.ts
// One source of truth for the generic disclaimer wording.
//
// This text previously existed in four places with four different phrasings
// (the footer, the layout metadata, and two more in components). Anything
// generic belongs here. Context-specific notes — the backtest panel, the
// track-record methodology, the war-room pages — deliberately do NOT come from
// this module: each says something particular about its own content, and
// flattening them into one sentence would lose that.

/** Bar text at `sm` and above. */
export const DISCLAIMER_BAR_LONG =
  "Development project · Educational use only · Not financial advice";

/** Bar text below `sm`. Must fit one line at 320px — see the length test. */
export const DISCLAIMER_BAR_SHORT = "Educational only · Not financial advice";

/** Footer paragraph. */
export const DISCLAIMER_FOOTER =
  "Signals are for educational and analysis purposes only. Not financial advice. Trading involves risk.";

/** Trailing clause of the site metadata description. */
export const DISCLAIMER_META =
  "Signals are for education and analysis — not financial advice.";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run tests/lib/disclaimer.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/disclaimer.ts web/tests/lib/disclaimer.test.ts
git commit -m "feat(disclaimer): one source of truth for the generic wording"
```

---

## Task 2: Warning colour tokens and chrome height tokens

**Files:**
- Modify: `web/src/app/globals.css`

No test — these are CSS custom properties consumed by later tasks, which do have tests.

- [ ] **Step 1: Add warn + height tokens to the light `:root` block**

In `web/src/app/globals.css`, inside `:root { ... }`, immediately after the `--shadow-card-hover:` line and before the closing `}`, add:

```css
  /* Warning surface. Deliberately unlike --accent (indigo) and unlike the
     #c9a227 gold used by the war-room floor styling: the disclaimer bar has to
     read as a warning, not as another branded surface. */
  --warn: #fef3c7;
  --warn-ink: #92400e;
  --warn-line: #fcd34d;

  /* Chrome heights. --nav-h MUST match the h-16 on the header in Nav.tsx, and
     --disclaimer-h MUST match the fixed height of DisclaimerBar. Pages subtract
     --chrome-h from 100svh; a bar that wrapped to two lines would make this a
     lie and /war-room (overflow-hidden) would clip rather than fail visibly. */
  --disclaimer-h: 2.25rem;
  --nav-h: 4rem;
  --chrome-h: calc(var(--disclaimer-h) + var(--nav-h));
```

- [ ] **Step 2: Add the dark warn overrides**

Inside the `.dark { ... }` block, after its `--shadow-card-hover:` line and before the closing `}`, add:

```css
  --warn: #2e2205;
  --warn-ink: #e8b93a;
  --warn-line: #4a3a0d;
```

Heights are theme-independent, so they are NOT repeated here.

- [ ] **Step 3: Expose warn colours to Tailwind**

Inside `@theme inline { ... }`, after the `--color-short-soft: var(--short-soft);` line, add:

```css
  --color-warn: var(--warn);
  --color-warn-ink: var(--warn-ink);
  --color-warn-line: var(--warn-line);
```

- [ ] **Step 4: Verify the build still compiles the CSS**

Run: `cd web && npx next build 2>&1 | grep -E "Compiled|error"`
Expected: `✓ Compiled successfully`

- [ ] **Step 5: Commit**

```bash
git add web/src/app/globals.css
git commit -m "feat(theme): warning surface and chrome-height tokens"
```

---

## Task 3: The DisclaimerBar component

**Files:**
- Create: `web/src/components/shared/DisclaimerBar.tsx`
- Test: `web/tests/components/shared/DisclaimerBar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web/tests/components/shared/DisclaimerBar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DisclaimerBar } from "@/components/shared/DisclaimerBar";
import {
  DISCLAIMER_BAR_LONG,
  DISCLAIMER_BAR_SHORT,
} from "@/lib/disclaimer";

describe("DisclaimerBar", () => {
  it("renders both breakpoint wordings so CSS picks one", () => {
    render(<DisclaimerBar />);
    expect(screen.getByText(DISCLAIMER_BAR_LONG)).toBeDefined();
    expect(screen.getByText(DISCLAIMER_BAR_SHORT)).toBeDefined();
  });

  it("links to the full disclaimer page", () => {
    render(<DisclaimerBar />);
    const link = screen.getByRole("link", { name: /what this means/i });
    expect(link.getAttribute("href")).toBe("/disclaimer");
  });

  // The whole point of choosing a permanent bar over a dismissible banner: a
  // dismissed banner is invisible to the returning visitor most likely to act
  // on a signal. Nothing in here may offer a way to close it.
  it("offers no way to dismiss itself", () => {
    const { container } = render(<DisclaimerBar />);
    expect(container.querySelectorAll("button").length).toBe(0);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("is a landmark screen readers can find", () => {
    render(<DisclaimerBar />);
    expect(screen.getByRole("note")).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/components/shared/DisclaimerBar.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/shared/DisclaimerBar"`

- [ ] **Step 3: Write the implementation**

```tsx
// web/src/components/shared/DisclaimerBar.tsx
import Link from "next/link";

import { DISCLAIMER_BAR_LONG, DISCLAIMER_BAR_SHORT } from "@/lib/disclaimer";

// Permanent, site-wide, not dismissible. A server component on purpose: there
// is no state and no dismissal, so it ships zero client JS.
//
// Fixed height (--disclaimer-h) and whitespace-nowrap are load-bearing, not
// cosmetic. Pages subtract --chrome-h from 100svh, and /war-room is
// overflow-hidden — a bar that wrapped on a narrow screen would push content
// out of view rather than merely look wrong.
export function DisclaimerBar() {
  return (
    <div
      role="note"
      aria-label="Site disclaimer"
      className="sticky top-0 z-50 flex h-[var(--disclaimer-h)] items-center gap-2 overflow-hidden whitespace-nowrap border-b border-warn-line bg-warn px-4 text-xs font-medium text-warn-ink"
    >
      <span aria-hidden="true">⚠</span>
      <span className="hidden sm:inline">{DISCLAIMER_BAR_LONG}</span>
      <span className="sm:hidden">{DISCLAIMER_BAR_SHORT}</span>
      <Link
        href="/disclaimer"
        className="ml-auto shrink-0 underline underline-offset-2 hover:no-underline"
      >
        What this means
      </Link>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run tests/components/shared/DisclaimerBar.test.tsx`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add web/src/components/shared/DisclaimerBar.tsx web/tests/components/shared/DisclaimerBar.test.tsx
git commit -m "feat(disclaimer): permanent non-dismissible bar component"
```

---

## Task 4: Mount the bar and offset the nav

**Files:**
- Modify: `web/src/app/layout.tsx`
- Modify: `web/src/components/shared/Nav.tsx:21`
- Test: `web/tests/lib/chrome-wiring.test.ts`

The layout returns `<html>`, which jsdom cannot usefully render, so this task's
test reads source files instead. That is weaker than a render test but it is
the property that actually matters: the bar must not silently fall out of the
layout, and the two height tokens must not drift from the markup they describe.

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/lib/chrome-wiring.test.ts
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const root = join(__dirname, "..", "..", "src");
const read = (p: string) => readFileSync(join(root, p), "utf8");

describe("site chrome wiring", () => {
  it("mounts the disclaimer bar in the root layout", () => {
    const layout = read("app/layout.tsx");
    expect(layout).toContain("DisclaimerBar");
    expect(layout).toMatch(/<DisclaimerBar\s*\/>/);
  });

  it("offsets the nav by the bar height instead of pinning it to the top", () => {
    const nav = read("components/shared/Nav.tsx");
    expect(nav).toContain("top-[var(--disclaimer-h)]");
    expect(nav).not.toContain("sticky top-0");
  });

  // --nav-h is subtracted from 100svh by three pages. If someone changes the
  // header's h-16 without changing the token, those pages break silently.
  it("keeps --nav-h in step with the header height in Nav.tsx", () => {
    expect(read("components/shared/Nav.tsx")).toContain("h-16");
    expect(read("app/globals.css")).toContain("--nav-h: 4rem;");
  });

  it("sizes viewport-height pages from the chrome token, not a magic number", () => {
    for (const page of [
      "app/signals/page.tsx",
      "app/markets/page.tsx",
      "app/war-room/page.tsx",
    ]) {
      const src = read(page);
      expect(src).toContain("var(--chrome-h)");
      expect(src).not.toContain("100svh-4rem");
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/lib/chrome-wiring.test.ts`
Expected: FAIL — first assertion, layout does not contain `DisclaimerBar`

- [ ] **Step 3: Mount the bar in the root layout**

In `web/src/app/layout.tsx`, add to the imports (after the `import "./globals.css";` line):

```tsx
import { DisclaimerBar } from "@/components/shared/DisclaimerBar";
import { DISCLAIMER_META } from "@/lib/disclaimer";
```

Replace the `description` line in `metadata` with:

```tsx
  description: `Technical setups on crypto, gold, and forex — confirmed by AI, explained in plain language. ${DISCLAIMER_META}`,
```

Replace the `<body>` line with:

```tsx
      <body className="min-h-full flex flex-col">
        <DisclaimerBar />
        {children}
      </body>
```

- [ ] **Step 4: Offset the nav**

In `web/src/components/shared/Nav.tsx`, replace line 21:

```tsx
    <header className="sticky top-0 z-40 border-b border-line bg-card backdrop-blur-xl transition-all duration-300">
```

with:

```tsx
    <header className="sticky top-[var(--disclaimer-h)] z-40 border-b border-line bg-card backdrop-blur-xl transition-all duration-300">
```

`z-40` stays below the bar's `z-50`, so the bar wins if they ever overlap.

- [ ] **Step 5: Repoint the three viewport-height pages**

In `web/src/app/signals/page.tsx`, replace `min-h-[calc(100svh-4rem)]` with `min-h-[calc(100svh-var(--chrome-h))]`.

In `web/src/app/markets/page.tsx`, replace `min-h-[calc(100svh-4rem)]` with `min-h-[calc(100svh-var(--chrome-h))]`.

In `web/src/app/war-room/page.tsx`, replace `h-[calc(100svh-4rem)]` with `h-[calc(100svh-var(--chrome-h))]`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd web && npx vitest run tests/lib/chrome-wiring.test.ts`
Expected: PASS, 4 tests

- [ ] **Step 7: Verify the calc actually reaches the stylesheet**

Tailwind v4 normalises `calc(100svh-var(--chrome-h))` into valid CSS with
spaces around the operator. Confirm rather than assume:

Run: `cd web && npx next build >/dev/null 2>&1 && find .next -name "*.css" | xargs grep -oh "calc(100svh - var(--chrome-h))" | head -1`
Expected: prints `calc(100svh - var(--chrome-h))` at least once

- [ ] **Step 8: Commit**

```bash
git add web/src/app/layout.tsx web/src/components/shared/Nav.tsx web/src/app/signals/page.tsx web/src/app/markets/page.tsx web/src/app/war-room/page.tsx web/tests/lib/chrome-wiring.test.ts
git commit -m "feat(disclaimer): mount the bar site-wide and tokenise chrome heights"
```

---

## Task 5: The /disclaimer page

**Files:**
- Create: `web/src/components/disclaimer/DisclaimerBody.tsx`
- Create: `web/src/app/disclaimer/page.tsx`
- Test: `web/tests/components/disclaimer/DisclaimerBody.test.tsx`

The body lives in its own component file rather than being exported from the
page. The page imports `Nav`, which imports `lib/supabase/server`, which imports
`next/headers` — importing the page module inside vitest would drag all of that
in and can throw at import time. A standalone component is both testable and a
cleaner unit.

- [ ] **Step 1: Write the failing test**

```tsx
// web/tests/components/disclaimer/DisclaimerBody.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DisclaimerBody } from "@/components/disclaimer/DisclaimerBody";

describe("DisclaimerBody", () => {
  it("renders all seven sections", () => {
    render(<DisclaimerBody />);
    for (const heading of [
      /what this is/i,
      /not advice/i,
      /how signals are made/i,
      /how outcomes are measured/i,
      /costs are estimates/i,
      /data caveats/i,
      /risk/i,
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeDefined();
    }
  });

  it("states the scale-out R model rather than implying a full 3R win", () => {
    render(<DisclaimerBody />);
    expect(screen.getByText(/\+2R/)).toBeDefined();
  });

  it("names the cost assumptions as assumptions", () => {
    render(<DisclaimerBody />);
    expect(screen.getByText(/20\s*bps/i)).toBeDefined();
  });

  it("discloses that gold prices are COMEX futures, not spot", () => {
    render(<DisclaimerBody />);
    expect(screen.getByText(/GC=F/)).toBeDefined();
  });

  it("discloses the strategies that backtest negative", () => {
    render(<DisclaimerBody />);
    expect(screen.getByText(/−0\.137R|-0\.137R/)).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/components/disclaimer/DisclaimerBody.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/disclaimer/DisclaimerBody"`

- [ ] **Step 3: Write the body component**

```tsx
// web/src/components/disclaimer/DisclaimerBody.tsx
function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-line py-6">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-slate">
        {children}
      </div>
    </section>
  );
}

export function DisclaimerBody() {
  return (
    <div className="page-container max-w-3xl py-10">
      <h1 className="text-2xl font-bold md:text-3xl">Disclaimer</h1>
      <p className="mt-2 text-sm text-slate">
        The short version is in the bar at the top of every page. This is the
        long version.
      </p>

      <Section title="What this is">
        <p>
          Qauntify is a development project, built in the open. It is not a
          product, not a service, and not a business offering to manage anyone
          &apos;s money. It exists so its author can learn how automated trading
          systems behave, and to publish what happens when they do.
        </p>
      </Section>

      <Section title="Not advice">
        <p>
          Nothing here is financial advice or a recommendation to buy or sell
          anything. Everything published is for education and analysis. If you
          act on it, you do so entirely on your own judgement and at your own
          risk.
        </p>
      </Section>

      <Section title="How signals are made">
        <p>
          Deterministic rules scan candle data for setups. Each candidate is
          then reviewed by a language model that either confirms or rejects it.
          No claim is made about accuracy. The model can be wrong, the rules can
          be wrong, and the market data feeding both can be wrong or late.
        </p>
      </Section>

      <Section title="How outcomes are measured">
        <p>
          Results are reported in R — multiples of the risk between entry and
          stop. Each trade is modelled as a scale-out: one third booked at each
          of the three targets, with the stop moved to breakeven once the first
          target is banked.
        </p>
        <p>
          That means a trade running all the way to the final target is{" "}
          <strong className="text-ink">+2R</strong>, not +3R. Any track record
          quoting +3R for the same trade is using a model nobody could have
          executed from the published levels.
        </p>
      </Section>

      <Section title="Costs are estimates">
        <p>
          Every closed trade is charged an estimated round-trip cost — spread
          plus commission — before it counts: 20&nbsp;bps on crypto,
          2&nbsp;bps on gold, 1.5&nbsp;bps on GBPUSD.
        </p>
        <p>
          These are assumptions, not fills. Real costs depend on venue, fee tier
          and how much the market moved between the signal and the order. Cost
          is a share of price while R is a share of the stop distance, so
          tighter stops carry proportionally more of it.
        </p>
      </Section>

      <Section title="Data caveats">
        <p>
          XAUUSD prices come from the front-month COMEX gold future{" "}
          <code className="font-mono text-xs">GC=F</code>, not spot gold,
          because the market data source has no spot pair. The future trades at
          a basis to spot, and that basis steps when the front month rolls.
        </p>
        <p>
          Nothing detects or adjusts for a roll. On the hourly timeframe the gap
          is small against the stop distance. On the one-minute scalper, whose
          targets are a fraction of a very tight stop, it is not.
        </p>
      </Section>

      <Section title="Risk, and strategies that backtest negative">
        <p>
          Trading risks your capital. You can lose money, including more than
          you expect to.
        </p>
        <p>
          Some strategies here are run despite measuring negative. Over 8.87
          years of verified history,{" "}
          <code className="font-mono text-xs">bbma_reentry</code> scored
          −0.137R per trade and{" "}
          <code className="font-mono text-xs">bbma_extreme</code> −0.153R. They
          are still available because a forward result is the only way to
          confirm or refute a backtest — but they are experiments, and they are
          disclosed as such rather than quietly omitted.
        </p>
      </Section>
    </div>
  );
}

```

- [ ] **Step 4: Write the page that mounts it**

```tsx
// web/src/app/disclaimer/page.tsx
import type { Metadata } from "next";

import { DisclaimerBody } from "@/components/disclaimer/DisclaimerBody";
import { Footer } from "@/components/shared/Footer";
import { Nav } from "@/components/shared/Nav";

export const metadata: Metadata = {
  title: "Disclaimer — Qauntify",
  description:
    "What Qauntify is, how its numbers are produced, and what they do not mean.",
};

export default function DisclaimerPage() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <DisclaimerBody />
      </main>
      <Footer />
    </>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run tests/components/disclaimer/DisclaimerBody.test.tsx`
Expected: PASS, 5 tests

- [ ] **Step 6: Commit**

```bash
git add web/src/components/disclaimer/DisclaimerBody.tsx web/src/app/disclaimer/page.tsx web/tests/components/disclaimer/DisclaimerBody.test.tsx
git commit -m "feat(disclaimer): full disclosure page"
```

---

## Task 6: Move the admin-denied notice to /signals

Must land **before** Task 7. Three call sites send a rejected non-admin to
`/dashboard?admin=denied`, and `dashboard/page.tsx` renders the explanation.
Retiring the route first would swallow that message.

**Files:**
- Create: `web/src/components/shared/AdminDeniedNotice.tsx`
- Modify: `web/src/app/signals/page.tsx`
- Test: `web/tests/components/shared/AdminDeniedNotice.test.tsx`

Its own component file, for the same reason as `DisclaimerBody`: importing
`app/signals/page.tsx` in a test would pull in `SignalsBrowse` and the server
Supabase client.

- [ ] **Step 1: Write the failing test**

```tsx
// web/tests/components/shared/AdminDeniedNotice.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminDeniedNotice } from "@/components/shared/AdminDeniedNotice";

describe("AdminDeniedNotice", () => {
  it("renders nothing when the param is absent", () => {
    const { container } = render(<AdminDeniedNotice admin={undefined} />);
    expect(container.textContent).toBe("");
  });

  it("renders nothing for an unrelated param value", () => {
    const { container } = render(<AdminDeniedNotice admin="hello" />);
    expect(container.textContent).toBe("");
  });

  it("explains the denial when redirected from /admin", () => {
    render(<AdminDeniedNotice admin="denied" />);
    expect(screen.getByText(/admin access is not enabled/i)).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/components/shared/AdminDeniedNotice.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/shared/AdminDeniedNotice"`

- [ ] **Step 3: Write the component**

```tsx
// web/src/components/shared/AdminDeniedNotice.tsx
import { Notice } from "@/components/shared/Notice";

// Someone who typed /admin without being an admin is redirected here. Without
// this they would land on a normal page with no explanation of what happened.
export function AdminDeniedNotice({ admin }: { admin?: string }) {
  if (admin !== "denied") return null;
  return (
    <Notice tone="error" className="mb-5">
      Admin access is not enabled for this account. Ask the owner to add your
      email to ADMIN_EMAILS, then sign out and back in.
    </Notice>
  );
}
```

- [ ] **Step 4: Wire it into the signals page**

In `web/src/app/signals/page.tsx`, add to the imports:

```tsx
import { AdminDeniedNotice } from "@/components/shared/AdminDeniedNotice";
```

Change the `searchParams` type to include `admin`:

```tsx
  searchParams: Promise<{ tab?: string; page?: string; admin?: string }>;
```

Destructure it:

```tsx
  const { tab, page: pageParam, admin } = await searchParams;
```

And render it as the first child of the `<div className="mb-5 shrink-0">`'s parent — directly above that div:

```tsx
          <AdminDeniedNotice admin={admin} />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run tests/components/shared/AdminDeniedNotice.test.tsx`
Expected: PASS, 3 tests

- [ ] **Step 6: Commit**

```bash
git add web/src/components/shared/AdminDeniedNotice.tsx web/src/app/signals/page.tsx web/tests/components/shared/AdminDeniedNotice.test.tsx
git commit -m "feat(signals): carry the admin-denied notice on the public page"
```

---

## Task 7: Repoint every /dashboard reference

**Files:**
- Modify: `web/src/proxy.ts:43`
- Modify: `web/src/app/auth/actions.ts:33`
- Modify: `web/src/app/auth/confirm/route.ts:18,21`
- Modify: `web/src/app/login/page.tsx:30`
- Modify: `web/src/app/admin/actions.ts:22,111`
- Modify: `web/src/app/admin/layout.tsx:32,53`
- Modify: `web/src/lib/admin-guard.ts:25`
- Test: `web/tests/lib/no-dashboard-links.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/lib/no-dashboard-links.test.ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..", "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

describe("retired dashboard routes", () => {
  it("nothing links or redirects to /dashboard any more", () => {
    const offenders = sourceFiles(SRC).filter((file) =>
      /["'`]\/dashboard/.test(readFileSync(file, "utf8")),
    );
    expect(offenders.map((f) => f.slice(SRC.length + 1))).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/lib/no-dashboard-links.test.ts`
Expected: FAIL — lists the dashboard page files plus the ~11 referrers

- [ ] **Step 3: Repoint the non-admin denial call sites**

In `web/src/proxy.ts`, replace:

```ts
        const denied = new URL("/dashboard", request.url);
```

with:

```ts
        const denied = new URL("/signals", request.url);
```

In `web/src/lib/admin-guard.ts:25`, replace `redirect("/dashboard?admin=denied");` with `redirect("/signals?admin=denied");`

In `web/src/app/admin/actions.ts:22`, replace `redirect("/dashboard?admin=denied");` with `redirect("/signals?admin=denied");`

In `web/src/app/admin/actions.ts:111`, replace `revalidatePath("/dashboard");` with `revalidatePath("/signals");`

- [ ] **Step 4: Repoint the auth redirects**

In `web/src/app/auth/actions.ts:33`, replace `redirect("/dashboard");` with `redirect("/signals");`

In `web/src/app/auth/confirm/route.ts`, replace **both** occurrences of `new URL("/dashboard", request.url)` with `new URL("/signals", request.url)`.

In `web/src/app/login/page.tsx:30`, replace `redirect("/dashboard");` with `redirect("/signals");`

- [ ] **Step 5: Repoint the admin layout links**

In `web/src/app/admin/layout.tsx`, replace both `href="/dashboard"` with `href="/signals"`.

- [ ] **Step 6: Run test — it should still fail, on the dashboard pages only**

Run: `cd web && npx vitest run tests/lib/no-dashboard-links.test.ts`
Expected: FAIL, and the listed offenders are now only `app/dashboard/*` and `components/dashboard/DashboardShell.tsx` / `DashboardNav.tsx`. Task 8 removes those.

- [ ] **Step 7: Commit**

```bash
git add web/src/proxy.ts web/src/lib/admin-guard.ts web/src/app/admin/actions.ts web/src/app/admin/layout.tsx web/src/app/auth/actions.ts web/src/app/auth/confirm/route.ts web/src/app/login/page.tsx web/tests/lib/no-dashboard-links.test.ts
git commit -m "refactor(routing): point post-auth and denial redirects at /signals"
```

---

## Task 8: Retire the dashboard routes and /signup

**Files:**
- Delete: `web/src/app/dashboard/page.tsx`
- Delete: `web/src/app/dashboard/markets/page.tsx`
- Delete: `web/src/app/dashboard/war-room/page.tsx`
- Delete: `web/src/components/dashboard/DashboardShell.tsx`
- Delete: `web/src/components/dashboard/DashboardNav.tsx`
- Delete: `web/src/app/signup/page.tsx`
- Modify: `web/next.config.ts`
- Modify: `web/src/app/auth/actions.ts` (remove `signup`)

Real 308 redirects in `next.config.ts`, not `redirect()` inside a page — the
routes should not render at all.

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/lib/retired-routes.test.ts
import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";

describe("retired routes", () => {
  it("permanently redirects every retired route to its public replacement", async () => {
    const redirects = await nextConfig.redirects!();
    const bySource = Object.fromEntries(redirects.map((r) => [r.source, r]));

    for (const [source, destination] of [
      ["/dashboard", "/signals"],
      ["/dashboard/markets", "/markets"],
      ["/dashboard/war-room", "/war-room"],
      ["/signup", "/login"],
    ]) {
      expect(bySource[source]).toBeDefined();
      expect(bySource[source].destination).toBe(destination);
      expect(bySource[source].permanent).toBe(true);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/lib/retired-routes.test.ts`
Expected: FAIL — `nextConfig.redirects is not a function`

- [ ] **Step 3: Add the redirects to next.config.ts**

Replace the whole of `web/next.config.ts` with:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep soft-navigated pages warm in the client router so back/forward and
  // revisiting admin tabs feel instant instead of refetching immediately.
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
  // The dashboard duplicated the public pages once every signal became
  // readable without an account. Permanent so existing links and bookmarks
  // settle, rather than re-resolving on every visit.
  async redirects() {
    return [
      { source: "/dashboard", destination: "/signals", permanent: true },
      { source: "/dashboard/markets", destination: "/markets", permanent: true },
      { source: "/dashboard/war-room", destination: "/war-room", permanent: true },
      { source: "/signup", destination: "/login", permanent: true },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 4: Delete the retired files**

```bash
cd web
git rm src/app/dashboard/page.tsx src/app/dashboard/markets/page.tsx src/app/dashboard/war-room/page.tsx
git rm src/components/dashboard/DashboardShell.tsx src/components/dashboard/DashboardNav.tsx
git rm src/app/signup/page.tsx
```

- [ ] **Step 5: Remove the signup action**

In `web/src/app/auth/actions.ts`, delete the entire `export async function signup(formData: FormData) { ... }` block (starts at line 37, ends at the `redirect("/signup?sent=1");` line and its closing brace).

Then remove the now-unused `headers` import — change:

```ts
import { headers } from "next/headers";
```

Delete that line entirely. Verify `headers` is not used elsewhere in the file first:

Run: `cd web && grep -n "headers" src/app/auth/actions.ts`
Expected: no matches after the deletion

- [ ] **Step 6: Verify nothing still imports the deleted modules**

Run: `cd web && grep -rn "DashboardShell\|DashboardNav\|auth/actions\".*signup\|{ signup }" src/ || echo "clean"`
Expected: `clean`

- [ ] **Step 7: Run the full test suite**

Run: `cd web && npx vitest run`
Expected: PASS, including `no-dashboard-links.test.ts` which now finds zero offenders

- [ ] **Step 8: Typecheck and build**

Run: `cd web && npx tsc --noEmit && npx next build 2>&1 | grep -E "Compiled|error"`
Expected: no TS errors, `✓ Compiled successfully`, and `/dashboard` and `/signup` absent from the route list

- [ ] **Step 9: Commit**

```bash
git add web/next.config.ts web/src/app/auth/actions.ts web/tests/lib/retired-routes.test.ts
git commit -m "refactor(routing): retire the dashboard and public signup"
```

---

## Task 9: Point the footer at the shared strings

**Files:**
- Modify: `web/src/components/shared/Footer.tsx`
- Test: `web/tests/components/shared/Footer.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web/tests/components/shared/Footer.test.tsx
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer } from "@/components/shared/Footer";
import { DISCLAIMER_FOOTER } from "@/lib/disclaimer";

describe("Footer", () => {
  it("shows the shared disclaimer text", () => {
    render(<Footer />);
    expect(screen.getByText(new RegExp(DISCLAIMER_FOOTER.slice(0, 40)))).toBeDefined();
  });

  it("links to the full disclaimer page", () => {
    render(<Footer />);
    const link = screen.getByRole("link", { name: /disclaimer/i });
    expect(link.getAttribute("href")).toBe("/disclaimer");
  });

  // The wording lived in four files with four phrasings before lib/disclaimer.
  // Assert on all three consumers, not just this one: the whole point is that
  // no consumer keeps a private copy that can drift.
  it("no consumer hardcodes its own copy of the wording", () => {
    const src = (...p: string[]) =>
      readFileSync(join(__dirname, "..", "..", "..", "src", ...p), "utf8");

    const footer = src("components", "shared", "Footer.tsx");
    expect(footer).not.toContain("educational and analysis purposes only");
    expect(footer).toContain("DISCLAIMER_FOOTER");

    const bar = src("components", "shared", "DisclaimerBar.tsx");
    expect(bar).not.toContain("Not financial advice");
    expect(bar).toContain("DISCLAIMER_BAR_LONG");
    expect(bar).toContain("DISCLAIMER_BAR_SHORT");

    const layout = src("app", "layout.tsx");
    expect(layout).not.toContain("not financial advice");
    expect(layout).toContain("DISCLAIMER_META");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run tests/components/shared/Footer.test.tsx`
Expected: FAIL — no link named `/disclaimer`, and the source still hardcodes the sentence

- [ ] **Step 3: Update the footer**

In `web/src/components/shared/Footer.tsx`, add to the imports:

```tsx
import { DISCLAIMER_FOOTER } from "@/lib/disclaimer";
```

Add a `Disclaimer` link inside the existing `<div className="flex flex-col gap-2">`, after the Track Record link:

```tsx
              <Link href="/disclaimer" className="text-slate hover:text-accent">
                Disclaimer
              </Link>
```

Replace the closing paragraph:

```tsx
        <p className="mt-10 border-t border-line pt-6 text-xs leading-relaxed text-slate">
          Signals are for educational and analysis purposes only. Not financial
          advice. Trading involves risk. © {new Date().getFullYear()} Qauntify.
        </p>
```

with:

```tsx
        <p className="mt-10 border-t border-line pt-6 text-xs leading-relaxed text-slate">
          {DISCLAIMER_FOOTER} © {new Date().getFullYear()} Qauntify.
        </p>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run tests/components/shared/Footer.test.tsx`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add web/src/components/shared/Footer.tsx web/tests/components/shared/Footer.test.tsx
git commit -m "refactor(footer): read disclaimer wording from the shared module"
```

---

## Task 10: Full verification

**Files:** none

`npm run lint` is a CI step that was missed on a previous push and broke the
build. It runs here before anything leaves the machine.

- [ ] **Step 1: Lint**

Run: `cd web && npm run lint`
Expected: `0 errors`. Warnings about `<img>` are pre-existing and do not fail CI.

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no output

- [ ] **Step 3: Web tests**

Run: `cd web && npx vitest run`
Expected: all files pass

- [ ] **Step 4: Build**

Run: `cd web && npx next build 2>&1 | tail -30`
Expected: `✓ Compiled successfully`; route list contains `/disclaimer` and does not contain `/dashboard` or `/signup`

- [ ] **Step 5: Engine tests (nothing here touches Python, so this is a regression check)**

Run: `cd .. && .venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Confirm the bar renders on a page with no Nav**

Run: `cd web && npm run dev` then load `http://localhost:3000/login`
Expected: the amber bar is at the top with no nav beneath it — the accepted
behaviour for `/login` and `/admin`, which never rendered `Nav`.

Stop the dev server when done.

- [ ] **Step 7: Push**

```bash
git push origin main
```

- [ ] **Step 8: Confirm CI and deploy both go green**

```bash
gh run list --limit 4 --json workflowName,status,conclusion,headSha \
  -q '.[] | "\(.workflowName)  \(.status)  \(.conclusion)  \(.headSha[0:7])"'
```

Expected: `CI success` and `Deploy web to Vercel success` on the pushed SHA. If
the deploy fails on a module it cannot resolve, check `.vercelignore` — its
patterns match at any depth, which has silently dropped `web/**` directories
before.
