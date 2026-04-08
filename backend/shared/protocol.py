"""
Protocol message types for inter-agent communication.

Defines:
- MCP Protocol: MCPRequest, MCPResponse
- UI Protocol: UIEvent, UIRender, UIUpdate, UIAppend
- A2A Protocol: AgentCard, AgentSkill, RegisterAgent, RegisterUI
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
        return Message(**data)

# --- MCP Protocol Wrappers ---
@dataclass
class MCPRequest(Message):
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

# --- UI Protocol ---
@dataclass
class UIEvent(Message):
    type: str = "ui_event"
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None

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
