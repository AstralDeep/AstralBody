"""
A2A Bridge — Type conversion between custom protocol types and official a2a-sdk types.

Maps:
- Custom AgentCard/AgentSkill <-> a2a.types.AgentCard/AgentSkill
- MCPRequest/MCPResponse <-> a2a.types.Message with DataPart/TextPart
"""
import os
import uuid
import logging
from typing import Optional, Dict, Any, List

from a2a.types import (
    AgentCard as A2AAgentCard,
    AgentSkill as A2AAgentSkill,
    AgentCapabilities,
    AgentProvider,
    Message as A2AMessage,
    Part,
    TextPart,
    DataPart,
    Role,
    SecurityScheme,
)

from shared.protocol import (
    AgentCard as CustomAgentCard,
    AgentSkill as CustomAgentSkill,
    MCPRequest,
    MCPResponse,
)

logger = logging.getLogger("A2ABridge")


def custom_skill_to_a2a(skill: CustomAgentSkill) -> A2AAgentSkill:
    """Convert a custom AgentSkill to an official A2A AgentSkill."""
    tags = list(skill.tags) if skill.tags else []
    if skill.scope:
        tags.append(f"scope:{skill.scope}")

    return A2AAgentSkill(
        id=skill.id or skill.name,
        name=skill.name,
        description=skill.description,
        tags=tags,
        input_modes=["application/json"],
        output_modes=["application/json"],
    )


def custom_card_to_a2a(card: CustomAgentCard, base_url: str) -> A2AAgentCard:
    """Convert a custom AgentCard to an official A2A AgentCard.

    Args:
        card: Our custom AgentCard dataclass.
        base_url: The agent's HTTP base URL (e.g. "http://localhost:9003").
    """
    skills = [custom_skill_to_a2a(s) for s in card.skills]

    # Build security schemes from Keycloak config
    authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
    security_schemes = None
    security = None
    if authority:
        security_schemes = {
            "keycloak_oidc": SecurityScheme(
                type="openIdConnect",
                openIdConnectUrl=f"{authority}/.well-known/openid-configuration",
            )
        }
        security = [{"keycloak_oidc": ["tools:read", "tools:write", "tools:search", "tools:system"]}]

    return A2AAgentCard(
        name=card.name,
        description=card.description,
        url=base_url,
        version=card.version or "1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        skills=skills,
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        protocol_version="0.3.0",
        preferred_transport="JSONRPC",
        provider=AgentProvider(
            organization="AstralBody",
            url=os.getenv("PUBLIC_BASE_URL", "http://localhost:5173"),
        ),
        security_schemes=security_schemes,
        security=security,
    )


def a2a_skill_to_custom(skill: A2AAgentSkill) -> CustomAgentSkill:
    """Convert an official A2A AgentSkill to our custom AgentSkill."""
    scope = "tools:read"  # default
    tags = []
    for tag in (skill.tags or []):
        if tag.startswith("scope:"):
            scope = tag[len("scope:"):]
        else:
            tags.append(tag)

    return CustomAgentSkill(
        name=skill.name,
        description=skill.description,
        id=skill.id,
        tags=tags,
        scope=scope,
    )


def a2a_card_to_custom(a2a_card: A2AAgentCard) -> CustomAgentCard:
    """Convert an official A2A AgentCard to our custom AgentCard.

    The agent_id is derived from the card name (slugified) if not available
    from the URL or metadata.
    """
    skills = [a2a_skill_to_custom(s) for s in a2a_card.skills]

    # Try to derive agent_id from the URL or name
    agent_id = a2a_card.url.rstrip("/").split("/")[-1] if a2a_card.url else a2a_card.name.lower().replace(" ", "-")

    metadata = {}
    if a2a_card.provider:
        metadata["provider"] = {
            "organization": a2a_card.provider.organization,
            "url": a2a_card.provider.url,
        }
    metadata["a2a_url"] = a2a_card.url
    metadata["protocol_version"] = a2a_card.protocol_version
    metadata["preferred_transport"] = a2a_card.preferred_transport
    metadata["external"] = True  # Flag: this agent was discovered via A2A, not WebSocket

    return CustomAgentCard(
        name=a2a_card.name,
        description=a2a_card.description,
        agent_id=agent_id,
        version=a2a_card.version,
        skills=skills,
        metadata=metadata,
    )


def mcp_response_to_a2a_message(resp: MCPResponse, task_id: str) -> A2AMessage:
    """Convert an MCPResponse to an A2A Message with appropriate parts.

    - result -> DataPart with the result data
    - ui_components -> DataPart with {"_ui_components": [...]}
    - error -> TextPart with error description
    """
    parts: List[Part] = []

    if resp.error:
        error_msg = resp.error.get("message", "Unknown error") if isinstance(resp.error, dict) else str(resp.error)
        parts.append(Part(root=TextPart(text=f"Error: {error_msg}")))
        # Still include ui_components if present (e.g. error alerts)
        if resp.ui_components:
            parts.append(Part(root=DataPart(data={"_ui_components": resp.ui_components})))
    else:
        if resp.result is not None:
            if isinstance(resp.result, dict):
                parts.append(Part(root=DataPart(data=resp.result)))
            else:
                parts.append(Part(root=TextPart(text=str(resp.result))))

        if resp.ui_components:
            parts.append(Part(root=DataPart(
                data={"_ui_components": resp.ui_components},
                metadata={"type": "ui_components"},
            )))

    if not parts:
        parts.append(Part(root=TextPart(text="OK")))

    return A2AMessage(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=parts,
        task_id=task_id,
    )


def a2a_message_to_mcp_request(msg: A2AMessage, request_id: Optional[str] = None) -> Optional[MCPRequest]:
    """Extract an MCPRequest from an incoming A2A Message.

    Looks for a DataPart containing:
    {"method": "tools/call", "name": "tool_name", "arguments": {...}}

    If no such DataPart is found, returns None (the message may be natural language).
    """
    for part in msg.parts:
        inner = part.root if hasattr(part, 'root') else part
        if isinstance(inner, DataPart) and isinstance(inner.data, dict):
            data = inner.data
            if data.get("method") == "tools/call" and "name" in data:
                return MCPRequest(
                    request_id=request_id or f"a2a_{uuid.uuid4().hex[:12]}",
                    method="tools/call",
                    params={
                        "name": data["name"],
                        "arguments": data.get("arguments", {}),
                    },
                )
            elif data.get("method") == "tools/list":
                return MCPRequest(
                    request_id=request_id or f"a2a_{uuid.uuid4().hex[:12]}",
                    method="tools/list",
                    params={},
                )
    return None


def extract_text_from_a2a_message(msg: A2AMessage) -> str:
    """Extract plain text content from an A2A Message (for natural language routing)."""
    texts = []
    for part in msg.parts:
        inner = part.root if hasattr(part, 'root') else part
        if isinstance(inner, TextPart):
            texts.append(inner.text)
    return "\n".join(texts)


def a2a_response_to_mcp_response(
    task_or_message,
    request_id: str,
) -> MCPResponse:
    """Convert an A2A task/message response back to an MCPResponse.

    Handles both Task objects (with artifacts) and direct Message objects.
    """
    from a2a.types import Task, TaskState, Message as A2AMsg

    if isinstance(task_or_message, A2AMsg):
        return _message_to_mcp_response(task_or_message, request_id)

    if isinstance(task_or_message, Task):
        task = task_or_message
        if task.status and task.status.state == TaskState.failed:
            error_msg = "Task failed"
            if task.status.message:
                for p in task.status.message.parts:
                    inner = p.root if hasattr(p, 'root') else p
                    if isinstance(inner, TextPart):
                        error_msg = inner.text
                        break
            return MCPResponse(
                request_id=request_id,
                error={"code": -32000, "message": error_msg, "retryable": False},
            )

        # Extract result from artifacts
        result = None
        ui_components = None
        if task.artifacts:
            for artifact in task.artifacts:
                for p in artifact.parts:
                    inner = p.root if hasattr(p, 'root') else p
                    if isinstance(inner, DataPart):
                        if "_ui_components" in inner.data:
                            ui_components = inner.data["_ui_components"]
                        else:
                            result = inner.data
                    elif isinstance(inner, TextPart):
                        if result is None:
                            result = inner.text

        # Also check the final status message
        if task.status and task.status.message:
            msg_resp = _message_to_mcp_response(task.status.message, request_id)
            if result is None:
                result = msg_resp.result
            if ui_components is None:
                ui_components = msg_resp.ui_components

        return MCPResponse(
            request_id=request_id,
            result=result,
            ui_components=ui_components,
        )

    # Fallback
    return MCPResponse(
        request_id=request_id,
        error={"code": -32000, "message": f"Unexpected response type: {type(task_or_message)}", "retryable": False},
    )


def _message_to_mcp_response(msg: A2AMessage, request_id: str) -> MCPResponse:
    """Convert a single A2A Message to MCPResponse."""
    result = None
    ui_components = None

    for p in msg.parts:
        inner = p.root if hasattr(p, 'root') else p
        if isinstance(inner, DataPart):
            if "_ui_components" in inner.data:
                ui_components = inner.data["_ui_components"]
            elif result is None:
                result = inner.data
        elif isinstance(inner, TextPart):
            if result is None:
                result = inner.text

    return MCPResponse(
        request_id=request_id,
        result=result,
        ui_components=ui_components,
    )
