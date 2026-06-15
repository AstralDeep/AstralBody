# Contract: Auto-Create Parser Lifecycle

Defines the safe, admin-gated, globally-promoting lifecycle that produces a backend parser for an accepted file type no existing tool can read. Reuses the feature-027 lifecycle primitives (`agent_lifecycle`, `code_security`, VirtualWebSocket self-test, `draft_agents`, `agent_lifecycle` audit class) with two clarified changes: **admin-only approval** and **global promotion**.

## Trigger (eager, on upload)

```
POST /api/upload (success)
  └─ parser_registry.coverage(extension, category)
       ├─ covered (built-in OR attachment_parser row status='live')  → parser_status="covered"; done
       └─ uncovered
            ├─ FF_ATTACHMENT_AUTOPARSE off → parser_status="unavailable"; audit; done
            ├─ existing attachment_parser row status in (pending) for gap → parser_status="pending_admin_approval"; done  (dedup, FR-018)
            └─ none → enqueue attachment_autoparse.start(attachment, user_id, chat_id)  (background); parser_status="preparing"
```

`gap_fingerprint = sha256(f"attachment_parser:{category}:{extension}")[:32]` — format-scoped (NOT chat-scoped), so the same type never double-drafts.

## Background creation (reuses 027 primitives)

`attachment_autoparse.start(...)` runs off-request:

1. **Register intent**: insert `attachment_parser` row `status='pending'`, `gap_fingerprint`, `source_attachment_id`, `source_chat_id`, `requested_by`. Emit audit `agent_lifecycle / gap_detected`, `correlation_id = draft_id` (allocated next), `inputs_meta={extension,category,attachment_id,gap_fingerprint,trigger:"upload"}`.
2. **Create draft**: `lifecycle.create_draft(...)` with `agent_name="<EXT> Parser"`, a single tool `parse_<ext>` described as "extract text/structured content from a <ext> file"; `update_draft_agent(origin="auto_attachment", source_chat_id, gap_fingerprint, source_attachment_id)`; link `attachment_parser.draft_agent_id`.
3. **Generate code**: `lifecycle.generate_code(draft_id)` — LLM writes `mcp_tools.py` under the **stdlib + already-installed packages only** constraint (R7). Output must return astralprims-shaped components.
4. **Security gate**: `code_security.analyze(code)` — AST + import + regex. CRITICAL/HIGH ⇒ not eligible to go live (see decision table).
5. **Start + self-test**: `start_draft_agent(draft_id)`; `_self_test_draft(...)` executes the parser against **the uploaded file** in an isolated VirtualWebSocket (120 s budget, ≤1 auto-refine). Persist `self_test` JSON.
6. **Notify uploader**: send a "pending admin approval" (or "could not prepare a reader") status card to all of the uploader's sockets on `source_chat_id`. Emit `agent_lifecycle / auto_created` + `/ self_test`.

The draft is now **pending**. Nothing is live; no parser code has run against the user file outside the gate + isolated self-test.

## Approval (ADMIN ONLY)

Surfaced in the drafts chrome surface (now `ADMIN_ONLY` for `auto_attachment` origin). Actions dispatched via `chrome_events.py` (server-side admin re-check):

```
draft-decision action  →  _h_draft_approve / _h_draft_refine / _h_draft_discard
  guard: "admin" in roles  (else: audit agent_lifecycle/ rejected outcome=failure; show "requires admin"; no-op)
```

### Decision table (at approval)
| Security gate | Self-test | Admin action | Result |
|---|---|---|---|
| CRITICAL | any | (blocked) | `attachment_parser.status='failed'`; never live; reason shown; refine/discard |
| HIGH | any | admin approve | requires explicit admin override (pending_review semantics); else stays pending |
| clean | passed | admin approve | **promote global** (below) |
| clean | failed | admin approve | blocked until refined to a passing self-test |
| any | any | admin discard | `status='discarded'`; no capability added; uploader told type unreadable |

## Global promotion (on admin approve)

`lifecycle.approve_agent(draft_id)` then:
1. `set_agent_ownership(agent_id, owner_email=<system/admin>, is_public=True)` — **global** (vs 027's per-user `is_public=False`).
2. Enable the read scope so the `parse_<ext>` tool is dispatchable by every user.
3. `attachment_parser`: `status='live'`, set `live_agent_id`, `tool_name`, `approved_by=<admin>`, `updated_at`.
4. **Re-parse trigger**: using `draft_agents.source_attachment_id`, parse the original file and continue the uploader's request; deliver the result to the uploader's chat.
5. Audit `agent_lifecycle / approved`, `correlation_id=draft_id`, `agent_id=<live>`.

After this, every subsequent upload of that type resolves to `parser_status="covered"` via the `attachment_parser` registry.

## Invariants (fail-closed)

- **I1** No auto-generated parser code executes against a user file except inside the security gate + isolated self-test, or after admin approval. (FR-019, SC-005)
- **I2** Exactly one draft per format gap while pending (unique `gap_fingerprint`). (FR-018, SC-007)
- **I3** Approval requires the `admin` role, enforced server-side; the uploading user cannot self-approve. (FR-015)
- **I4** A promoted parser is global and audited; its provenance (gap, source attachment, approver) is recoverable from `attachment_parser` + `audit_events` by `correlation_id`. (FR-017, FR-023)
- **I5** Disabled flag or any failure ⇒ "cannot read this type yet"; never a silent empty result or silent execution. (R9, FR-010/FR-019)
