# MCP Tool Contract: `gap_check_section`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["gap_check_section"]`

## Purpose

Take pasted draft text for a section and return a structured gap analysis: (a) missing required sub-elements, (b) named verdicts against NSF review criteria (Intellectual Merit, Broader Impacts, plus the solicitation-specific criteria), (c) tone / framing violations, (d) suggested rewrites for the weakest passages. Implements FR-011, plus the review-criteria coverage in User Story 2.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "section_key": {
      "type": "string",
      "enum": ["loi_synopsis", "section_1", "section_2", "section_3", "section_4", "section_5"]
    },
    "draft_text": {"type": "string"},
    "include_rewrites": {
      "type": "boolean",
      "default": true,
      "description": "When true, return a 'Suggested Rewrites' card with rewritten text for the weakest passages."
    }
  },
  "required": ["section_key", "draft_text"]
}
```

## Output

`_ui_components` payload:

- `Card(title="Required Sub-Element Coverage")` — `Table` with two columns: required sub-element, present (✓ / ✗ / partial). Drives SC-001 verification.
- `Card(title="Review Criteria Verdicts")` — for each applicable criterion (Intellectual Merit, Broader Impacts, solicitation-specific criteria from the spec's "Additional Solicitation-Specific Criteria"), a one-paragraph verdict and a one-line confidence indicator.
- `Card(title="Framing & Tone Violations")` — a `List_` of detected violations matching `FRAMING_RULES.violation_pattern_hints` with the offending substring quoted.
- `Card(title="Suggested Rewrites")` — only when `include_rewrites=true`. Pairs each weak passage with a stronger replacement.
- For `section_4` only: an extra `Card(title="Metric Coverage")` enumerating which NSF-required metrics are present, which extended layers are present, whether a Year 1 baseline is stated, and whether an independent evaluation component appears.

## Refusal paths

- Empty `draft_text` → `Alert(variant="error", message="No draft supplied. Provide section text to gap-check.")`.

## Post-processing invariants

1. Every entry in `SECTION_REQUIREMENTS[section_key]` appears as a row in the coverage Table.
2. Verdicts cite the specific solicitation criterion language (one of: "clear vision and approach", "statewide convening and coordination capacity", "understanding of current Kentucky AI efforts", "realistic milestones, measurable outcomes, evidence-based scaling", "credible strategies for mobilizing additional resources beyond NSF funding").
3. For `section_4`: every NSF-required metric is named in the Metric Coverage card, present-or-absent.

## Test expectations

- Unit: golden test where a draft missing governance language for Section 2 yields a "✗" row for the governance sub-element.
- Unit: golden test where Section 4 with no baseline statement yields "Year 1 baseline: missing".
- Integration: round-trip emits all expected Cards.
