# MCP Tool Contract: `draft_loi`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["draft_loi"]`

## Purpose

Draft the LOI title and/or one-page synopsis. Implements FR-013, FR-014, plus the LOI scope of FR-002.

**Canonical synopsis path**: `draft_loi(produce="synopsis", ...)` and `draft_proposal_section(section_key="loi_synopsis")` MUST produce identical synopsis output. To enforce this, `draft_proposal_section` delegates internally to `draft_loi(produce="synopsis", ...)` whenever `section_key="loi_synopsis"`. The shared synopsis builder lives in a private module-level helper `_build_loi_synopsis(...)` in `mcp_tools.py` so both tools call it directly.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "produce": {
      "type": "string",
      "enum": ["title", "synopsis", "both"],
      "default": "both",
      "description": "Which LOI artifact to draft."
    },
    "descriptive_phrase": {
      "type": "string",
      "description": "Optional: a phrase the user wants in the title after the required prefix. Tool will reject acronyms."
    },
    "pi_email": {
      "type": "string",
      "description": "Optional PI email to surface in the LOI's PI/contact field guidance."
    },
    "senior_personnel": {
      "type": "array",
      "items": {"type": "object"},
      "description": "Optional list of {name, affiliation, role} dicts for PI / co-PIs / senior personnel / sub-awardees."
    },
    "participating_organizations": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Optional list of all institutions and community partners; defaults to the likely Kentucky partnership architecture if omitted."
    }
  }
}
```

## Output

`_ui_components` payload:

- Title block: `Card(title="LOI Title", content=[Text(...)])`. Text MUST start with exactly `Kentucky Coordination Hub:` and contain no acronyms.
- Synopsis block: `Card(title="LOI Synopsis", content=[Text(...)])` ≤ ~600 words. Functions as compressed Section 1 + Section 2 (FR-014).
- A small `Table` listing PI / Co-PIs / Senior Personnel and Participating Organizations from the inputs (or working-assumption defaults from `KY_PARTNERS`).
- An `Alert(variant="info")` reminding the team of the LOI deadline (June 16, 2026) and the prohibition on supplementary documents in the LOI.

## Refusal paths

- If `descriptive_phrase` contains forbidden acronyms (`NSF`, `AI`, `UK`, `KCTCS`, `CPE`, `COT`, `KY`, `KDE`, `SBDC`, etc.) → `Alert(variant="error", message="LOI title must not contain acronyms; expand them.")`. The tool offers an auto-expanded variant and asks the user to confirm.

## Post-processing invariants

1. Title starts with `LOI_RULES["title_prefix"]` exactly.
2. Title contains no token from a hard-coded acronym disallow-list.
3. Synopsis is ≤ a token budget that approximates one page (default ~650 tokens).
4. Synopsis covers `LOI_RULES["synopsis_must_cover"]` (Section-1-compressed AND Section-2-compressed content).
5. PI/personnel block uses long-form names for institutions on first reference.

## Test expectations

- Unit: title-prefix and acronym checks pass / fail correctly on adversarial inputs.
- Unit: synopsis word count is bounded.
- Integration: round-trip via `MCPServer.process_request` returns the expected two `Card`s.
