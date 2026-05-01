# Quickstart: NSF TechAccess Grant Writing Agent

This is a developer-and-team quickstart for the NSF TechAccess (NSF 26-508) capability that lives inside the existing `grants` agent.

## Who this is for

- **Proposal team members** at the University of Kentucky working on the Kentucky Coordination Hub LOI (due June 16, 2026) and full proposal (due July 16, 2026; internal deadline ~July 9, 2026).
- **Backend developers** maintaining `backend/agents/grants/`.

## What you get

The existing `grants` agent now also exposes six new MCP tools dedicated to NSF 26-508:

| Tool | What it does |
|------|--------------|
| `draft_proposal_section` | Drafts any of Sections 1–5 (or LOI synopsis), using the exact required heading and addressing every required sub-element. |
| `draft_loi` | Produces the LOI title (must begin "Kentucky Coordination Hub:") and/or the one-page synopsis. |
| `refine_section` | Strengthens a pasted draft — fixes direct-delivery framing, replaces generic "AI training" with literacy/proficiency/fluency-anchored phrasing, and tightens prose. |
| `gap_check_section` | Returns a structured coverage table against required sub-elements + verdicts against NSF review criteria + a list of framing/tone violations. |
| `draft_supplemental_artifact` | Produces Letters of Collaboration (PAPPG format), Data Management Plan, or a Mentoring Plan (only if budget includes postdocs/grad-students). Refuses prohibited artifacts (Letters of Support, etc.). |
| `techaccess_scope_check` | Classifies a user request as primary Hub / sibling (National Lead OTA / Catalyst) / out-of-family. Produces a redirect for out-of-family requests. |

## Team-facing usage (P1 user story flow)

1. Start a chat that has the `grants` agent enabled.
2. Tell the agent which section you're working on. Be explicit, e.g.:
   > "Draft Section 4 (Work Plan, Milestones, and Performance Metrics) for the Kentucky Coordination Hub. Our partners are UK, KCTCS, CPE, COT, UK Cooperative Extension, KentuckianaWorks, and KY SBDC. We have not yet established baselines."
3. The agent calls `draft_proposal_section(section_key="section_4", ...)`. The output Card uses the exact required heading, names every NSF-required metric, and includes reach / depth / system-change layers.
4. Review the draft. To strengthen it, paste it back and say:
   > "Refine this Section 4 — preserve our partner roster but fix any direct-delivery framing."
5. The agent calls `refine_section(...)` and returns a side-by-side "Refined Draft" + "What Changed and Why" pair.
6. To verify reviewer-readiness, ask:
   > "Gap-check this Section 4 against NSF review criteria."
7. The agent calls `gap_check_section(...)` and returns a coverage table, review-criterion verdicts, and framing/tone violations.

## Team-facing usage (P3 supplementals)

```
"Generate a PAPPG-format Letter of Collaboration for KCTCS."
→ tool: draft_supplemental_artifact(artifact_key="letter_of_collaboration", partner_key="kctcs")

"Draft a Data Management Plan for the Hub."
→ tool: draft_supplemental_artifact(artifact_key="data_management_plan")

"Write a Mentoring Plan." (when budget includes postdocs)
→ tool: draft_supplemental_artifact(artifact_key="mentoring_plan",
                                    budget_includes_postdocs_or_grad_students=true)

"Write me a Letter of Support for UK leadership."
→ refused with Alert(variant="error", ...) explaining the supplemental rules.
```

## What the agent will refuse

- Anything outside NSF 26-508 / TechAccess: AI-Ready America (other NSF solicitations, other funders, unrelated coding tasks).
- Any prohibited supplemental artifact (Letters of Support, additional narrative documents).
- LOI titles that contain acronyms.
- Mentoring Plans when the user has not confirmed the budget includes postdocs or graduate students.

For **National Coordination Lead OTA** and **AI-Ready Catalyst Award Competitions** (siblings inside the family), the agent helps but emits a framing-change alert reminding you the rules differ.

## Developer setup

No new environment variables. No new dependencies. No DB migrations. The capability is delivered by changes to:

```
backend/agents/grants/
├── grants_agent.py              # description + skill_tags expanded
├── mcp_tools.py                 # 6 new tool entries in TOOL_REGISTRY
└── nsf_techaccess_knowledge.py  # NEW knowledge module
```

To run the existing grants-agent test suite locally:

```powershell
cd backend
pytest tests/agents/grants/ -v
```

The new test files (added in implementation, not in this plan) will be:

- `backend/tests/agents/grants/test_nsf_techaccess_knowledge.py`
- `backend/tests/agents/grants/test_techaccess_tools.py`
- `backend/tests/agents/grants/test_techaccess_integration.py`

## End-to-end smoke test (manual, after implementation)

1. Start the backend (`docker compose up`) and frontend (`npm run dev` in `frontend/`).
2. Open the app, start a new chat, enable the `grants` agent.
3. Send: *"Draft the LOI synopsis for the Kentucky Coordination Hub."*
4. Confirm: the response renders an `LOI Title` Card starting with "Kentucky Coordination Hub:" and an `LOI Synopsis` Card ≤ ~one page, plus a deadline-reminder info Alert.
5. Send: *"Help me write a Python script."*
6. Confirm: the response is a brief decline with redirect text — no off-topic content (per SC-004).

## Solicitation reference

- Title: NSF TechAccess: AI-Ready America State/Territory Coordination Hub
- Solicitation ID: NSF 26-508
- LOI deadline: 2026-06-16 (Research.gov)
- Full proposal deadline: 2026-07-16 (Research.gov or Grants.gov; AOR signature required)
- Award size: $1M/year for 3 years (possible 4th year), up to 56 awards in three rounds
- Required exact section headings: Section 1 — Vision and Approach to Responsibilities; Section 2 — Organizational Background, Team Expertise, and Partnership Rationale; Section 3 — Current State of AI Planning and Coordination; Section 4 — Work Plan, Milestones, and Performance Metrics; Section 5 — Resource Mobilization and Leveraging Additional Support
- Narrative page limit: 15 (references excluded)

## Pointers to the spec and design

- [spec.md](spec.md) — what the agent does and why
- [research.md](research.md) — design decisions
- [data-model.md](data-model.md) — Python knowledge-module shape
- [contracts/](contracts/) — six MCP tool contracts
- [checklists/requirements.md](checklists/requirements.md) — spec quality checklist
