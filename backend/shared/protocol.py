"""
Protocol message types for inter-agent communication.

Defines:
- MCP Protocol: MCPRequest, MCPResponse
- UI Protocol: UIEvent, UIRender, UIUpdate, UIAppend
- A2A Protocol: AgentCard, AgentSkill, RegisterAgent, RegisterUI
- Tool Streaming: ToolStreamData, ToolStreamEnd, ToolStreamCancel
  (see specs/001-tool-stream-ui/contracts/protocol-messages.md §B)
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
import json

# --- Base Message ---
@dataclass
class Message:
    type: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(json_str: str) -> 'Message':
        data = json.loads(json_str)
        msg_type = data.get('type')
        if msg_type == 'mcp_request':
            return MCPRequest(**data)
        elif msg_type == 'mcp_response':
            return MCPResponse(**data)
        elif msg_type == 'ui_event':
            return UIEvent(**data)
        elif msg_type == 'ui_render':
            return UIRender(**data)
        elif msg_type == 'ui_update':
            return UIUpdate(**data)
        elif msg_type == 'ui_append':
            return UIAppend(**data)
        elif msg_type == 'register_agent':
            return RegisterAgent.from_json(json_str)
        elif msg_type == 'register_ui':
            return RegisterUI.from_json(json_str)
        elif msg_type == 'tool_progress':
            return ToolProgress(**data)
        elif msg_type == 'tool_stream_data':
            return ToolStreamData(**data)
        elif msg_type == 'tool_stream_end':
            return ToolStreamEnd(**data)
        elif msg_type == 'tool_stream_cancel':
            return ToolStreamCancel(**data)
        elif msg_type == 'audit_append':
            return AuditAppend(**data)
        return Message(**data)

# --- MCP Protocol Wrappers ---
@dataclass
class MCPRequest(Message):
    """A tool-call request from orchestrator to agent.

    For streaming tools (001-tool-stream-ui), the orchestrator sets the
    following conventional keys inside ``params`` (no schema change required
    because params is already an open dict):

    - ``_stream``: ``True`` when the orchestrator wants the agent to treat
      the request as long-lived and emit ``ToolStreamData`` chunks instead of
      a single ``MCPResponse``.
    - ``_stream_id``: The canonical ``stream_id`` the agent must echo on
      every emitted chunk so the orchestrator can correlate them back to the
      originating ``StreamSubscription``.

    Agents that do not understand these keys (e.g. when ``FF_TOOL_STREAMING``
    is off) MUST ignore them and run the tool to completion as a normal
    one-shot call.
    """
    type: str = "mcp_request"
    request_id: str = ""
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MCPResponse(Message):
    type: str = "mcp_response"
    request_id: str = ""
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    ui_components: Optional[List[Dict[str, Any]]] = None
    # Feature 004: correlation_id propagated from the orchestrator's
    # ToolDispatchAudit context so every produced UI component can be
    # tagged with the originating tool dispatch's audit correlation_id.
    # The orchestrator stamps this onto the response after the audit
    # context closes; agents do not set it.
    correlation_id: Optional[str] = None

# --- UI Protocol ---
@dataclass
class UIEvent(Message):
    type: str = "ui_event"
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None


# --- Feature 004 UI event action names ---------------------------------
# The UIEvent message above is open (action is a free string; payload is
# a free dict) so adding new actions does not require a new dataclass.
# These constants exist purely to make the wire contract greppable and to
# document the valid set in one place.

# Client → server
UI_ACTION_COMPONENT_FEEDBACK = "component_feedback"
UI_ACTION_FEEDBACK_RETRACT = "feedback_retract"
UI_ACTION_FEEDBACK_AMEND = "feedback_amend"

# Server → client (delivered as ui_event messages on the same socket).
UI_ACTION_COMPONENT_FEEDBACK_ACK = "component_feedback_ack"
UI_ACTION_COMPONENT_FEEDBACK_ERROR = "component_feedback_error"
UI_ACTION_FEEDBACK_RETRACT_ACK = "feedback_retract_ack"
UI_ACTION_FEEDBACK_AMEND_ACK = "feedback_amend_ack"

# Optional metadata key attached to each component dict in UIRender.components
# when the component originated from a tool dispatch. The value is the
# audit-log correlation_id of that dispatch (string). Frontend consumers
# treat this as an opaque identifier used to scope feedback submissions.
UI_RENDER_META_CORRELATION_ID = "_source_correlation_id"

@dataclass
class UIRender(Message):
    type: str = "ui_render"
    components: List[Dict[str, Any]] = field(default_factory=list)
    target: str = "canvas"  # "canvas" for SDUI main area, "chat" for floating chat panel

@dataclass
class UIUpdate(Message):
    type: str = "ui_update"
    components: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class UIAppend(Message):
    type: str = "ui_append"
    target_id: str = ""
    data: Any = None

# --- Agent2Agent Protocol ---
@dataclass
class AgentSkill:
    name: str
    description: str
    id: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    scope: str = ""  # Required scope: "tools:read", "tools:write", "tools:search", "tools:system"
    metadata: Dict[str, Any] = field(default_factory=dict)  # Optional metadata (e.g. streamable config)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class AgentCard:
    name: str
    description: str
    agent_id: str
    version: str = "0.1.0"
    skills: List[AgentSkill] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'AgentCard':
        skills_data = data.get('skills', [])
        skills = [AgentSkill(**s) if isinstance(s, dict) else s for s in skills_data]
        card_data = {k: v for k, v in data.items() if k not in ('skills',)}
        return AgentCard(skills=skills, **card_data)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "agent_id": self.agent_id,
            "version": self.version,
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description,
                 "input_schema": s.input_schema, "tags": s.tags,
                 "scope": s.scope}
                for s in self.skills
            ] if self.skills else []
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

@dataclass
class RegisterAgent(Message):
    type: str = "register_agent"
    agent_card: Optional[AgentCard] = None

    def to_json(self) -> str:
        data = asdict(self)
        if self.agent_card:
            data['agent_card'] = asdict(self.agent_card)
        return json.dumps(data)

    @staticmethod
    def from_json(json_str: str) -> 'RegisterAgent':
        data = json.loads(json_str)
        if 'agent_card' in data and data['agent_card']:
            data['agent_card'] = AgentCard.from_dict(data['agent_card'])
        return RegisterAgent(**data)

# --- Agent Creation Protocol ---
@dataclass
class AgentCreationProgress(Message):
    """Progress update during agent creation/refinement/approval."""
    type: str = "agent_creation_progress"
    draft_id: str = ""
    step: str = ""          # e.g., "generating_template", "generating_tools", "security_scan", "writing_files"
    message: str = ""       # human-readable progress message
    status: str = ""        # pending | generating | generated | testing | analyzing | approved | rejected | live | error
    detail: Optional[Dict[str, Any]] = None  # optional extra data (e.g., security report)

@dataclass
class ToolProgress(Message):
    """Real-time progress update during tool execution.

    Agents can send these messages during long-running tool calls so the
    orchestrator can forward them to the UI client immediately.
    """
    type: str = "tool_progress"
    tool_name: str = ""
    agent_id: str = ""
    message: str = ""
    percentage: Optional[int] = None  # 0-100, or None if indeterminate
    metadata: Dict[str, Any] = field(default_factory=dict)

# --- Tool Streaming (001-tool-stream-ui) ---
@dataclass
class ToolStreamData(Message):
    """One streaming chunk from an agent tool back to the orchestrator.

    Sent by an agent in response to an ``MCPRequest`` whose ``params._stream``
    is ``True``. The orchestrator forwards (after ROTE adaptation and per-
    subscriber authorization) to every websocket subscribed to the
    corresponding ``StreamSubscription`` as a ``ui_stream_data`` message.

    See specs/001-tool-stream-ui/contracts/protocol-messages.md §B2.
    """
    type: str = "tool_stream_data"
    request_id: str = ""
    stream_id: str = ""
    agent_id: str = ""
    tool_name: str = ""
    seq: int = 0
    components: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Any] = None
    terminal: bool = False
    error: Optional[Dict[str, Any]] = None  # see §A5: code, message, phase, attempt, next_retry_at_ms, retryable


@dataclass
class ToolStreamEnd(Message):
    """Sent by an agent when a streaming tool's async generator returns
    naturally (no more data, no error). Orchestrator forwards as a final
    ``ui_stream_data`` chunk with ``terminal: true`` and removes the
    subscription.

    See specs/001-tool-stream-ui/contracts/protocol-messages.md §B4.
    """
    type: str = "tool_stream_end"
    request_id: str = ""
    stream_id: str = ""


@dataclass
class ToolStreamCancel(Message):
    """Sent by the orchestrator to an agent to ask it to stop a streaming
    tool. Triggered by user-leaves-chat, explicit unsubscribe, token
    revocation, or dormant TTL expiry. The agent MUST close the underlying
    async generator (which propagates ``GeneratorExit`` to any ``finally``
    cleanup) within 1 second.

    See specs/001-tool-stream-ui/contracts/protocol-messages.md §B3.
    """
    type: str = "tool_stream_cancel"
    request_id: str = ""
    stream_id: str = ""


@dataclass
class AuditAppend(Message):
    """Server→client live audit-log append (feature 003-agent-audit-log).

    Sent on the user's existing WebSocket immediately after a new audit
    row is inserted. The ``event`` payload matches the ``AuditEventDTO``
    JSON Schema (see backend/audit/schemas.py and
    specs/003-agent-audit-log/contracts/audit-event-schema.json) — it
    is a strict subset of the underlying database row that omits
    internal AU-9 fields. Server-side filtering by user_id is mandatory:
    a connection authenticated as user A MUST NEVER receive an
    ``audit_append`` whose event belongs to user B (FR-007 / FR-019).
    """
    type: str = "audit_append"
    event: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegisterUI(Message):
    type: str = "register_ui"
    capabilities: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    token: Optional[str] = None
    device: Optional[Dict[str, Any]] = None  # ROTE: frontend device capabilities

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(json_str: str) -> 'RegisterUI':
        data = json.loads(json_str)
        return RegisterUI(**data)


# --- Streaming tool metadata validation (001-tool-stream-ui) ---
def validate_streaming_metadata(metadata: Dict[str, Any]) -> None:
    """Validate the streaming-related fields of an ``AgentSkill.metadata``.

    Called by the orchestrator at ``RegisterAgent`` time for any tool whose
    metadata declares ``streamable: True``. Raises ``ValueError`` with a
    human-readable message on the first invariant violation.

    Required when streamable=True:
    - ``streaming_kind`` MUST be ``"push"`` or ``"poll"``.

    Optional but constrained:
    - ``min_fps`` and ``max_fps`` (default 5/30) MUST satisfy
      ``1 <= min_fps <= max_fps <= 60``.
    - ``max_chunk_bytes`` (default 65536) MUST be ``<= 1 << 20`` (1 MiB hard
      ceiling — anything larger indicates a tool that should be paginated,
      not streamed).
    - ``default_interval_s`` (poll only) MUST be a positive number when
      present.

    See specs/001-tool-stream-ui/contracts/protocol-messages.md §B5.
    """
    if not metadata.get("streamable"):
        return  # nothing to validate
    kind = metadata.get("streaming_kind")
    if kind not in ("push", "poll"):
        raise ValueError(
            f"streamable tool metadata must set streaming_kind to 'push' or "
            f"'poll', got {kind!r}"
        )
    min_fps = metadata.get("min_fps", 5)
    max_fps = metadata.get("max_fps", 30)
    if not isinstance(min_fps, int) or not isinstance(max_fps, int):
        raise ValueError(
            f"min_fps and max_fps must be integers, got {min_fps!r}, {max_fps!r}"
        )
    if not (1 <= min_fps <= max_fps <= 60):
        raise ValueError(
            f"streamable tool fps clamp invalid: must satisfy "
            f"1 <= min_fps <= max_fps <= 60, got min={min_fps}, max={max_fps}"
        )
    max_chunk_bytes = metadata.get("max_chunk_bytes", 65536)
    if not isinstance(max_chunk_bytes, int) or max_chunk_bytes <= 0:
        raise ValueError(
            f"max_chunk_bytes must be a positive integer, got {max_chunk_bytes!r}"
        )
    if max_chunk_bytes > (1 << 20):
        raise ValueError(
            f"max_chunk_bytes={max_chunk_bytes} exceeds 1 MiB hard ceiling; "
            f"streaming is not the right pattern for chunks this large"
        )
    if kind == "poll":
        interval = metadata.get("default_interval_s")
        if interval is not None and (not isinstance(interval, (int, float)) or interval <= 0):
            raise ValueError(
                f"default_interval_s must be a positive number, got {interval!r}"
            )
