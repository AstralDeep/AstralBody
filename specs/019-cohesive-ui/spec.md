# Spec 019: Cohesive Generated UI (US-18)

**Status:** In Progress
**Branch:** `018-cohesive-ui`
**User Story:** As a user, I want a cohesive, unified generated UI instead of the components being sectioned off in their own components.

## Current State

The SDUICanvas renders each agent-generated component (tables, charts, metrics, cards, etc.) inside individual bordered glass-card wrappers. Each card has:
- A drag handle (GripVertical)
- Collapse/expand toggle
- Delete button
- "Pin to dashboard" button
- Fullscreen button
- Card border and padding

This creates visual segmentation — each component feels like a standalone widget rather than part of a unified dashboard. When a user queries "show me all patient vitals," the output is 3-5 separate cards (BP chart, heart rate metric, temp table, etc.) rather than a single cohesive dashboard.

## Problem

1. **Visual Fragmentation:** Each component is boxed in its own card, making the UI feel like a widget collection rather than a report
2. **Chrome Overload:** Every component shows drag handles, collapse toggles, delete buttons simultaneously — visual noise
3. **Component Islands:** Related components (e.g., all vitals) appear disconnected rather than as a unified group
4. **Auto-condense Friction:** The existing condense feature uses an LLM to merge similar components but requires manual triggering or overflow detection; it's reactive, not proactive

## Proposed Changes

### 1. Unified Chrome Pattern
- **Remove individual card borders, drag handles, collapse buttons, and delete buttons from components in the canvas**
- Replace with a **single toolbar** that appears above/beside the component when hovered
- Components are borderless by default — just raw content in a continuous scroll
- Toolbar items fade in on hover: drag handle, delete, fullscreen

### 2. Hover-Activated Controls
- Individual component controls only appear on **hover of each component area**
- Default view: clean, borderless, chromeless content
- Hover: subtle highlight + small floating toolbar in top-right corner

### 3. Smart Auto-Grouping
- When components share the same `chat_id` and arrive within a short window, render them **adjacent without dividers**
- Add a subtle group header or separator between chat-response groups
- Components that belong together (same chat response) should look like parts of a single report

### 4. Remove Individual Collapse
- Replace per-component collapse with **global compact/expand toggle** in the canvas toolbar
- Default: all expanded
- Compact mode: reduces visual weight of all components (smaller metrics, shorter tables)

### 5. Visual Separation Between Chat Responses
- Add a subtle horizontal rule or timestamp divider between groups of components from different chat messages
- This gives the "flow" of a report while still distinguishing individual responses

## Files to Touch

1. **`frontend/src/components/SDUICanvas.tsx`** — Major refactor:
   - Remove per-component card wrapper, collapse, drag handle, delete from render
   - Add hover-activated floating toolbar
   - Add response-group dividers based on `chat_id` grouping
   - Add global compact/expand toggle instead of per-component collapse

2. **`frontend/src/components/DynamicRenderer.tsx`** — Minor changes:
   - Components may need spacing adjustment when not inside cards

3. **`frontend/tests/SDUICanvas.test.tsx`** or related test files — Update component mount assertions

## Constitution Compliance

| Principle | Assessment |
|-----------|-----------|
| I — No New Dependencies | ✅ Zero new npm packages |
| II — HIPAA | ✅ No PHI handling changes |
| III — Audit Trail | ✅ UI change only, audit is backend |
| IV — Agent Autonomy | ✅ Agents still emit UI primitives; rendering is presentation only |
| V — No Third-Party Libs | ✅ Pure React/Tailwind/framer-motion only |
| VI — Accessibility | ✅ Keep ARIA labels; hover controls still reachable via keyboard focus |
| VII — Extensibility | ✅ Toolbar pattern is extensible; new controls can be added to the toolbar |
| VIII — Performance | ✅ Removing wrappers reduces DOM nodes; hover CSS is GPU-compositable |
| IX — Database Schema | ✅ No DB changes |
| X — Testing | ✅ Update tests for new rendering structure |

## Success Criteria

1. Components render without individual card chrome — no borders, drag handles, or delete buttons visible by default
2. Hovering a component shows a floating toolbar with drag/delete/fullscreen controls
3. Components from the same chat response render as a contiguous block without dividers
4. A subtle divider appears between groups of components from different chat messages
5. Global compact toggle replaces individual collapse/expand
6. All existing component types still render correctly
7. Tests pass without regression beyond expected UI structure changes
8. Drag-and-drop combination between components still works