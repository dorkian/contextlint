# Product

## Register

product

## Users

Two audiences, one screen:

1. **Ash, running it locally.** He points it at a project (usually his own vault or one of his repos), reads the always-on cost, the security findings, and what's dead weight, then acts on it — either from the UI (`Apply Fixes`) or by copying a file path into an editor.
2. **A recruiter or interviewer, looking over his shoulder or at a screenshot.** contextlint is a technical-depth portfolio piece in an active job search (Neo4j, Reflow pipelines). This dashboard is one of the things that gets opened during a screen-share or linked from the README. It has to survive that look: legible in a five-second scan, not just "functional if you already know what it does."

Both audiences are served by the same design, not two different modes: precision that reads as competence to the second audience, and stays genuinely fast and correct for the first.

## Product Purpose

A local dashboard for the `contextlint` CLI: audits what an AI coding assistant loads before the user types a word (always-on token cost, dead weight, MCP security risk) and presents it as something a person can actually read at a glance — not a wall of JSON, not a raw terminal dump. Success is: open it, understand your context budget and your biggest risk within seconds, and know exactly what to fix and how.

## Brand Personality

**Precise, restrained, evidence-first** — inherited directly from the CLI and the README, not invented separately. The tool's whole credibility argument is that its numbers are reproducible and its incumbents' aren't; a dashboard that oversells itself with gradient hero-metrics and vague confidence would undercut that argument in the same breath it's making it.

Within that restraint: **stunning is earned through craft, not decoration.** No ceiling on visual ambition — but the ambition spends itself on typographic hierarchy, spacing, the one diagram that actually explains the mechanism, and flawless execution of the existing validated palette, not on gimmicks. The explicit bar: readable in one quick glance. The story (budget, risk, what's safe vs. worth reviewing) has to land before anyone scrolls.

## Anti-references

- Generic SaaS analytics dashboard: gradient hero metrics, glassy cards, a rainbow of KPI pills, side-stripe accent borders as the default card treatment.
- Anything that asks the reader to work to find the headline number. The always-on cost and the risk split are the whole point; they cannot be buried below the fold or in a wall of equally-weighted stat tiles.
- Decorative or page-load motion. No stagger-cascade "watch it load" sequence, no scroll-triggered reveals for their own sake.

## Design Principles

1. **The overview is the product.** A cold reader gets the full story — cost, risk, safe-vs-review split — from the first screen, before any scrolling or interaction. Everything below the fold is detail for someone who wants to act, not the pitch.
2. **Motion conveys state, never decoration.** Hover, filter change, data refresh, panel reveal — 150–250ms, always with a `prefers-reduced-motion` fallback. No orchestrated entrance sequence on mount.
3. **Never claim what isn't measured.** The CLI's own rule extends to the UI: a stat that's an estimate says so; a cost that's unmeasured (unprobed MCP schemas) is labeled unmeasured, not silently omitted or rounded into the total.
4. **One accent, spent deliberately.** The existing validated palette (categorical hues for used/unused/mcp/memory, semantic severity colors) already does the work. New surface area reuses it rather than introducing a second visual language.
5. **The tool disappears into the task.** Familiar product-UI vocabulary (buttons, filters, modals) over invented affordances. Delight is saved for the one moment that earns it — the overview diagram — not spread thin across every card.

## Accessibility & Inclusion

WCAG AA as the floor: visible `:focus-visible` states on every interactive element (currently missing — first fix), 4.5:1 body text contrast in both themes, keyboard-operable filters/modals/toggles. Respects `prefers-reduced-motion` for every animation, no exceptions. No special accessibility requirements beyond that were raised.
