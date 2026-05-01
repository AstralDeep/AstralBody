# MCP Tool Contract: `prioritize_page_budget`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["prioritize_page_budget"]`

## Purpose

Advise on prioritization within the 15-page narrative limit when current section drafts collectively exceed the budget. Produces a per-section current-vs-target page allocation table, names which sub-elements are required (and protected) vs. discretionary, and proposes an ordered cut list that respects all required sub-elements. Implements FR-016 and US2 Acceptance Scenario 4 / SC-013.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "current_pages": {
      "type": "object",
      "description": "Map of section_key → current page count (float).",
      "additionalProperties": {"type": "number"}
    },
    "drafts": {
      "type": "object",
      "description": "Optional: map of section_key → current draft text. When supplied, the tool uses the text to infer which sub-elements are present and therefore which are candidates for compression vs. cut.",
      "additionalProperties": {"type": "string"}
    }
  },
  "required": ["current_pages"]
}
```

## Output

`_ui_components` payload:

- `Card(title="Page Budget Status")` with a `Table` of columns: section, current pages, target pages, delta. A summary row shows the total vs. the 15-page limit.
- `Card(title="Required Sub-Elements (Protected)")` enumerating, per section, the sub-elements from `SECTION_REQUIREMENTS` that MUST be preserved.
- `Card(title="Recommended Cut Order")` — an ordered `List_` of cuts with rationale for each (e.g., "Section 5: trim sustainability narrative from 1.2 to 0.8 pages — discretionary elaboration beyond required sub-elements").
- An `Alert(variant="info")` if `sum(current_pages) <= 15` ("No cuts required; current allocation fits the 15-page limit").
- An `Alert(variant="warning")` if any single section's `current_pages` falls below `0.5 × target_pages` (under-investment in a required section).

## Refusal paths

- If any key in `current_pages` is not in `{"section_1"..."section_5"}` → `Alert(variant="error", message="Unknown section key.")`.
- If any value in `current_pages` is negative → `Alert(variant="error", message="Page counts must be non-negative.")`.

## Post-processing invariants

1. Recommended cuts NEVER target text matching a sub-element listed in `SECTION_REQUIREMENTS[section_key]` (verified by substring scan when `drafts` are supplied; verified by exclusion otherwise).
2. The recommended cut list, when applied, MUST bring the projected total to ≤ 15 pages.
3. Target pages per section are sourced from `PAGE_BUDGET[section_key].target_pages` (no per-call recomputation).

## Test expectations

- Unit: a 17-page input with bloated Section 5 yields a cut list that targets Section 5 first.
- Unit: a 14-page input yields the "no cuts required" Alert.
- Unit: a 15-page input where Section 1 is at 0.8 pages (under target) yields the under-investment warning.
- Unit: invalid section_key in input → canonical error Alert.
- Integration: round-trip via `MCPServer.process_request` returns the expected three Cards.
