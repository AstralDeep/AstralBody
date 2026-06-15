# Feature Specification: Finish Soul Integration

**Feature Branch**: `030-finish-soul-integration`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "Complete the unfinished work from the recent specs — primarily feature 025 (agentic-soul-integration) plus the leftover cleanup from feature 029. This is a remediation/completion feature that closes verified gaps found in an implementation audit."

## Context

An implementation audit (2026-06-15) of the recently merged specs found that **026, 027, and 028 are fully implemented**, **029 is functionally complete except for one disk-cleanup gap**, and **025 (agentic-soul-integration) is substantially incomplete** despite many tasks being checkbox-marked done. The audit adversarially verified each gap. The most serious finding: the scheduled-jobs subsystem is **live but broken** — its background loop is started, yet the orchestrator methods it calls do not exist, and it runs under an offline-grant credential store that never received its mandated security review.

This feature brings 025 to genuine end-to-end completion and finishes 029's cleanup, so the project has a trustworthy base before any net-new feature work begins. It adds **no new user-facing capabilities** beyond what 025 already promised — it makes the promised capabilities actually work, observable, tested, and safe.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scheduled work runs safely or not at all (Priority: P1)

A user asks the assistant to run a recurring task ("compile a digest every Monday at 9am"). The job is created with explicit consent, and when its time arrives it actually executes unattended and the user receives an in-app notification with the result. Crucially, until the offline-grant credential store has passed its security review, the execution loop does not run in a half-working state that silently fails or executes under unreviewed authority — it is explicitly disabled and reported as unavailable.

**Why this priority**: The scheduler subsystem is currently shipping in a broken, ungoverned state — the loop starts, calls orchestrator methods that don't exist (failures are swallowed), and operates against an offline-grant store with no security sign-off. This is both a correctness bug and a governance/security violation. It is the single highest-risk item.

**Independent Test**: Create a scheduled job via chat consent; advance/trigger its run time; confirm the job executes, produces output, and the user gets an in-app notification — OR, if the security gate is not yet satisfied, confirm the loop is disabled and the user is told scheduling is unavailable, with no silent failures and no execution under unreviewed authority.

**Acceptance Scenarios**:

1. **Given** the offline-grant store has a recorded security sign-off and scheduled execution is enabled, **When** a consented job's scheduled time arrives, **Then** the job runs unattended within its expected window and the user receives an in-app notification of the result.
2. **Given** a user consents to a recurring job in chat, **When** the consent is captured, **Then** the job is stored with a populated offline-grant reference so it can execute under bounded, persistent authority.
3. **Given** the security sign-off has NOT been recorded, **When** the application starts, **Then** the scheduled-execution loop does not run, no job-execution code paths are reachable, and the user-facing scheduling surface reports that unattended execution is currently unavailable.
4. **Given** a scheduled job runs, **When** it completes or fails, **Then** the run outcome is persisted and an operator can see a structured log/metric for the run without reading code.

---

### User Story 2 - The assistant can remember and recall on request (Priority: P1)

During a conversation a user says "remember that I prefer concise answers" or "what do you know about my project preferences?". The assistant can actively store a memory and later search and retrieve it, in addition to the existing passive recall that is injected into its prompt.

**Why this priority**: Cross-session memory is a headline capability of 025. The storage, retrieval, and PHI-gating logic already exist and are tested, but the tools are never registered with the assistant, so the assistant cannot actually use them on request — only passive prompt-injected recall works. This is a small wiring task with high user-visible payoff.

**Independent Test**: In a chat, ask the assistant to remember a non-PHI preference; in a later turn (or session) ask it to recall that preference; confirm it can both store and retrieve via its own tool calls, and that the PHI gate still blocks disallowed content.

**Acceptance Scenarios**:

1. **Given** memory is enabled for a user, **When** the user asks the assistant to remember a non-PHI fact, **Then** the assistant stores it and confirms.
2. **Given** a stored memory, **When** the user asks the assistant to recall related information, **Then** the assistant retrieves and surfaces it.
3. **Given** a user attempts to store content that the PHI gate disallows, **When** the assistant tries to remember it, **Then** the store is refused and the refusal is handled gracefully and audited.

---

### User Story 3 - Onboarding actually personalizes the assistant (Priority: P2)

A new user completes the onboarding flow — choosing their profession/goals, enabling recommended skills, and setting an assistant personality. Their selections are saved, and subsequent assistant behavior reflects the enabled skills and chosen personality. A returning user is not re-prompted and sees their captured preferences in effect.

**Why this priority**: Onboarding panels render today, but submitted values are silently dropped — nothing is persisted and the enabled-skill guidance never reaches the assistant's prompt (a dead call site). Onboarding therefore looks complete but personalizes nothing. This blocks the core US1 value of 025.

**Independent Test**: Complete onboarding as a new user, enabling at least one skill and a personality; confirm the profile and skill selections persist; confirm the assistant's behavior reflects the enabled skills; reload as a returning user and confirm no re-prompt and preferences in effect.

**Acceptance Scenarios**:

1. **Given** a new user submits the onboarding personalization panel, **When** they confirm, **Then** their profile (profession, goals, personality) is persisted.
2. **Given** a user enables recommended skills during onboarding, **When** they confirm, **Then** those skills are enabled (subject to scope-gating) and their guidance is reflected in the assistant's responses.
3. **Given** a user who has completed onboarding, **When** they return, **Then** they are not re-onboarded and their captured preferences remain in effect.

---

### User Story 4 - Background consolidation runs automatically (Priority: P2)

For users who have "dreaming" (background memory consolidation) enabled — the default — consolidation sweeps run automatically on a recurring schedule rather than only when manually triggered. Users who disable dreaming have no sweeps run.

**Why this priority**: The consolidation logic, enable/disable flag, and manual trigger all exist, but the per-user recurring job is never created — the default cron value is dead code. Dreaming is advertised as default-on automatic, but in reality nothing runs unless triggered by hand.

**Independent Test**: For a user with dreaming enabled, confirm a recurring consolidation job exists and fires on schedule; disable dreaming and confirm the sweep no longer runs; re-enable and confirm it resumes.

**Acceptance Scenarios**:

1. **Given** a user with dreaming enabled, **When** the system initializes their personalization, **Then** a recurring consolidation job exists for them on the default cadence.
2. **Given** a user disables dreaming, **When** the next scheduled time arrives, **Then** no consolidation sweep runs for that user.
3. **Given** a user re-enables dreaming, **When** the next scheduled time arrives, **Then** consolidation resumes.

---

### User Story 5 - The completed work is trustworthy and production-ready (Priority: P3)

A maintainer can rely on the 025 subsystems because they are covered by automated tests at or above the project's changed-code coverage gate, emit structured logs/metrics for every user-visible background operation, are documented for operators, and have accurate task bookkeeping (no checkbox claims that contradict the code).

**Why this priority**: 025 deferred its formal automated tests ("validated live"), leaving its REST endpoints and scheduler loops at ~0% automated coverage (below the ≥90% changed-code gate), with no structured observability for background operations, stale operator-doc references, and several checkboxes that contradict reality. This is required for a clean, maintainable base but does not change user-facing behavior.

**Independent Test**: Run the test suite and the coverage gate on the changed code and confirm it meets the threshold; inspect logs/metrics emitted by a scheduled run, a sweep, a memory write, and a grant mint; confirm operator docs and task bookkeeping are accurate.

**Acceptance Scenarios**:

1. **Given** the remediation work is complete, **When** the test suite and changed-code coverage gate run, **Then** coverage on the changed lines meets or exceeds the project threshold and the deferred contract/integration tests exist and pass.
2. **Given** a background operation (scheduled run, consolidation sweep, memory write, grant mint) occurs, **When** an operator inspects logs/metrics, **Then** the operation is observable without code changes.
3. **Given** the prior specs' task lists, **When** a reader compares checkboxes to the code, **Then** the bookkeeping is accurate (reimplemented/relocated work is reflected, archived items are documented, and no done-marked task is actually missing).
4. **Given** the operator documentation, **When** an operator follows it to configure the realm and environment, **Then** all referenced documents exist and the offline-session/realm requirements are correct.

---

### User Story 6 - Retired agents leave no trace in the knowledge base (Priority: P3)

When agents are retired or merged, their knowledge-base entries do not reappear. The assistant never surfaces or routes to retired agents because of stale knowledge files.

**Why this priority**: Feature 029 retired six agents and merged three, but their knowledge `.md` files still exist on disk in a git-ignored directory, so the runtime knowledge indexer re-discovers them and re-adds references to retired agents. Low user impact but it pollutes the index and risks surfacing retired capabilities.

**Independent Test**: Confirm the retired/merged agents' knowledge files no longer exist on disk and the regenerated knowledge index contains no references to them.

**Acceptance Scenarios**:

1. **Given** the knowledge directory, **When** the knowledge index is regenerated, **Then** it contains no entries for retired agents (grants, nefarious) or merged agents (classify, forecaster, llm_factory).
2. **Given** a user query that previously matched a retired agent's knowledge, **When** the assistant routes, **Then** no retired agent is surfaced.

---

### Edge Cases

- **Scheduler enabled without sign-off**: If configuration attempts to enable scheduled execution while no security sign-off is recorded, the system MUST fail closed (treat execution as disabled) rather than run.
- **Job fires while user has no valid offline grant**: A job whose offline grant is missing, expired, or revoked MUST NOT execute with elevated authority; it is skipped/marked and the user is informed, with no silent unauthorized action.
- **Authority narrowed after consent**: If a user's live scopes shrink after a job was consented, the run MUST use the intersection of consented and current authority and record what was skipped.
- **Onboarding submit with partial/invalid values**: Malformed or partial personalization submissions MUST be rejected with a clear message and MUST NOT persist a corrupt profile.
- **PHI in a remember request**: Disallowed PHI content MUST be blocked at store time and never persisted.
- **Dreaming toggled mid-cycle**: Enabling/disabling dreaming MUST take effect for subsequent scheduled runs without requiring a restart.
- **Knowledge file re-created on disk**: If a retired agent's knowledge file reappears on disk, the index MUST still not surface retired agents (cleanup must be durable, not a one-off delete that the indexer undoes).
- **Notification when the user is offline**: A scheduled job's result MUST be persisted and delivered when the user next connects, not lost.

## Requirements *(mandatory)*

### Functional Requirements

**Scheduled execution & notifications (US1)**

- **FR-001**: The system MUST provide the orchestrator execution seam that the scheduler runner invokes to run a scheduled turn, so consented jobs actually execute unattended. *(closes 025 T046/T040)*
- **FR-002**: The system MUST provide the orchestrator notification seam that delivers in-app notifications of job outcomes, with the notification output persisted so it is delivered when the user reconnects. *(closes 025 T049)*
- **FR-003**: The system MUST capture user consent for unattended execution and persist a bounded, persistent-authority reference on the job, via the consent handshake. *(closes 025 T042)*
- **FR-004**: The offline-grant credential store MUST receive a recorded lead-developer security review (encryption at rest, revocation, lifetime cap, no token egress), and the sign-off MUST be recorded in the repository. *(closes 025 T057)*
- **FR-005**: Unattended scheduled execution MUST be gated such that it runs only when the security sign-off (FR-004) is recorded; otherwise the loop MUST be disabled (fail-closed) and the scheduling surface MUST report unattended execution as unavailable. No code path may execute jobs while the gate is unsatisfied.
- **FR-006**: Job runs MUST use the intersection of consented and currently-live authority, and MUST record any skipped actions due to narrowed or revoked authority.

**Conversational memory (US2)**

- **FR-007**: The assistant MUST be able to invoke memory operations (store, search, retrieve) as tools during a conversation, in addition to the existing passive prompt-injected recall. *(closes 025 T036)*
- **FR-008**: Memory tool availability MUST respect the user's enablement/scope settings, and all writes MUST pass the existing PHI gate and be audited.

**Onboarding personalization (US3)**

- **FR-009**: Submissions from the onboarding personalization panels MUST be interpreted and persisted (profile: profession, goals, personality; enabled skills) instead of being dropped. *(closes 025 T021)*
- **FR-010**: Enabled-skill guidance MUST reach the assistant's prompt so that enabling a skill changes assistant behavior; the currently-dead guidance call site MUST be populated. *(closes 025 T028 / FR-012 of 025)*
- **FR-011**: Skill enablement during onboarding MUST enforce scope-gating (a skill the user is not authorized for is refused).
- **FR-012**: A user who has completed onboarding MUST NOT be re-onboarded on return, and their captured preferences MUST remain in effect.

**Background consolidation (US4)**

- **FR-013**: For each user with dreaming enabled, the system MUST ensure a per-user recurring consolidation job exists on the default cadence, honoring the dreaming-enabled flag (using the currently-unused default cron value). *(closes 025 T053)*
- **FR-014**: Disabling dreaming MUST stop future consolidation runs for that user; re-enabling MUST resume them, without a restart.

**Quality, observability & bookkeeping (US5)**

- **FR-015**: The system MUST include the deferred automated contract/integration tests for personalization profile, onboarding personalize steps, skills, memory endpoints, and the scheduler end-to-end run. *(closes 025 T013/T014/T015/T024/T033/T040)*
- **FR-016**: Changed-code coverage for this feature MUST meet or exceed the project's ≥90% changed-code gate. *(closes 025 T059)*
- **FR-017**: User-visible background operations — scheduled runs, consolidation sweeps, memory writes, and grant mints — MUST emit structured logs/metrics sufficient to diagnose them without code changes. *(closes 025 T055)*
- **FR-018**: Operator documentation MUST be updated and corrected: the realm/offline-session requirements MUST be documented and all referenced document paths MUST exist (fix the stale filename reference). *(closes 025 T056)*
- **FR-019**: The system MUST record verification that no disallowed new third-party libraries were added and no new UI primitive types were introduced. *(closes 025 T058 / SC-009/SC-010)*
- **FR-020**: Task bookkeeping in the prior specs MUST be reconciled to match reality: the personalization editing surface reimplemented as a server-rendered surface MUST be reflected (not the deleted client frontend), the chat-scheduling interpretation already implemented MUST be marked complete, and the archived onboarding tutorial steps MUST have their final state documented. *(closes 025 T022/T050/T018 bookkeeping)*

**Knowledge-base cleanup (US6)**

- **FR-021**: The knowledge-base entries for retired agents (grants, nefarious) and merged agents (classify, forecaster, llm_factory) MUST be removed so the regenerated index contains no references to them, and the removal MUST be durable against the runtime indexer re-discovering on-disk files. *(closes 029 T018/T023)*

**Cross-cutting constraints**

- **FR-022**: No new third-party runtime libraries beyond those already approved for 025 may be introduced.
- **FR-023**: All user-facing UI MUST be server-driven via the existing primitive + render pipeline (no client-side framework reintroduced).
- **FR-024**: The production fail-closed posture MUST be preserved; every new action MUST be audited consistent with existing audit classes.

### Key Entities *(include if feature involves data)*

- **Scheduled job**: A user-consented recurring/one-time task. Relevant attributes: schedule, instruction, consented authority scope, and a reference to the persistent-authority grant used for unattended runs.
- **Job run**: A single execution of a scheduled job. Attributes: outcome/status, timing, skipped actions due to authority intersection, and the produced notification/output.
- **Offline (persistent-authority) grant**: An encrypted, revocable, lifetime-capped credential reference enabling unattended execution under bounded authority. Subject to recorded security review.
- **Memory item**: A stored, non-PHI personalization fact the assistant can write and recall, subject to the PHI gate.
- **Personalization profile**: A user's profession, goals, enabled skills, and assistant personality captured at onboarding and editable later.
- **Consolidation job / sweep**: The recurring background memory-consolidation work governed by the user's dreaming-enabled flag.
- **Knowledge index entry**: A discovered capability/technique record for an agent; must not exist for retired/merged agents.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of consented scheduled jobs either execute within their expected window with an in-app notification delivered, or — when the security gate is unsatisfied — do not execute at all and report as unavailable. There are zero silently-failing job runs.
- **SC-002**: The application never executes unattended jobs under the offline-grant store without a recorded security sign-off (verifiable: with no sign-off, the loop is provably off).
- **SC-003**: A user can, in a single session, ask the assistant to remember a fact and recall it in a later turn, with a 100% success rate for non-PHI facts and 0% persistence of PHI-blocked content.
- **SC-004**: 100% of completed onboarding submissions persist the profile and enabled skills; a returning onboarded user is re-prompted 0% of the time; enabling a skill produces an observable change in assistant guidance.
- **SC-005**: For users with dreaming enabled, a recurring consolidation job exists and runs on schedule; for users who disable it, 0 sweeps run.
- **SC-006**: Changed-code coverage for the feature is ≥90%, and all previously-deferred contract/integration tests exist and pass.
- **SC-007**: Every user-visible background operation (scheduled run, sweep, memory write, grant mint) produces a structured log/metric an operator can find without reading code (100% of the four operation types covered).
- **SC-008**: The regenerated knowledge index contains 0 references to the five retired/merged agents.
- **SC-009**: No new third-party runtime libraries and no new UI primitive types are introduced (verified and recorded).
- **SC-010**: Every prior-spec task checkbox affected by this work matches the actual code state (0 contradictions between bookkeeping and reality).

## Assumptions

- **Security sign-off is a human gate.** This feature delivers all code so the scheduler *can* run and provides the gating mechanism, but turning unattended execution ON requires a real recorded lead-developer security sign-off. Until that exists, the loop ships disabled (fail-closed). The default delivered state is OFF.
- **Onboarding submit interpretation follows the existing meta-tool pattern.** The personalization/skill submit handling mirrors the already-working chat-scheduling meta-tool approach rather than introducing a new mechanism.
- **Tutorial-step final state is "archived".** The personalization onboarding tutorial steps that the 030-wiring rewrite archived stay archived; this feature documents that decision rather than re-seeding them, since onboarding personalization is delivered through the panel/submit flow (FR-009), not the legacy tutorial seed.
- **Memory remains structured non-PHI personalization only**, consistent with 025's posture; the existing PHI gate is reused unchanged.
- **Knowledge cleanup must be durable.** Because the knowledge directory is git-ignored and re-indexed from disk at runtime, "removal" means the files do not exist on disk in deployed images and the indexer does not re-create retired-agent entries — not merely a one-time git deletion.
- **No new user-facing capabilities.** Scope is strictly to make 025's promised capabilities work, observable, tested, and safe, plus 029's cleanup. Net-new features are explicitly out of scope.
- **The existing scheduler, offline-grant store, memory tools, consolidation logic, personalization panels, and audit infrastructure are reused** as-is; this feature wires and completes them rather than rebuilding them.

## Out of Scope

- Any net-new agent, tool, or user-facing capability not already specified by 025.
- Reintroducing a client-side UI framework.
- Adding third-party libraries beyond those already approved for 025.
- Changes to specs 026, 027, and 028 (verified complete).
