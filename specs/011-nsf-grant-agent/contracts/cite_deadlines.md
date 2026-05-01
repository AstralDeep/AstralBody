# MCP Tool Contract: `cite_deadlines`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["cite_deadlines"]`

## Purpose

Standalone deadline-citation tool. Returns all three relevant dates (LOI 2026-06-16, full proposal 2026-07-16, internal ~2026-07-09) outside any drafting flow. Implements FR-020 and US3 Acceptance Scenario 4 / SC-014.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "include": {
      "type": "array",
      "items": {"type": "string", "enum": ["loi", "full_proposal", "internal"]},
      "description": "Optional: subset of deadlines to cite. Defaults to all three."
    }
  }
}
```

## Output

`_ui_components` payload:

- `Card(title="NSF 26-508 Critical Deadlines")` containing a `Table` with columns: deadline, date, submission path, notes. Row order matches `DEADLINES` ordering.

## Refusal paths

- If `include` is supplied but contains an unknown key → `Alert(variant="error", message="Unknown deadline key. Use one or more of: loi, full_proposal, internal.")`.

## Post-processing invariants

1. When called with no `include` parameter, the output Table contains all three deadlines.
2. Each row's `date` field exactly matches the ISO date in `DEADLINES[key].date_iso`.
3. The full-proposal row's `submission path` MUST mention "AOR signature required".

## Test expectations

- Unit: default call returns all three rows in canonical order.
- Unit: `include=["loi"]` returns one row.
- Unit: unknown key → canonical error Alert.
- Integration: round-trip via `MCPServer.process_request` returns the expected Card.
