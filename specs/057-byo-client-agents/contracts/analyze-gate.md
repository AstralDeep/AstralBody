# Contract: Analyze Gate (`orchestrator/agent_analyze.py`)

**Purpose**: a **deterministic**, pre-generation validator of a drafted agent spec against the agent constitution's A–L checklist. It is the mandatory gate that makes "no code generated while Analyze fails" structural (FR-003/FR-005/SC-004). It is **distinct** from the existing code-level gates (`code_security`, `agent_validator`), which run on *generated code*, post-generation.

## Interface

```
check(draft_spec, *, constitution=load()) -> AnalyzeResult
```

- **Input** `draft_spec`: the drafted fields — `display_name`, `description`, `declared_tools`, `declared_scopes`, `declared_egress`, plan mapping, clarify answers.
- **Input** `constitution`: parsed from `agent_constitution.load_checklist()` (A–L) + `AGENT_CONSTITUTION_VERSION`.
- **Output** `AnalyzeResult`:
  - `passed: bool`
  - `constitution_version: str` (stamped onto the draft/user_agent on pass)
  - `violations: [{principle, title, plain_language, offending_field}]` — one per failed check, each citing the offending part (constitution requires a cited offending part; UX requires plain language).

## Determinism requirement

Each A–L check is a **rule over declared fields** (pass/fail decidable), optionally LLM-assisted for phrasing the plain-language message but **never** LLM-decided. Examples of the rule shape:

- **A** (no self-authority): reject if the spec requests a token/identity/scope not expressible as an owner-delegated tool/scope.
- **B** (declared surface): the set of tools/scopes/data-categories the plan uses ⊆ the declared set.
- **C** (least privilege): every `declared_scopes` entry is referenced by ≥1 declared capability.
- **D** (no cross-user reach): no field references another user / a non-owner-resolvable target (pattern + allow-list check).
- **E/F** (untrusted/fail-closed/honest): the plan declares no client-side-trust assumption and no undeclared side effect.
- **G** (bounded): declared resource envelope present and within platform caps.
- **H** (identity): proposed `agent_id` is owner-namespaced and non-colliding with built-in/public/reserved/other-user ids.
- **I/J** (no secret exfil / gated egress): every egress in `declared_egress` is routed through the gated path; no secret categories in outputs.
- **K** (privacy): no share/publish/transfer capability in the spec.
- **L** (version binding): result stamps `AGENT_CONSTITUTION_VERSION`.

## Hook point (structural gate)

- Called in the authoring flow **immediately before** `agent_lifecycle.generate_code(draft_id)` (today `create_draft` is followed directly by `generate_code`). On `passed == False`, generation is **not** invoked and the phase does not advance.
- Re-run on `extend_agent`/`apply_revision` (FR-026) and whenever `revalidation_required` is set by a constitution bump (FR-028).

## Guarantees

- A draft that fails any check never reaches `generate_code` (FR-003) and never goes `live` (SC-004).
- Every failure is reported in plain language tied to the offending field (FR-005).
- The pass records the exact constitution version (Constitution L).
