# MCP Tool Contract: `techaccess_scope_check`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["techaccess_scope_check"]`

## Purpose

Classify an arbitrary user request as in-scope (NSF 26-508 Coordination Hub Kentucky proposal — primary), sibling-but-different (National Coordination Lead OTA, AI-Ready Catalyst Award Competition), or out-of-family. Provide a redirect message for out-of-family requests and a framing-change alert for sibling requests. Used both as a standalone tool and as a precondition gate inside the other five tools. Implements FR-001 and the off-topic edge cases.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "user_request": {
      "type": "string",
      "description": "The free-text user message to classify."
    }
  },
  "required": ["user_request"]
}
```

## Output

`_ui_components` payload:

- `Card(title="Scope Decision")` containing a `Text` line stating one of:
  - `"In scope: NSF 26-508 Coordination Hub (Kentucky)."`
  - `"In scope but different mechanism: National Coordination Lead (Other Transaction Agreement)."`
  - `"In scope but different mechanism: AI-Ready Catalyst Award Competition."`
  - `"Out of scope. Redirecting back to the Kentucky Coordination Hub proposal."`
- For sibling cases: an `Alert(variant="info")` listing the framing differences (mechanism, deadlines, page limits, review criteria) so callers know not to reuse Hub-specific language.
- For out-of-family: an `Alert(variant="warning", message="This request is outside the NSF TechAccess: AI-Ready America family. Returning focus to the Kentucky Coordination Hub proposal.")`.

## Classification heuristics

The tool combines deterministic substring checks (e.g., "national coordination lead", "OTA", "catalyst", "Kentucky", "Hub", "26-508", "TechAccess", "AI-Ready America") with the existing LLM classification path. Deterministic matches win; the LLM is consulted only when keyword evidence is ambiguous, and the deterministic decision is logged with `logger.info`.

## Refusal paths

- Empty `user_request` → `Alert(variant="error", message="No request supplied.")`.

## Post-processing invariants

1. Output always includes exactly one classification line.
2. For `out_of_family`, no draft content is produced.
3. For sibling cases, the framing-difference alert is always present.
4. For primary, no extra alert is added.

## Test expectations

- Unit: golden inputs covering all four classifications.
- Unit: ambiguous input falls back to LLM classifier and records a `logger.info` with the chosen branch.
- Integration: round-trip via `MCPServer.process_request` returns the right Card for each classification.
- Reuse test: another tool calling `techaccess_scope_check` internally and short-circuiting on `out_of_family` is exercised in `test_techaccess_integration.py`.
