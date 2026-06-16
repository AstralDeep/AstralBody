# Quickstart — navigating the corpus & spinning up a follow-on

## Read in this order

1. **[`research/SYNTHESIS.md`](research/SYNTHESIS.md)** — start here.
   - §1 method · §2 convergent themes (the ≥3-stream, highest-confidence signals) ·
     **§3 the prioritized backlog** (71 capabilities, grouped Novelty / UX / Memory / Device /
     Security, each with id, sources, scores, consensus) · §4 wave sequencing + locked decisions ·
     §5 do-not-regress · §6 deferred/out-of-constraint · §7 hype log.
2. **[`spec.md`](spec.md)** — the six user-story initiatives (US1 = this research deliverable;
   US2/US3/US4 = co-flagship follow-ons; US5/US6 = follow-ons), their independent tests, and the
   FR/SC that govern every future implementation.
3. **A stream file** (e.g. [`research/scholarly-generative-ui.md`](research/scholarly-generative-ui.md))
   — full per-finding detail, sources, and implementation notes for any capability you want to act on.

## Find the highest-value moves fast

- **Quick wins (Wave 0, mostly Effort-S, convergent):** `C-N14` structured output · `C-N15` two-tier
  output · `C-N16` context engineering · `C-N5` eval backbone · `C-S4` spotlighting · `C-M4`
  multi-signal retrieval · `C-U2` conservative adaptation · `C-D2` host-config.
- **Co-flagship novelty (Waves 1–2′):** `C-N1` task-model-first UI + `C-U1` deterministic scorer
  (US2) · `C-N4` evolutionary auto-create + `C-N7`/`C-N8` orchestration (US3) · `C-M1`/`C-M2`
  reconcile+linked memory + `C-N11` sleep-time compute (US4).
- **Device:** `C-D4` VOICE renderer (highest-novelty empty target) · `C-D1` capability negotiation ·
  `C-D6` model router.
- **Security (timed to its dependents):** `C-S1` by-construction patterns · `C-S2` taint/provenance ·
  `C-S3` policy engine · `C-S6` sandboxed codegen · `C-S7` red-team self-test.

## Verify the corpus against its contract

See [`contracts/capability-record.md`](contracts/capability-record.md) — the acceptance-check table
maps each Success Criterion (SC-001…SC-010) to a concrete inspection over `research/`.

## Spin a capability up into an approved follow-on feature (after permission)

1. Pick a Consolidated Capability (`C-*`) and its dependencies from SYNTHESIS §3/§4.
2. Open a new feature branch via the normal flow (`/speckit-specify`), citing the `C-*` id(s) and
   the contributing stream findings as the Input.
3. The follow-on spec inherits the **Constraint Envelope** (Python-only, no new deps, SDUI mandate,
   idempotent migrations, fail-closed) and the delivery posture from FR-010 (flag-gated, fail-open,
   ≥90% changed-code coverage) and FR-011 (ship the guarding security control with/before the
   autonomy increase).
4. Implement, test to the constitution's bar, and merge through the Principle-XI CI gates.

## What branch 033 does NOT do

No `backend/` changes, no schema, no dependency, no product behavior change — `git diff` against
`main` touches only `specs/033-frontier-techniques-research/` and the corrected `.specify/feature.json`.
Implementation begins only when you approve opening the follow-on specs.
