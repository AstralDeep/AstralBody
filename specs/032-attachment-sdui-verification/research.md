# Phase 0 Research: Agentic File-Upload SDUI & Delegated-Authority Verification

**Feature**: 032-attachment-sdui-verification | **Date**: 2026-06-16

All NEEDS CLARIFICATION items are resolved (four were settled in `/speckit-clarify`, Session 2026-06-16; the rest are answered below from a direct read of the system under test). Each decision records what was chosen, why, and what was rejected. File:line references are the seams the harness consumes; they are anchors, not contracts (the harness asserts on observable behavior, not on line numbers).

## D1. Verdict model — agentic structure, deterministic gate

- **Decision**: The pass/fail/uncertain verdict is decided by **deterministic structural + authority assertions** only. The plan→act→observe→verify loop and an optional LLM-as-judge are agentic flourishes layered on top; they never decide a pass.
- **Rationale**: Clarification 2026-06-16. The product is generative, so asserting on structure (component types ∈ published vocabulary, content provenance from the file, persistence + identity, audit-chain integrity, permission/ownership/admin outcomes) is the only reproducible gate (Edge case "non-determinism"; FR-004). It makes the CI gate independent of model availability.
- **Alternatives rejected**: *Fully agentic* (LLM decides everything) — non-deterministic, needs LLM creds in CI, hard to gate. *Fully deterministic with no agentic behavior* — fails the spec's explicit "mirror modern agentic frameworks" intent (FR-001/003/007).

## D2. In-process determinism — scripted LLM via the client-factory seam

- **Decision**: In-process mode injects a **deterministic scripted LLM** by assigning `orch._call_llm = <scripted coroutine>` (the exact seam existing tests use: `backend/tests/test_ui_designer_integration.py` builds a fake `_call_llm` and assigns it). `_call_llm(websocket, messages, tools_desc=None, temperature=None, feature="tool_dispatch")` returns `(message, usage)` where `message` has `.content` and `.tool_calls` (each `.id`, `.function.name`, `.function.arguments` JSON string). Real tool execution, component construction, persistence, ROTE, render, and audit all still run.
- **Rationale**: Clarification 2026-06-16. Scripting only the model's token output preserves the *entire* real pipeline while making output reproducible (SC-012). Reuses an established, proven seam — no parallel mechanism (FR-030).
- **Alternatives rejected**: *Real live LLM in CI* — flaky, costs tokens, credential risk, contradicts "no live deployment." *Bypass the LLM and call readers directly* — skips the orchestrator's real tool-dispatch + designer path, weakening the end-to-end claim.

## D3. Component-production path — two-step scripted chain over REAL tools

- **Decision**: The canonical in-process scenario is a **two-step ReAct chain**: (1) the scripted LLM calls the real reader for the file's category (`parser_registry.BUILTIN_CATEGORY_TOOL`: `document→read_document`, `spreadsheet→read_spreadsheet`, `text→read_text`, `image→read_image`); (2) on seeing the reader's **real parsed output** in the tool-result message, the scripted LLM calls a **real component-emitting tool** (general agent tools in `backend/agents/general/mcp_tools.py` that return `_ui_components` of `Table`/`MetricCard`/`PlotlyChart`; or connectors widget tools) with arguments **populated from that real output**; (3) a final no-tool text turn closes the loop. Components are therefore produced by *product* tools and their data derives from the *actual uploaded file*.
- **Rationale**: Readers return raw data dicts, not components (verified: `read_*` return `{text|rows|columns|…}`). Routing real reader output into a real component tool keeps provenance genuine (FR-011) and makes the component re-executable through the real `_source_agent/_source_tool/_source_params` stamping (FR-013) — all while staying deterministic because the scripted LLM derives the second call's args from the first call's real result.
- **Alternatives rejected**: *Scripted LLM authors component JSON in its final response* — the product does validate such components against `allowed_primitive_types()` (orchestrator.py:2270/3631/5882) and would satisfy FR-010/011/023, but the component would be harness-authored, not product-tool-authored, and would not be re-executable (no source tool) — fails FR-013. We keep the validated-final-response path only as the representation for the "legitimately prose/short answer" scenario (FR-015).

## D4. Response capture — VirtualWebSocket-style buffer

- **Decision**: Capture the exact server→client messages by giving the driven turn a capture socket that buffers every `send_text`/`send_json` payload (the `VirtualWebSocket` pattern, `orchestrator/async_tasks.py:56`). Captured message `type`s of interest: `ui_render` (full canvas; carries `components` + server `html` wrapping each in `<div class="astral-component" data-component-id=…>`), `ui_upsert` (`ops:[{op,component_id,component,html}]`), `chat_status`, `user_message_acked`, `chat_created`.
- **Rationale**: This is literally what a browser receives (FR-030, FR-001 "captures the same server→client UI messages a browser would receive"). Reuses the product's own primitive.
- **Alternatives rejected**: Mocking `send_ui_render`/`_safe_send` with bespoke spies — works but a thin capture socket is closer to the real wire and exercises `_safe_send` serialization.

## D5. In-process identity & delegated authority

- **Decision**: Create distinct authenticated principals A, B, admin in-process by registering sessions directly (`orch.ui_sessions[ws] = {"sub": <id>, "preferred_username":…, "realm_access":{"roles":[…]}}`) under **namespaced** ids. Delegated-authority *evidence* is asserted via `delegation.py` (`DelegationService.exchange_token_for_agent` → RFC 8693 `act:{sub:"agent:<id>"}` claim, attenuated `scope`, RFC 9449 DPoP `cnf.jkt`) and `audit.hooks.actor_principal_from_claims(claims) -> (actor_user_id=sub, auth_principal=act.sub)`. The harness asserts audit rows carry on-behalf-of user (`actor_user_id`) distinct from acting agent (`auth_principal`).
- **Rationale**: Satisfies FR-019 (delegation, not identity assumption) and FR-020 (attribution) against the real delegation + audit code. Mock-auth literals confirmed (`web_auth.py`: `test_user`/`dev-token`, roles `["admin","user"]`) but the harness uses its own namespaced principals rather than the single shared mock user, so users A/B/admin are genuinely distinct.
- **Alternatives rejected**: Routing in-process auth through the full HTTP `/auth` Keycloak flow — unnecessary for in-process; that fidelity belongs to the external surface (D11).

## D6. Cross-user isolation & scope-withholding checks

- **Decision**: (a) Cross-user (FR-017): user A uploads; user B references A's `attachment_id` in a turn → `_attach_turn_attachments` calls `att_repo.get_by_id(aid, user_b)` → `None` (ownership `WHERE attachment_id=? AND user_id=?`), drops it, and records `event_class="file" action_type="attachment_reference_denied"`; the harness asserts the drop + audit + that A's filename/content never reach B's turn or workspace. (b) Scope (FR-016): set a scope off via `tool_permissions.set_agent_scopes(user, agent, {scope:False})`; assert the tool is withheld from dispatch (`is_tool_allowed` False at `execute_single_tool`). (c) Re-exec under revoked scope (US2 scenario 3): revoke, then trigger `component_action` → `_component_action_allowed` False → `_audit_workspace_denial` (`workspace.action_denied`).
- **Rationale**: Exercises the real gates and the real denial audits. Verified seams: `attachments/repository.py:106`, `tool_permissions.py:239`, `orchestrator.py:_handle_component_action`/`_component_action_allowed`.
- **Alternatives rejected**: Asserting only at the DB layer — misses the orchestrator-level withholding and the denial audit the spec requires.

## D7. Admin-only auto-parser approval

- **Decision**: Drive a draft for a **synthetic, clearly-namespaced unsupported extension** so coverage is genuinely absent; assert `agentic_creation._h_draft_approve` refuses non-admin/self-approval (audits `lifecycle.rejected`, outcome failure) and that an admin reaches the approve path. Teardown discards the draft and removes any `attachment_parser`/visibility/scope artifacts so global fleet state is not polluted.
- **Rationale**: FR-018, US2 scenario 4. `_decidable_draft` + `_h_draft_approve` gate `origin == "auto_attachment"` to admins; uploader can't self-approve. The synthetic extension + teardown keeps `_promote_parser_global` side effects (`set_agent_visibility(True)`, scope grant, replay) contained (FR-031).
- **Alternatives rejected**: Approving a real format globally — pollutes the catalogue and changes fleet behavior (violates FR-031/FR-032 spirit).

## D8. Audit-chain verification

- **Decision**: After each scenario, assert the per-user chain is unbroken via `AuditRepository.verify_chain(user_id)` (returns `None` if clean, else first bad `event_id`; HMAC-SHA256, per-user `pg_advisory_xact_lock`, genesis-anchored). Assert paired tool dispatch rows (`tool.<name>.start`→`.end`, same `correlation_id`) and attribution (`actor_user_id` vs `auth_principal`).
- **Rationale**: FR-020, SC-007. Uses the product's own verifier — no reimplementation of the hash logic.
- **Alternatives rejected**: Re-deriving HMACs in the harness — duplicates trust-critical logic and could mask a real bug behind a matching reimplementation.

## D9. Thin-client static inspection (objective measure)

- **Decision**: An objective, recorded measurement over `backend/webrender/static/client.js` (~858 lines): PRESENCE of generic server-HTML injection (`innerHTML =`) and identity-addressed morph (`data-component-id`) and generic action forwarding (the `ui_event` send / `.astral-action` delegation); ABSENCE of (i) any client-side rendering framework import (`react`, `vue`, `angular`, `import … from "react"`), and (ii) per-component-type construction logic (a `switch`/dispatch on `component.type` that builds widgets). The measurement (booleans + matched/!matched markers) is recorded as evidence (FR-025).
- **Rationale**: Makes US3's "no construction logic, no framework" assertion concrete and reproducible. Vocabulary (FR-023) is asserted from captured output against `webrender.allowed_primitive_types()` (frozenset of 31 types). Server-markup (FR-024) is asserted from the `html` field present on `ui_render`/`ui_upsert`.
- **Alternatives rejected**: A subjective "looks thin" claim — not measurable (fails SC-008).

## D10. ROTE device adaptation evidence

- **Decision**: Adapt one captured component set for two device profiles via `rote.adapter.ComponentAdapter.adapt(components, DeviceProfile.from_dict({...}))` (BROWSER vs MOBILE/WATCH) and assert the differences are produced by the backend adapter (e.g., charts collapsed, grid columns reduced), satisfying FR-026.
- **Rationale**: ROTE is server-side; the harness calls the same adapter the orchestrator calls before render (`send_ui_upsert` adapts per profile then renders). No client involvement.
- **Alternatives rejected**: Driving two real device clients in-process — heavier; the adapter call is the authoritative seam.

## D11. External-client surface (opt-in)

- **Decision**: External mode uses already-present `httpx` (REST: `POST /api/upload`, chat) and `websockets` (`ws://<base>/ws`: `register_ui{token,device}` → `chat_message{payload:{message,attachments}}`; capture `ui_render`/`ui_upsert`). Auth uses real Keycloak via env-named creds (`KEYCLOAK_AUTHORITY`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_REALM`, `KEYCLOAK_TOKEN_URL`) and the real RFC 8693 token exchange. Base URL via env (e.g., `ASTRAL_VERIFY_BASE_URL`). This surface is **opt-in, not a CI merge gate**.
- **Rationale**: Clarification 2026-06-16 + FR-021/FR-030. Proves the thin-client and delegated-authority claims through the real network; keeps live-network/real-realm/live-LLM flakiness out of the merge gate.
- **Alternatives rejected**: Making external a gate — non-deterministic, needs a live deployment. Deferring external entirely — drops the real-realm proof the spec requires.

## D12. Run mode labelling & credential safety

- **Decision**: Every run records its **authority mode** (`real_keycloak` | `mock_inprocess`) and never claims real-realm guarantees for a mock run (SC-010). All identity/provider creds are read by **env-var NAME only**; a redaction pass scrubs known secret-shaped values from every captured artifact, log, and report, and any near-exposure flags the run (FR-022/SC-011).
- **Rationale**: Direct spec mandate. Mock-vs-real degradation is the documented fallback when Keycloak is unreachable (Edge case "Real Keycloak unreachable").

## D13. Termination, retries, and uncertainty

- **Decision**: Each scenario runs under hard budgets (default ≤ 8 plan→act→observe→verify steps, ≤ 6 ReAct turns, ≤ 60 s, ≤ 2 retries) and always exits with `pass|fail|uncertain` — never on the agent's own "I'm done" (FR-005). Retries carry forward the prior failure record (FR-006). A deterministic↔LLM-judge disagreement, or a counter-check that contradicts the primary check, yields `uncertain` with both evidences (Edge case "self-verification disagreement"; FR-003); the proportion of uncertain verdicts is reported (SC-009).
- **Rationale**: Verifiable termination is a first-class requirement; "uncertain" is a real outcome, not a hidden pass.
- **Alternatives rejected**: Unbounded retry until green — masks regressions and can loop.

## D14. Isolation & cleanup

- **Decision**: All harness principals/chats/attachments/drafts use a `__verif__<run_id>_…` namespace. Teardown deletes deletable rows for those principals (`chats`, `messages`, `saved_components`, `workspace_layout`, `user_attachments`, `message_attachment`, `draft_agents`, `attachment_parser`) and removes uploaded blobs. `audit_events` are append-only by design and remain, but only ever under namespaced principals — never under a real user (FR-031). Run records live in a gitignored, per-run dir.
- **Rationale**: Safe to run repeatedly (FR-031, SC-013) on the shared container Postgres without touching real users.
- **Alternatives rejected**: A throwaway database per run — heavier and diverges from how the suite already shares the running Postgres.

## D15. CI wiring

- **Decision**: Mark the in-process suite `@pytest.mark.integration` (so it is excluded from invocation #1's `-m 'not integration'`) and add `verification/tests` to the **second** pytest invocation in `.github/workflows/ci.yml` (which lists explicit module dirs with no `-m` filter and already provides `ASTRAL_ENV=development`, DB env, `AGENT_API_KEY`, `AUDIT_HMAC_SECRET`). Coverage flows into the same `coverage.xml` consumed by the diff-cover gate.
- **Rationale**: This is exactly how `audit/tests`, `orchestrator/tests`, etc. run today; it makes the harness a real merge gate (clarification 2026-06-16) with a one-line CI edit and no product change.
- **Alternatives rejected**: Leaving tests unmarked under `tests/` (would run in invocation #1, coupling them to the fast dev loop and the `not integration` default) — the integration marking + explicit invocation is the precise match for "integration suite that gates CI."

## D16. No new dependencies — confirmed

- **Decision/Finding**: `backend/requirements.txt` already provides `websockets`, `httpx` (and `requests`), `pytest`/`pytest-asyncio`, `openai`, `psycopg2-binary`, `astralprims`. The harness needs nothing else; everything else is stdlib (`json`, `hashlib`, `dataclasses`, `pathlib`, `asyncio`, `re`, `uuid`, `argparse`).
- **Rationale**: FR-032 / Constitution V satisfied with zero additions.
