# Contract: Driver

**Feature**: 032 | Phase 1 | Authoritative for the surface that both modes implement (FR-030). One core, two drivers.

```python
class Driver(Protocol):
    mode: Literal["in_process", "external"]
    auth_mode: Literal["real_keycloak", "mock_inprocess"]

    async def authenticate(self, principal: Principal) -> Session: ...
    async def upload(self, session: Session, fixture: FixtureRef) -> Attachment: ...
    async def send_query(self, session: Session, chat_id: str, query: str,
                         attachments: list[Attachment]) -> CapturedEvidence: ...
    async def read_workspace(self, session: Session, chat_id: str) -> list[dict]: ...
    async def read_audit(self, principal: Principal) -> tuple[list[dict], bool | str]: ...  # rows, chain_ok
    async def set_scope(self, principal: Principal, agent_id: str,
                        scope: str, enabled: bool) -> None: ...
    async def trigger_component_action(self, session: Session, chat_id: str,
                                       component_id: str, patch: dict) -> CapturedEvidence: ...
    async def teardown(self) -> None: ...
```

## In-process driver (the CI gate)

- `authenticate`: register a namespaced session directly (`orch.ui_sessions[ws] = {...}`); no HTTP auth.
- `upload`: write the blob + `user_attachments` row exactly as the upload route does (real ownership/scoping); category from `content_type`.
- `send_query`: assign the **scripted LLM** (`orch._call_llm = scripted_for(scenario)`), drive `orch.handle_chat_message(capture_ws, query, chat_id, user_id=…, attachments=[…])`, return the buffered messages + flattened components + workspace + audit as `CapturedEvidence`.
- `read_audit`: `AuditRepository.list_for_user` + `verify_chain(user_id)`.
- `set_scope`: `tool_permissions.set_agent_scopes`.
- `trigger_component_action`: drive the real `component_action` ui_event path.
- `teardown`: delete namespaced rows + blobs (D14).

## External driver (opt-in, not a gate)

- `authenticate`: real Keycloak via env-named creds + RFC 8693 exchange; degrades to mock with a run flag if unreachable (auth_mode reported).
- `upload`: `httpx POST /api/upload`.
- `send_query`: `websockets` connect `ws://<base>/ws` → `register_ui{token,device}` → `chat_message{payload:{message,attachments}}`; collect `ui_render`/`ui_upsert` until quiescent or budget.
- `read_workspace`/`read_audit`: REST (`/api/chats/{id}`, `/api/audit`).
- The real LLM produces components; the SAME deterministic checks run on the captured output.

## Invariants (both drivers)

- Identical `CapturedEvidence` shape → identical checks (FR-030 "same property verdicts").
- Credentials by env NAME only; redaction before any persistence (FR-022).
- Bounded per call (timeouts/turn caps); a hang becomes `errored_observation`, never an infinite wait (FR-005/033).
