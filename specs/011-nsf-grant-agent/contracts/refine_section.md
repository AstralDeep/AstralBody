# MCP Tool Contract: `refine_section`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["refine_section"]`

## Purpose

Take pasted draft text and return a strengthened version that fixes tone violations (direct-delivery framing, overpromising), tightens prose, replaces generic "AI training" language with literacy/proficiency/fluency-anchored phrasing, and grounds vague claims in Kentucky-specific anchors. Implements FR-005, FR-006, FR-009, FR-010, FR-011, FR-017, FR-018.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "section_key": {
      "type": "string",
      "enum": ["loi_synopsis", "section_1", "section_2", "section_3", "section_4", "section_5"]
    },
    "draft_text": {
      "type": "string",
      "description": "The user's existing draft text to refine."
    },
    "preserve_factual_claims": {
      "type": "boolean",
      "default": true,
      "description": "When true, the refiner preserves user-supplied factual claims (named partners, numbers, dates) verbatim and does not invent replacements."
    }
  },
  "required": ["section_key", "draft_text"]
}
```

## Output

`_ui_components` payload with two columns side-by-side (rendered as two Cards via existing primitives):

- `Card(title="Refined Draft")` — the strengthened text.
- `Card(title="What Changed and Why")` — a `List_` of named edits, each citing the framing rule it addresses (e.g., `coordinator_not_builder`, `no_overpromise_innovation_or_econ_dev`, `prose_over_bullets`, AI-literacy-level mapping).

## Refusal paths

- If `draft_text` is empty → `Alert(variant="error", message="No draft supplied. Use draft_proposal_section to start from scratch.")`.

## Post-processing invariants

1. Refined output retains every `required_subelement` for the section that was already present in the input draft (no regression).
2. Refined output flags and rewrites any string matching `FRAMING_RULES.violation_pattern_hints` for direct-delivery / overpromise.
3. If `preserve_factual_claims=true`, named entities (partner organizations, numbers, dates) present in the input MUST appear unchanged in the refined output.
4. Every training reference in the refined output names both an audience and a literacy/proficiency/fluency level.

## Test expectations

- Unit: golden tests with adversarial input ("CAAI will deliver AI training to all KCTCS students") → refined output reframes as coordinator/convener and maps to a level + audience.
- Unit: number/date preservation when `preserve_factual_claims=true`.
- Integration: round-trip yields both expected Cards.
