"""
Pydantic models for the AstralBody REST API.

These models define the request/response shapes for all REST endpoints,
powering the auto-generated OpenAPI documentation at /docs.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class ChatStatusEnum(str, Enum):
    idle = "idle"
    thinking = "thinking"
    executing = "executing"
    done = "done"


# =============================================================================
# Chat Models
# =============================================================================

class ChatMessageRequest(BaseModel):
    """Send a chat message. The response streams back via WebSocket."""
    message: str = Field(..., description="The user's message text")
    display_message: Optional[str] = Field(None, description="Optional formatted version of the message to display in the UI")

    model_config = {"json_schema_extra": {"examples": [{"message": "What is the weather in Lexington, KY?"}]}}


class ChatMessageResponse(BaseModel):
    """Acknowledgement that the message was received. Actual results stream via WebSocket."""
    chat_id: str = Field(..., description="The chat session ID")
    status: str = Field("accepted", description="Message acceptance status")
    message: str = Field("Message received. Results will stream via WebSocket.", description="Info message")


class ChatSummary(BaseModel):
    """Summary of a chat session (metadata only, no messages)."""
    id: str
    title: str
    updated_at: int = Field(..., description="Unix timestamp in milliseconds")
    preview: str = Field("", description="Preview of the last message")
    has_saved_components: Optional[bool] = None


class ChatMessage(BaseModel):
    """A single message in a chat session."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: Any = Field(..., description="Message content — string for user, component list for assistant")
    timestamp: Optional[int] = None


class ChatDetail(BaseModel):
    """Full chat session with messages."""
    id: str
    title: str
    updated_at: int
    messages: List[ChatMessage] = []


class ChatListResponse(BaseModel):
    """List of recent chat sessions."""
    chats: List[ChatSummary]


class ChatCreateResponse(BaseModel):
    """Response when a new chat is created."""
    chat_id: str
    message: str = "Chat created successfully"


class ChatDetailResponse(BaseModel):
    """Full chat detail response."""
    chat: ChatDetail


class DeleteResponse(BaseModel):
    """Generic delete confirmation."""
    success: bool = True
    message: str = "Deleted successfully"


# =============================================================================
# Component Models
# =============================================================================

class ComponentSaveRequest(BaseModel):
    """Save a UI component to the dashboard."""
    component_data: Dict[str, Any] = Field(..., description="The component tree (JSON object)")
    component_type: str = Field(..., description="Type of component (e.g. 'card', 'table', 'bar_chart')")
    title: Optional[str] = Field(None, description="Display title for the saved component")


class SavedComponent(BaseModel):
    """A saved UI component."""
    id: str
    chat_id: str
    component_data: Dict[str, Any]
    component_type: str
    title: str
    created_at: int


class ComponentSaveResponse(BaseModel):
    """Response after saving a component."""
    component: SavedComponent


class ComponentListResponse(BaseModel):
    """List of saved components."""
    components: List[SavedComponent]


class ComponentCombineRequest(BaseModel):
    """Combine two components into one using LLM."""
    source_id: str = Field(..., description="ID of the first component")
    target_id: str = Field(..., description="ID of the second component")


class ComponentCondenseRequest(BaseModel):
    """Condense multiple components into fewer using LLM."""
    component_ids: List[str] = Field(..., min_length=2, description="IDs of components to condense")


class ComponentCombineResponse(BaseModel):
    """Result of combining/condensing components."""
    removed_ids: List[str]
    new_components: List[SavedComponent]


# =============================================================================
# Agent Models
# =============================================================================

class AgentTool(BaseModel):
    """A tool exposed by an agent."""
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None


class AgentInfo(BaseModel):
    """Information about a connected agent."""
    id: str
    name: str
    description: Optional[str] = None
    tools: List[AgentTool] = []
    permissions: Optional[Dict[str, bool]] = Field(None, description="Per-tool permission map (tool_name: allowed)")
    security_flags: Optional[Dict[str, Any]] = Field(None, description="System-level security flags per tool from proactive review")
    status: str = "connected"
    owner_email: Optional[str] = Field(None, description="Email of the agent owner")
    is_public: bool = Field(False, description="Whether the agent is publicly available to all users")


class AgentListResponse(BaseModel):
    """List of connected agents."""
    agents: List[AgentInfo]


class AgentPermissionsRequest(BaseModel):
    """Update tool permissions for an agent."""
    permissions: Dict[str, bool] = Field(..., description="Map of tool_name to allowed (true/false)")

    model_config = {"json_schema_extra": {"examples": [{"permissions": {"modify_data": False, "get_system_status": True}}]}}


class AgentPermissionsResponse(BaseModel):
    """Current tool permissions for an agent."""
    agent_id: str
    agent_name: str
    permissions: Dict[str, bool] = Field(..., description="Map of tool_name to allowed (true/false)")
    tool_descriptions: Optional[Dict[str, str]] = Field(None, description="Map of tool_name to description")
    security_flags: Optional[Dict[str, Any]] = Field(None, description="System-level security flags per tool from proactive review")


class AgentVisibilityRequest(BaseModel):
    """Toggle agent public/private visibility."""
    is_public: bool = Field(..., description="Whether the agent should be publicly available")


class CredentialSetRequest(BaseModel):
    """Set one or more credentials for an agent."""
    credentials: Dict[str, str] = Field(..., description="Map of credential_key to value (e.g. LINKEDIN_ACCESS_TOKEN: abc123)")

    model_config = {"json_schema_extra": {"examples": [{"credentials": {"LINKEDIN_ACCESS_TOKEN": "abc123", "LINKEDIN_ORG_ID": "12345"}}]}}


class CredentialListResponse(BaseModel):
    """List of stored credential keys for an agent (values are never returned)."""
    agent_id: str
    agent_name: str
    credential_keys: List[str] = Field(default_factory=list, description="Stored credential key names (no values)")
    required_credentials: List[Dict[str, Any]] = Field(default_factory=list, description="Credentials the agent declares it needs")


class CredentialDeleteResponse(BaseModel):
    """Confirmation of credential deletion."""
    success: bool = True
    message: str = "Credential deleted successfully"


# =============================================================================
# Dashboard / System Models
# =============================================================================

class DashboardResponse(BaseModel):
    """System configuration and dashboard data."""
    agents: List[AgentInfo]
    total_tools: int


# =============================================================================
# Auth / Upload Models
# =============================================================================

class UploadResponse(BaseModel):
    """File upload response."""
    status: str = "success"
    filename: str
    file_path: str
    user_id: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None


# =============================================================================
# WebSocket Protocol Documentation (for OpenAPI description)
# =============================================================================

WS_PROTOCOL_DOCS = """
## WebSocket Protocol

Connect to `ws://<host>:<port>/ws` for real-time communication.

### Authentication

After connecting, send a `register_ui` message with your JWT token:

```json
{
    "type": "register_ui",
    "token": "<JWT_TOKEN>",
    "capabilities": ["render", "stream"],
    "session_id": "ui-<timestamp>"
}
```

### Client → Server Messages

All client messages use the `ui_event` type with an `action` field:

| Action | Payload | Description |
|--------|---------|-------------|
| `chat_message` | `{message, chat_id?, display_message?}` | Send a chat message |
| `get_history` | `{}` | Request list of recent chats |
| `load_chat` | `{chat_id}` | Load a specific chat with messages |
| `new_chat` | `{}` | Create a new chat session |
| `get_dashboard` | `{}` | Request system config/dashboard |
| `discover_agents` | `{}` | Request list of connected agents |
| `save_component` | `{chat_id, component_data, component_type, title?}` | Save a UI component |
| `get_saved_components` | `{chat_id?}` | Get saved components |
| `delete_saved_component` | `{component_id}` | Delete a saved component |
| `combine_components` | `{source_id, target_id}` | Combine two components via LLM |
| `condense_components` | `{component_ids[]}` | Condense multiple components via LLM |

**Message format:**
```json
{
    "type": "ui_event",
    "action": "<action_name>",
    "session_id": "<optional_chat_id>",
    "payload": { ... }
}
```

### Server → Client Messages

| Type | Fields | Description |
|------|--------|-------------|
| `system_config` | `{config: {agents[], total_tools}}` | Dashboard/system info |
| `agent_registered` | `{agent_id, name, tools[]}` | New agent connected |
| `agent_list` | `{agents[]}` | Full agent list |
| `chat_status` | `{status, message}` | Processing status (thinking/executing/done) |
| `chat_created` | `{payload: {chat_id, from_message}}` | New chat created |
| `chat_loaded` | `{chat: {id, title, messages[]}}` | Chat data loaded |
| `history_list` | `{chats[]}` | List of recent chats |
| `ui_render` | `{components[]}` | Render UI components (new message) |
| `ui_update` | `{components[]}` | Update current UI components |
| `ui_append` | `{components[]}` | Append to current UI components |
| `saved_components_list` | `{components[]}` | Saved components data |
| `component_saved` | `{component: {...}}` | Component save confirmation |
| `component_deleted` | `{component_id}` | Component delete confirmation |
| `combine_status` | `{status, message}` | Component combine in progress |
| `components_combined` | `{removed_ids[], new_components[]}` | Combine result |
| `components_condensed` | `{removed_ids[], new_components[]}` | Condense result |
| `combine_error` | `{error}` | Combine/condense failed |

### UI Component Types

Components are JSON objects with a `type` field:

`text`, `card`, `metric`, `table`, `grid`, `container`, `list`, `alert`,
`progress`, `bar_chart`, `line_chart`, `pie_chart`, `plotly_chart`,
`code`, `divider`, `collapsible`, `image`, `tabs`, `button`, `input`
"""
