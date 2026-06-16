# Feature Specification: Server-Driven Cross-Device Loading Skeleton

**Feature Branch**: `037-sdui-skeleton-loading`
**Created**: 2026-06-16
**Status**: In progress
**Input**: User request: "probably need to add a SDUI/skeleton for chat history. just make sure it will work across platforms and devices, not just web."

## Overview

Add a **server-driven `skeleton` loading primitive** — a content-free shimmer placeholder shown while a surface (the chat-history list, a transcript, the workspace) loads. Because AstralBody is server-driven (Constitution II: *astralprims defines → orchestrator renders → ROTE adapts*) and the project rule is **never web-only UI**, the skeleton is a real primitive rendered by the orchestrator and **adapted per device by ROTE** — not a web-client loading hack. It therefore works across every ROTE target: browser/tablet/TV (full shimmer), mobile/watch (capped row count), and voice (spoken "Loading…").

The web client already *ignores* `history_list` ("not needed for the core flow"), so there is no web-only history rendering to unwind — the correct foundation is this primitive, which any surface can emit.

## What this delivers (this increment)

| Piece | Detail | Status |
|-------|--------|--------|
| **Renderer** | `render_skeleton` in `backend/webrender/renderer.py` — registered in `PRIMITIVE_RENDERERS` (auto-joins `allowed_primitive_types()`); emits `role=status` + `aria-busy` + an `sr-only` label; variants `chat-history`/`list`, `card`, `lines`; `count` rows (bounded 1–12); all class names whitelisted, `label` escaped → safe by construction | ✅ done |
| **ROTE adaptation** | `backend/rote/adapter.py` — `_adapt_skeleton` caps rows on watch (3) / mobile (5), passes through browser/tablet/TV; `_extract_text` makes VOICE speak the label ("Loading…") | ✅ done |
| **CSS** | `.astral-skeleton-line` shimmer keyframes in `backend/webrender/static/astral.css`, honouring `prefers-reduced-motion` | ✅ done |
| **Builder** | `skeleton_component(variant, count, label)` — `variant='chat-history'` for the chat list; emit like any primitive | ✅ done |
| **Tests** | `backend/tests/test_skeleton.py` (12 cases): renderer structure/a11y/bounds/escaping/dispatch/builder + ROTE voice/watch/mobile/browser/tv | ✅ done |

## Cross-device behavior (the "not just web" requirement)

- **Browser / Tablet / TV** — full shimmer skeleton, row count unchanged.
- **Mobile** — capped to 5 placeholder rows.
- **Watch** — capped to 3 rows.
- **Voice** — collapses to a spoken `text` component ("Loading chats…"), via the existing ROTE voice-extraction path.
- **Accessibility** — `role=status` + `aria-live=polite` + `sr-only` label on every surface; `prefers-reduced-motion` disables the animation. New render targets inherit the primitive automatically (add a renderer, not a primitive).

## How a surface uses it

```python
from webrender.renderer import skeleton_component
# while the chat-history list loads, send a skeleton; replace it (ui_upsert /
# ui_render) when the real list arrives:
skeleton_component(variant="chat-history", count=6, label="Loading your chats…")
```

## Constraints & posture

- **SDUI mandate honored**: a new primitive added the sanctioned way (dict-based renderer + ROTE, per the feature-029 pattern) — no astralprims wheel change required, no web-only logic. New device targets get it for free.
- **No new third-party runtime libraries; no schema change.**
- **Safe by construction**: fixed class-name whitelist, escaped label, bounded count; `render_one` already wraps every renderer fail-safe.
- **Tests**: ≥90% changed-code coverage; renderer + ROTE + a11y + XSS + every device target covered. Existing ROTE/webrender suites green (136 passed).

## Out of scope (follow-on)

Wiring the skeleton into a *server-driven chat-history list surface* (so the history list itself is SDUI, then the skeleton shows while it loads) is a larger follow-on: the history list is currently sent as raw `history_list` data and not server-rendered. This increment ships the reusable primitive that surface will use; building the SDUI history surface + emitting/replacing the skeleton is the next step.

## Assumptions

- The shell self-hosts Tailwind (per `renderer.py`), so the layout utility classes used by the skeleton resolve; the shimmer itself is custom `.astral-skeleton-line` CSS.
- Surfaces emit/replace the skeleton via the existing `ui_render`/`ui_upsert` wire; no new protocol message is required for the primitive itself.
