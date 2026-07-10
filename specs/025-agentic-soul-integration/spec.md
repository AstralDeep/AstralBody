# Feature Specification: Agentic Soul Integration

**Feature Branch**: `025-agentic-soul-integration`  
**Created**: 2026-05-27  
**Status**: Draft  
**Input**: User description: "Copy all agentic aspects from openclaw to integrate them with AstralDeep while maintaining the security AstralDeep provides. Look at how openclaw handles agents, tools, cron, dreaming, soul, etc. and go through the same onboarding process openclaw has in AstralDeep — have agents available, ask the user to enable skills, and personalize the agent to whatever their profession and goals are just like openclaw does during onboarding. Keeping a server-generated UI via primitives is imperative, and combining AstralDeep with openclaw should create an unstoppable system that bends to the will of the user in a secure and HIPAA-compliant manner."

## Overview

AstralDeep today is a secure, audited, server-driven agent platform: agents are discoverable, tool access is gated by per-user scopes, every action is recorded in an immutable audit trail, and all output is rendered from server-generated UI primitives. What it lacks is the *personal*, *adaptive*, and *autonomous* character that openclaw delivers — an assistant that knows who you are, sounds the way you want, learns your preferences over time, picks up new capabilities ("skills") on demand, and quietly does work for you on a schedule.

This feature brings openclaw's agentic experience — **personalized onboarding, enableable skills, agent personality ("soul"), cross-session memory, scheduled autonomous work ("cron"), and background memory consolidation ("dreaming")** — into AstralDeep, without weakening any of AstralDeep's security or HIPAA guarantees. The goal is an assistant that bends to the user's will while every action remains scoped, consented, audited, and free of protected health information leaking outside its boundary.

Three guardrails, chosen to reconcile openclaw's openness with HIPAA, shape the entire feature:

1. **In-app delivery only.** All results, reminders, and notifications stay inside the secure AstralDeep application. No external messaging channels (email/SMS/chat apps) in this scope.
2. **Autonomy never exceeds the user.** Scheduled and background work runs under a time-bounded, user-consented authorization that can never do more than the user could do themselves, is refreshable, and is fully audited. Such work *may* process PHI in the moment, but only within these constraints.
3. **Memory holds personalization, not PHI.** The durable memory that makes the agent feel like it "knows you" stores professional context, goals, preferences, and workflow facts — never clinical/protected health information. PHI that flows through a task is delivered and audited but never settles into long-term memory.

## Clarifications

### Session 2026-05-27

- Q: What is a "skill" in AstralDeep, and where do skills come from? → A: A skill maps to a tool exposed by an agent, governed by the existing per-agent tool-scope model. "Enabling a skill" means enabling that agent tool for the user (within the tools they are scoped for); the skills "catalog" is the set of agent tools surfaced with plain-language descriptions and gated by scope. No separate authored skill artifact is introduced.
- Q: How is the authorization for scheduled/background jobs managed over time? → A: At job creation the user consents and the system captures an offline grant (reusing the existing persistent-login mechanism). Each run re-derives a fresh, short-lived delegated authorization from that grant, bounded by the user's current (live-checked) scopes. There is a hard maximum lifetime equal to the existing 365-day persistent-login cap, after which the job pauses and requires re-consent. User logout or scope revocation disables future runs.
- Q: Is the personality/"soul" one per user or one per agent? → A: One personality per user, applied across all of that user's agents and conversations (a global "soul"). Per-agent overrides are out of scope for this feature. Profession, goals, and durable memory are likewise per-user; only enabled skills remain per (user, agent).
- Q: How is memory captured? → A: Both. The user can explicitly ask the assistant to remember something, and the assistant may also auto-capture durable non-PHI facts as short-term signals (PHI excluded at capture). The user can always view, correct, and delete memory; the consolidation ("dreaming") sweep is the gate that promotes high-signal short-term items into durable memory.
- Q: Is background consolidation ("dreaming") opt-in or opt-out by default? → A: Opt-out — consolidation is enabled by default for all users; the user can disable it at any time and can also trigger it manually. (Consolidation only moves non-PHI signals into durable memory; no PHI and no external delivery.)
- Q: What scheduling expression model do scheduled jobs support? → A: Three forms — one-shot (run once at a future time), fixed interval (every N minutes/hours/days), and standard cron expressions — all timezone-aware. UI presets (e.g., "weekday mornings") compile down to these underlying forms.
- Q: How is PHI kept out of durable memory and short-term signals? → A: Reuse the existing PHI-detection/redaction capability as the single gate (single source of truth, no new classifier), applied at both short-term signal capture and durable memory write; anything it flags as PHI is blocked from both.
- Q: How are scheduled jobs governed to protect a multi-tenant system? → A: Enforce a per-user cap on active scheduled jobs and a minimum-interval floor (no sub-minute recurring jobs), with fair scheduling so one user cannot starve others; run-time concurrency reuses the existing background-task concurrency cap. Specific numeric limits are configurable and finalized in planning.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Personalized onboarding that makes the assistant feel like *yours* (Priority: P1)

A new user signs in for the first time. Instead of an empty chat box, they are walked through a short, friendly onboarding (rendered entirely from server-generated UI) that introduces the agents available to them, asks what they do for work and what they're trying to accomplish, invites them to turn on the skills relevant to that work, and confirms a personality/tone for their assistant. By the end, the user has an assistant that already understands their profession and goals, has the right capabilities switched on, and greets them accordingly — mirroring how openclaw personalizes an agent during its onboarding ritual.

**Why this priority**: This is the headline request and the foundation everything else builds on. A personalized, skill-equipped agent at first run is the single biggest difference between AstralDeep-as-a-tool and AstralDeep-as-*your* assistant. It is independently valuable even if scheduled tasks and dreaming never ship.

**Independent Test**: Can be fully tested by creating a brand-new user, completing onboarding end-to-end (profession + goals captured, at least one agent presented, at least one skill enabled, a personality chosen), then starting a fresh chat and confirming the assistant references the captured profession/goals and behaves with the chosen personality — all without the user re-entering any of it.

**Acceptance Scenarios**:

1. **Given** a user who has never completed onboarding, **When** they sign in, **Then** they are presented (via server-generated UI) with a guided flow that introduces the agents available to them and explains what each can help with.
2. **Given** the onboarding flow, **When** the user is asked about their work, **Then** they can state their profession and one or more goals, and these are saved as personalization (non-PHI) for reuse.
3. **Given** the onboarding flow and the user's stated profession/goals, **When** the user reaches the skills step, **Then** the system recommends relevant skills and lets the user enable or skip each one, and enabling a skill makes its capabilities available to the assistant.
4. **Given** the onboarding flow, **When** the user reaches the personality step, **Then** they can choose or describe a voice/tone for the assistant, and this choice is applied to the assistant's responses going forward.
5. **Given** a user who has completed onboarding, **When** they return in a later session, **Then** the assistant already knows their profession/goals and does not re-ask, and onboarding does not run again unless the user chooses to revisit it.
6. **Given** a user who wants to stop, **When** they skip or dismiss onboarding, **Then** they can still use the assistant, their partial choices are preserved, and they can resume or restart personalization later.

---

### User Story 2 - Enableable skills that expand what the assistant can do (Priority: P2)

A user (during onboarding or any time after) opens a catalog of skills — packaged capabilities that teach the assistant how to accomplish specific kinds of work (e.g., grant research, scheduling help, data lookups). Each skill clearly describes what it does and what tools/permissions it requires. The user enables the skills they want, and the assistant immediately becomes able to perform that work; disabling a skill cleanly removes that capability. Skill availability always respects the user's existing tool scopes — enabling a skill never grants access the user hasn't been authorized for.

**Why this priority**: "Ask the user to enable skills" is an explicit requirement and the mechanism by which the agent's capabilities grow over time. It is used inside onboarding (US1) but is also a standalone, ongoing management surface, so it is independently valuable.

**Independent Test**: Can be tested by opening the skills catalog as a user, enabling a skill that requires a capability the user is authorized for, confirming the assistant can now perform the associated work, then disabling it and confirming the capability is gone — with every enable/disable recorded in the audit trail.

**Acceptance Scenarios**:

1. **Given** the skills catalog, **When** the user views a skill, **Then** they see a plain-language description of what it does and which capabilities/permissions it relies on.
2. **Given** a skill the user is authorized to use, **When** the user enables it, **Then** the assistant gains the skill's guidance and the action is audited.
3. **Given** a skill that requires a capability the user has *not* been granted, **When** the user views or tries to enable it, **Then** the system clearly indicates the missing authorization and does not silently grant it.
4. **Given** an enabled skill, **When** the user disables it, **Then** the assistant can no longer rely on that skill and the change is audited.
5. **Given** a set of enabled skills, **When** the user starts a conversation, **Then** only the enabled skills inform the assistant's behavior (no leakage from disabled skills).

---

### User Story 3 - An assistant with a personality the user controls ("soul") (Priority: P2)

A user shapes how their assistant *sounds and behaves* — its voice, tone, level of directness, humor, and boundaries — separate from *what it can do*. This "soul" is honored consistently across every conversation and persists across sessions. The user can edit it at any time, and changes take effect in subsequent conversations.

**Why this priority**: openclaw's "soul" is a defining part of the experience and the user explicitly named it. It makes the assistant feel like a consistent personality rather than a generic tool. It is independent of skills and scheduling.

**Independent Test**: Can be tested by setting a distinctive personality (e.g., "concise and direct, no filler"), starting a new conversation, and confirming responses reflect that personality; then changing it and confirming the new tone applies in the next conversation.

**Acceptance Scenarios**:

1. **Given** the personality settings, **When** the user defines or selects a voice/tone, **Then** it is saved as personalization and applied to the assistant's responses.
2. **Given** a saved personality, **When** the user starts any new conversation, **Then** the assistant's behavior reflects that personality without the user re-specifying it.
3. **Given** a saved personality, **When** the user edits it, **Then** subsequent conversations reflect the updated personality.
4. **Given** the personality system, **When** a personality instruction would conflict with a safety, security, or HIPAA rule, **Then** the safety/security/compliance rule always takes precedence.

---

### User Story 4 - An assistant that remembers you across sessions (Priority: P2)

Over time, the assistant remembers durable, non-PHI facts about the user — their profession, goals, stated preferences, and recurring workflow context — so the user doesn't have to repeat themselves. The user can see what the assistant has remembered, correct it, and delete any of it. Protected health information is never written to this memory; it is used live and then discarded from the durable layer.

**Why this priority**: Cross-session memory is what turns personalization from a one-time onboarding into an assistant that keeps getting more useful. It depends on US1's captured profile but extends it continuously.

**Independent Test**: Can be tested by telling the assistant a durable non-PHI preference in one session, starting a new session, and confirming the assistant honors that preference without being told again; and by confirming that an attempt to remember PHI does not persist it.

**Acceptance Scenarios**:

1. **Given** a conversation where the user states a durable non-PHI preference or fact, **When** a later session begins, **Then** the assistant applies that remembered fact without being reminded.
2. **Given** stored memory, **When** the user asks to see what's remembered, **Then** the system shows the remembered personalization items in a readable form.
3. **Given** stored memory, **When** the user corrects or deletes an item, **Then** the change takes effect and the assistant stops relying on the removed item.
4. **Given** content that constitutes PHI, **When** the assistant would otherwise remember it, **Then** it is excluded from durable memory while still usable within the active session.
5. **Given** any memory item, **When** it is created, viewed, changed, or deleted, **Then** the event is recorded in the audit trail and the item is scoped strictly to the owning user.

---

### User Story 5 - Scheduled work the assistant does for you ("cron") (Priority: P3)

A user asks the assistant to do something on a recurring or future schedule — for example, "every weekday morning, summarize what's on my plate" or "in two hours, remind me to follow up." The user grants explicit consent at the time they set it up, defining what the job may do. The job then runs unattended on schedule under a time-bounded authorization that never exceeds the user's own permissions, and delivers its result inside the app. The user can list, inspect, run-now, pause, and delete their scheduled jobs, and review a history of each run.

**Why this priority**: Autonomous scheduled work is a powerful openclaw capability, but it depends on the personalization, skills, and security plumbing from the earlier stories and carries the most compliance nuance, so it follows them.

**Independent Test**: Can be tested by scheduling a short-interval job, confirming it runs at the expected time without the user present, delivers its result in-app, and appears in run history; then pausing/deleting it and confirming it stops running — with each run audited.

**Acceptance Scenarios**:

1. **Given** a request to schedule recurring or future work, **When** the user confirms it, **Then** the user explicitly consents to what the job may do, and a scheduled job is created with that scope recorded.
2. **Given** a scheduled job, **When** its scheduled time arrives and no user is present, **Then** it runs under an authorization that cannot exceed the consenting user's own scopes, and the run is fully audited.
3. **Given** a completed job run, **When** results are ready, **Then** they are delivered inside the app (notification + chat history) and never sent to any external channel.
4. **Given** existing scheduled jobs, **When** the user views them, **Then** they can see schedule, scope, next run, last run, and run history, and can run-now, pause, resume, or delete each.
5. **Given** a job whose underlying authorization has expired or been revoked, **When** its scheduled time arrives, **Then** it does not run with stale authority; it is paused or fails safe and the user is informed in-app.
6. **Given** a job run that processes PHI, **When** it completes, **Then** the PHI it touched is delivered/audited per policy but is not written into durable personalization memory.

---

### User Story 6 - Background consolidation that keeps memory sharp ("dreaming") (Priority: P3)

On a periodic background sweep, the assistant reviews recently learned signals and promotes only the high-value, recurring, non-PHI ones into durable memory, while leaving noise behind. It keeps a human-readable trail of what it consolidated so the user can review and trust the process. This keeps the assistant's long-term memory high-signal and prevents it from bloating with one-off chatter.

**Why this priority**: "Dreaming" is the most advanced/optional openclaw concept; it improves memory quality over time but the system is fully usable without it. It builds directly on US4's memory.

**Independent Test**: Can be tested by generating several sessions' worth of signals (some repeated, some one-off), triggering a consolidation sweep, and confirming that high-signal non-PHI items are promoted to durable memory while one-offs are not, with a readable summary of what happened.

**Acceptance Scenarios**:

1. **Given** accumulated short-term signals from recent sessions, **When** a consolidation sweep runs, **Then** only items meeting signal thresholds (e.g., recurring, relevant) are promoted to durable memory.
2. **Given** a consolidation sweep, **When** it evaluates candidates, **Then** any PHI-bearing content is excluded from promotion.
3. **Given** a completed sweep, **When** the user reviews it, **Then** they can see a readable summary of what was consolidated and why.
4. **Given** the consolidation feature, **When** the user wants control, **Then** they can enable, disable, or trigger it, and every sweep is audited.

---

### Edge Cases

- **No agents available to a user**: Onboarding must still function, clearly explain that capabilities are limited until an agent/skill is enabled, and avoid dead-ends.
- **User abandons onboarding midway**: Partial personalization is preserved; the assistant remains usable; the user can resume later from where they left off.
- **Skill enabled but required authorization missing or later revoked**: The skill must visibly degrade (clear "needs permission" state) rather than fail silently or appear to work.
- **Personality instruction attempts to override safety/compliance**: Compliance and security rules always win; the personality is applied only within those bounds.
- **Memory attempts to capture PHI**: The PHI must be kept out of durable memory while remaining usable for the live task.
- **Scheduled job outlives its authorization**: It must not run with stale/elevated authority; it fails safe and informs the user in-app.
- **Many scheduled jobs fire at once / overlap**: The system must run them within the existing execution-concurrency cap and per-user job/interval limits (FR-038), scheduling fairly so one user's jobs cannot affect another's.
- **Orchestrator/app restarts with jobs scheduled or in flight**: Durable schedules survive a restart; in-flight runs resolve to a defined, auditable state.
- **Consolidation runs while the user is active**: Background work must not disrupt the user's live session or corrupt active context.
- **User deletes a remembered item that a scheduled job or skill depended on**: The dependent feature degrades gracefully and the user is informed.

## Requirements *(mandatory)*

### Functional Requirements

#### Onboarding & personalization (US1)

- **FR-001**: System MUST present a new user with a guided onboarding experience, rendered entirely through the existing server-generated UI primitive system, that introduces the agents available to that user.
- **FR-002**: System MUST capture the user's profession and one or more goals during onboarding and store them as durable, non-PHI personalization.
- **FR-003**: System MUST recommend skills relevant to the user's stated profession/goals and let the user enable or skip each, with enabling a skill making its capability available to the assistant.
- **FR-004**: System MUST let the user choose or describe a personality/tone for their assistant during onboarding and apply it thereafter.
- **FR-005**: System MUST allow the user to skip, dismiss, pause, resume, and later restart onboarding without losing previously captured choices, and MUST NOT block use of the assistant on completing it.
- **FR-006**: System MUST run onboarding only for users who have not completed it (tracking per-user onboarding state), and MUST NOT re-run it automatically for returning users.

#### Agents (US1, cross-cutting)

- **FR-007**: System MUST make agents discoverable to a user according to existing visibility and ownership rules, and MUST present them in onboarding and in ongoing management surfaces.
- **FR-008**: System MUST treat the user's profession, goals, personality/"soul", and durable memory as per-user personalization that applies across all of that user's agents and conversations, while enabled skills remain per (user, agent); together these keep the experience consistent for the user.

#### Skills (US2)

- **FR-009**: System MUST present a catalog of skills, where each skill corresponds to a tool exposed by an agent, shown with a plain-language description of what it does, the agent it belongs to, and the scope it requires (read/write/search/system).
- **FR-010**: Users MUST be able to enable and disable skills (i.e., enable/disable the underlying agent tool for themselves) per agent, with each change taking effect for subsequent conversations and recorded in the audit trail.
- **FR-011**: System MUST ensure that enabling a skill never grants the assistant any capability beyond the scopes the user is already authorized for on that agent; a skill whose required scope is not granted MUST be shown as unavailable with a clear reason rather than silently enabled.
- **FR-012**: System MUST ensure that only enabled skills influence the assistant's behavior, with no leakage from disabled skills.

#### Personality / "soul" (US3)

- **FR-013**: Users MUST be able to define, view, and edit a personality (voice, tone, directness, boundaries) for their assistant, stored as durable non-PHI personalization.
- **FR-014**: System MUST apply the user's personality consistently across all of that user's conversations and persist it across sessions.
- **FR-015**: System MUST ensure that personality instructions can never override safety, security, or HIPAA/compliance rules; those rules take precedence.

#### Memory (US4)

- **FR-016**: System MUST allow durable, non-PHI facts about the user (profession, goals, preferences, recurring workflow context) to be remembered both by explicit user request ("remember this") and by the assistant auto-capturing them as short-term signals (PHI excluded at capture), and MUST recall them in later sessions without the user repeating them. Auto-captured short-term signals become durable only via the consolidation gate (FR-027).
- **FR-017**: System MUST exclude protected health information from durable memory and short-term signals while still allowing it to be used within the active session, using the existing PHI-detection/redaction capability as the single enforcement gate applied at both short-term signal capture and durable memory write.
- **FR-018**: Users MUST be able to view, correct, and delete remembered items, with changes taking effect immediately and the assistant ceasing to rely on removed items.
- **FR-019**: System MUST scope every memory item strictly to its owning user and record creation, viewing, modification, and deletion of memory in the audit trail.

#### Scheduled autonomous work / "cron" (US5)

- **FR-020**: Users MUST be able to schedule recurring or future work for the assistant using one-shot (run once at a future time), fixed-interval (every N minutes/hours/days), or cron expressions — all timezone-aware, with friendlier UI presets compiling down to these forms — and MUST explicitly consent at creation time to the scope of what the job may do.
- **FR-021**: System MUST execute scheduled jobs unattended at their scheduled time under authorization re-derived per run as a fresh, short-lived delegated token from the offline grant captured at job creation, bounded by the user's current (live-checked) scopes, and MUST audit every run.
- **FR-022**: System MUST deliver scheduled-job results only inside the application (in-app notification and chat history) and MUST NOT send results to any external channel.
- **FR-023**: Users MUST be able to list, inspect (schedule, scope, next/last run, run history), run-now, pause, resume, and delete their own scheduled jobs.
- **FR-024**: System MUST refuse to run a job whose offline grant has been revoked (e.g., user logout), whose required scopes are no longer granted, or that has reached the hard maximum lifetime (the existing 365-day persistent-login cap); in each case it MUST fail safe (pause/skip), require re-consent where applicable, and inform the user in-app rather than running with stale or elevated authority.
- **FR-025**: System MUST persist scheduled jobs durably so they survive an application restart, and MUST resolve any in-flight run interrupted by a restart to a defined, auditable state.
- **FR-026**: System MUST ensure PHI processed during a job run is delivered/audited per policy but never written into durable personalization memory.

#### Background consolidation / "dreaming" (US6)

- **FR-027**: System MUST be able to run a periodic background consolidation that promotes only high-signal, recurring, non-PHI items from short-term signals into durable memory and leaves low-signal noise behind.
- **FR-028**: System MUST exclude PHI-bearing content from consolidation/promotion, using the same PHI-detection gate defined in FR-017.
- **FR-029**: System MUST keep a human-readable record of each consolidation sweep (what was promoted and why) that the user can review. Consolidation MUST be enabled by default (opt-out), and the user MUST be able to disable it at any time as well as trigger it manually.
- **FR-030**: System MUST audit every consolidation sweep.

#### Cross-cutting: security, HIPAA, audit, UI

- **FR-031**: System MUST render all user-facing output for these features — onboarding, skills catalog, personality editor, memory viewer, schedule manager, consolidation review — through the existing server-generated UI primitive system, requiring no per-skill or per-agent bespoke frontend templates.
- **FR-032**: System MUST preserve AstralDeep's existing authentication and per-user, per-agent scope-based authorization for every new capability; no new capability may bypass these controls.
- **FR-033**: System MUST record every security-relevant action introduced by this feature (skill enable/disable, personality change, memory change, schedule create/run/delete, consolidation sweep, autonomous job execution) in the existing immutable, append-only audit trail.
- **FR-034**: System MUST ensure protected health information never leaves the application's secure boundary as a result of these features, and never persists into durable personalization memory.
- **FR-035**: System MUST apply existing PHI-redaction to any audit or review artifacts produced by these features so that audit/review surfaces never expose PHI.
- **FR-036**: System MUST be implemented without introducing new third-party libraries, consistent with the project's dependency-management principle — **except** for a lead-developer-approved local PHI-detection package (approved 2026-05-27) used solely to enforce the memory PHI gate (FR-017). Any such package MUST run locally (no PHI egress) and be documented in the PR per the dependency-management principle.
- **FR-037**: System MUST keep all new persistent data within the existing data store using the project's idempotent auto-migration approach, with per-user scoping on all new data.
- **FR-038**: System MUST govern scheduled jobs for multi-tenant safety by enforcing a per-user cap on active scheduled jobs and a minimum-interval floor (no sub-minute recurring jobs), scheduling fairly so one user cannot starve others, and reusing the existing background-task concurrency cap for run-time execution. Specific numeric limits MUST be configurable.

### Key Entities *(include if feature involves data)*

- **User Personalization Profile**: The durable, non-PHI description of a user that personalizes their assistant — profession, goals, stated preferences, and the chosen personality/"soul". Owned by and scoped to one user; readable, editable, and deletable by that user.
- **Skill**: A tool exposed by an agent, surfaced to the user with a plain-language description, its owning agent, and its required scope (read/write/search/system). It has an enabled/disabled state per user, per agent (the existing per-user/per-agent/per-tool override). Enabling a skill makes that tool available to the assistant for that user but grants no authority beyond the user's existing scopes; it is not a separately authored artifact.
- **Personality ("Soul")**: The voice/tone/boundaries definition that governs how the assistant communicates, distinct from what it can do. One per user, applied across all of that user's agents and conversations; part of the personalization profile; always subordinate to safety/compliance rules.
- **Memory Item**: A single durable, non-PHI fact the assistant has learned about the user. Scoped to the user; viewable/correctable/deletable; subject to audit; excluded from holding PHI.
- **Short-Term Signal**: A transient, non-PHI observation from recent sessions — captured automatically by the assistant or recorded from recall events — that is a candidate for consolidation into a durable Memory Item; discarded if it doesn't meet promotion thresholds.
- **Scheduled Job**: A user-defined recurring or future task — its schedule (one-shot, fixed interval, or cron, all timezone-aware), target agent, instruction, the user's recorded consent/scope, delivery target (in-app), and authorization state (the offline grant captured at creation plus its hard 365-day expiry). Authorization is re-derived per run as a fresh short-lived token bounded by the user's current scopes. Owned and scoped to one user.
- **Job Run**: A single execution record of a Scheduled Job — start/end, outcome, authorization used, audited reference, and delivered result. Survives restarts in a defined state.
- **Consolidation Sweep ("Dream")**: A record of one background consolidation pass — what was reviewed, what was promoted, and why — kept in human-readable form for user review and audited.
- **Onboarding State**: Per-user tracking of where the user is in the personalization flow (not started, in progress, completed, skipped, dismissed) so onboarding runs at the right times.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can complete the full personalized onboarding (profession + goals captured, at least one agent introduced, at least one skill enabled, a personality chosen) in under 5 minutes.
- **SC-002**: At least 80% of new users who begin onboarding reach a personalized state (profession/goals captured and at least one skill enabled or intentionally skipped).
- **SC-003**: In a returning session, the assistant correctly reflects the user's saved profession, goals, and personality without re-asking, in 100% of cases where those were previously captured.
- **SC-004**: 100% of security-relevant actions (skill enable/disable, personality change, memory change, schedule create/run/delete, consolidation sweep, autonomous job execution) appear in the audit trail.
- **SC-005**: 0 instances of protected health information are written to durable personalization memory, verifiable by inspection/audit of the memory store.
- **SC-006**: 0 instances of feature output (results, reminders, notifications) being delivered to any external channel; all delivery is in-app.
- **SC-007**: Scheduled jobs execute within a small, defined tolerance of their scheduled time (e.g., within 1 minute for interval/time-of-day jobs) and 100% of scheduled jobs survive an application restart.
- **SC-008**: No autonomous job ever performs an action outside the consenting user's granted scopes (0 privilege-escalation events), and jobs with expired/revoked authorization never execute (0 stale-authority runs).
- **SC-009**: Adding a new skill or agent requires 0 new bespoke frontend templates — all related UI renders through existing server-generated primitives.
- **SC-010**: No new third-party libraries are introduced by the feature, except the single lead-developer-approved local PHI-detection package (and its transitive dependencies) used to enforce the memory PHI gate; that package runs locally with no PHI egress.
- **SC-011**: After a consolidation sweep over mixed signals, only high-signal recurring non-PHI items are promoted (measurable as: one-off and PHI-bearing candidates promoted = 0), and a readable summary of the sweep is available to the user.
- **SC-012**: Users can find and delete any single remembered item about themselves and see it stop influencing the assistant within the same session.

## Assumptions

- **Existing platform is reused, not rebuilt.** The feature builds on AstralDeep's existing agent model, per-user/per-agent scope authorization, delegated-authorization mechanism, immutable audit trail, PHI-redaction, server-generated UI primitive system, onboarding/tutorial state, and data store. No parallel mechanisms are introduced.
- **Web application scope only.** openclaw's local-daemon installation, OS service integration, and external messaging channels (WhatsApp, Telegram, Discord, Slack, Signal, iMessage, email) are out of scope; everything occurs inside the existing AstralDeep web application with in-app delivery (per clarification).
- **Unattended authority is derived and bounded.** At job creation the user consents and the system captures an offline grant (reusing the existing persistent-login mechanism). Each run re-derives a fresh short-lived delegated token from that grant, bounded by the user's current (live-checked) scopes, and is fully audited. A hard maximum lifetime equal to the existing 365-day persistent-login cap applies, after which the job pauses pending re-consent; logout or scope revocation disables future runs. Such work may process PHI in the moment under these constraints (per clarification).
- **Durable memory is personalization, not PHI.** Long-term memory and the personality/"soul" store professional context, goals, preferences, and workflow facts only; PHI is used live and excluded from durable memory (per clarification). This makes the autonomy and memory decisions mutually compatible: PHI may pass *through* a job run and be delivered/audited, but never *persists* into memory.
- **Skills are guidance, not new privilege.** A skill teaches the assistant how to use capabilities it is already authorized for; enabling a skill never expands the user's authorization.
- **Personality is always subordinate to compliance.** No personality/"soul" setting can weaken safety, security, or HIPAA rules.
- **Single-orchestrator assumption for scheduling.** Durable persistence of schedules and defined restart behavior are required; horizontal/distributed scheduling across multiple orchestrator instances is assumed not required for this scope unless the platform already mandates it.
- **Reasonable defaults for unspecified UX details** (exact wording of prompts, default skill recommendations per profession, default personality presets, default consolidation frequency) follow the project's existing onboarding/tutorial conventions and can be refined during planning.

## Out of Scope

- External messaging/notification channels of any kind (email, SMS, WhatsApp, Telegram, Discord, Slack, Signal, iMessage).
- Local-daemon/desktop installation and OS service integration from openclaw.
- Storing PHI in durable agent memory or the personality store.
- Autonomous actions that exceed the consenting user's own authorization.
- Distributed/multi-node scheduling guarantees beyond durable persistence and defined single-instance restart behavior.
- Introducing new third-party libraries or frameworks.
