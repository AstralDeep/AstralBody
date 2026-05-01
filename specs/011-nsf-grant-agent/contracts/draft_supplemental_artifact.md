# MCP Tool Contract: `draft_supplemental_artifact`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["draft_supplemental_artifact"]`

## Purpose

Produce a permitted supplemental document — PAPPG-format Letter of Collaboration for a named partner, a Data Management Plan, or a Mentoring Plan (only when the user confirms postdoc/grad-student inclusion in the budget). Refuse any prohibited artifact with a tool-level error. Implements FR-012.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "artifact_key": {
      "type": "string",
      "enum": [
        "letter_of_collaboration",
        "data_management_plan",
        "mentoring_plan",
        "letter_of_support",
        "additional_narrative"
      ],
      "description": "Last two are prohibited and will be refused."
    },
    "partner_key": {
      "type": "string",
      "description": "Required when artifact_key=letter_of_collaboration. Must match a key in KY_PARTNERS or a free-string partner name supplied by the user."
    },
    "partner_contribution": {
      "type": "string",
      "description": "Optional: explicit text describing what the partner contributes. If omitted for a known partner, the tool uses unique_contribution from KY_PARTNERS."
    },
    "budget_includes_postdocs_or_grad_students": {
      "type": "boolean",
      "default": false,
      "description": "Required true when artifact_key=mentoring_plan."
    }
  },
  "required": ["artifact_key"]
}
```

## Output

`_ui_components` payload:

- For `letter_of_collaboration`: `Card(title="Letter of Collaboration — <Partner Name>")` containing a `Text` block in PAPPG format. The body MUST stay within PAPPG content limits (no project-quality endorsements, no "letter of support" framing).
- For `data_management_plan`: a multi-section `Card` covering data the Hub will collect (training participation, business-assistance outcomes, convening attendance, evaluation data), a common cross-partner instrument, retention, sharing policy, roles, and access controls.
- For `mentoring_plan`: a `Card` describing the mentoring approach for the postdocs/grad-students named, only when `budget_includes_postdocs_or_grad_students=true`.

## Refusal paths

- `artifact_key` ∈ `{"letter_of_support", "additional_narrative"}` → `Alert(variant="error", message="The NSF 26-508 solicitation permits only Letters of Collaboration (PAPPG format), a Data Management Plan, and — if the budget includes postdocs or graduate students — a Mentoring Plan. Letters of Support and other narrative supplements are prohibited.")`.
- `artifact_key="mentoring_plan"` AND `budget_includes_postdocs_or_grad_students=false` → `Alert(variant="error", message="A Mentoring Plan is required only if the budget includes postdocs or graduate students. Confirm the budget structure before generating one.")`.
- `artifact_key="letter_of_collaboration"` AND `partner_key` missing → `Alert(variant="error", message="Specify a partner.")`.

## Post-processing invariants

1. Letters of Collaboration MUST NOT contain endorsement language characteristic of Letters of Support (substring scan: "strongly support", "endorse", "highly recommend", etc.).
2. Letters of Collaboration MUST name a specific contribution (no generic "we will support this work" language).
3. Data Management Plan MUST mention the common cross-partner instrument and an independent evaluation component (carried over from Section 4 framing).

## Test expectations

- Unit: every prohibited `artifact_key` returns the canonical error Alert with correct text.
- Unit: Mentoring Plan condition flag enforced.
- Unit: LOC for a known partner key includes that partner's `unique_contribution`.
- Integration: round-trip via `MCPServer.process_request` for each happy-path artifact returns the expected `Card`.
