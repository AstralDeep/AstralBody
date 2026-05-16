# UX Polish — Browser Audit Fixes

**Branch:** `023-ux-polish`
**US:** Cross-cutting (no single US — addresses issues found in UI audit)
**Status:** In Progress

## Background

A comprehensive browser-based UI audit of the staging deployment revealed four actionable UX issues. All six merged user stories (US-16 through US-22) are functional with zero crashes or console errors, but the user experience is rough in specific areas.

## Findings

### 1. Agent Card — Missing Permissions Affordance
Clicking an agent card opens the permissions modal (tool-level configuration), but there is no visual indicator — no gear icon, no "Configure" text, no hover hint. Users discover this by accident.

### 2. No Typing/Loading Indicator
When a user sends a query, there is a 4-8 second gap before the agent response appears. During this time, the UI shows nothing — no "thinking" animation, no progress bar, no loading state. Users may assume their message wasn't sent.

### 3. Rapid-Query Response Mismatch
When messages are sent in rapid succession (less than the agent response time), responses can appear out of order. The textarea clears correctly but the response stream may still be flushing the previous query's output.

### 4. Compact Toggle Inconsistency
The compact toggle button renders only in certain UI states. It appears to require component content in the canvas to be visible, but should be consistently available when chat messages exist.

## Fixes

### Fix 1: Add gear icon to agent cards
- Add a small gear/cog icon on each agent card that explicitly shows "click to configure tools"
- The gear triggers `openPermissionsModal(agent.id)` — same as card click
- Keeps card click working for backward compatibility

### Fix 2: Add loading indicator to chat
- Show a "..." animated dots indicator in the chat when a message is sent but no response has arrived yet
- Use the existing WebSocket message flow to detect "sent but not responded"
- Clean up indicator when agent responds or on timeout (30s)

### Fix 3: Queue rapid messages
- If a message is being processed (indicator visible), queue subsequent messages
- Process queue in order — send next only after current response completes
- Prevent overlapping responses

### Fix 4: Compact toggle always visible
- Render the compact toggle in the chat toolbar whenever chat messages > 0
- Not just when DynamicRenderer has content

## Constitution Check (v1.1.0)

| Principle | Status |
|---|---|
| I. Agent Sovereignty | N/A — UI-only changes |
| II. Privacy & PHI | N/A — no data changes |
| III. Audit Trail | N/A |
| IV. Security | N/A — no new attack surface |
| V. No New Dependencies | ✅ Zero new libraries |
| VI. Tool Isolation | N/A |
| VII. Credential Safety | N/A |
| VIII. User Control | ✅ Improved — clear affordances |
| IX. Database Integrity | N/A |
| X. Error Resilience | ✅ Improved — loading states + queueing |