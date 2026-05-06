"""
Orchestrator — Central hub for the multi-agent system.

Responsibilities:
1. WebSocket server for UI clients (/ws) and agent connections
2. A2A agent discovery via agent cards
3. LLM-powered tool routing (chat message → tool selection)
4. Parallel MCP tool execution across agents
5. Dynamic UI assembly (combines tool outputs into cohesive layouts)
"""
import asyncio
import json
import time
import os
import sys
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import asdict

import websockets
import websockets.exceptions
import aiohttp
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt as jose_jwt
from dotenv import load_dotenv
from openai import OpenAI
from httpx import Timeout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager
from orchestrator.tool_permissions import ToolPermissionManager
from orchestrator.credential_manager import CredentialManager
from orchestrator.delegation import DelegationService
from orchestrator.tool_security import ToolSecurityAnalyzer
from orchestrator.compaction import compact_messages
from orchestrator.hooks import HookManager, HookEvent, HookContext
from orchestrator.task_state import TaskManager, TaskState

from shared.protocol import (
    Message, MCPRequest, MCPResponse, UIEvent, UIRender, UIUpdate,
    RegisterAgent, RegisterUI, AgentCard, AgentSkill, ToolProgress,
    ToolStreamData, ToolStreamEnd, ToolStreamCancel,
    validate_streaming_metadata,
)
from shared.primitives import (
    Container, Text, Card, Grid, Alert, MetricCard, ProgressBar,
    Collapsible, create_ui_response
)
from rote.rote import ROTE
from shared.feature_flags import flags
from orchestrator.stream_manager import StreamManager

load_dotenv(override=False)

PORT = int(os.getenv("ORCHESTRATOR_PORT", 8001))

debug_mode = os.getenv("DEBUG", "false").lower() == "true"
log_level = logging.INFO if debug_mode else logging.WARNING

logging.basicConfig(level=log_level,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('Orchestrator')


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out uvicorn access logs for specific "poll" endpoints
        msg = record.getMessage()
        return "/.well-known/agent-card.json" not in msg

# Filter uvicorn access logs if they exist
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


# Module-level singleton handle, set by Orchestrator.__init__. Used by
# external callers (e.g., feedback.cli) that need to reach into the
# running instance without going through FastAPI app.state.
_ORCH_INSTANCE = None  # type: Optional["Orchestrator"]


# Feature 008-llm-text-only-chat (FR-006a) — appended to the chat system
# prompt whenever a turn dispatches with zero usable tools. Tells the LLM
# (a) it has no tools/agents available, (b) it MUST NOT fabricate tool
# output, (c) when the user asks for an action that would require an
# agent, it should briefly state that no agents are enabled and suggest
# enabling one. The base system prompt for tool-augmented turns is
# unchanged (FR-011).
TEXT_ONLY_SYSTEM_PROMPT_ADDENDUM = """
TEXT-ONLY MODE (no agents currently available):
- You have NO tools or agents available for this turn. Do NOT emit tool calls.
- Do NOT emit any of the following tokens, in any form, as part of your reply
  text — they are tool-call markers and will be visible to the user as garbage:
    <|tool_call|>, <tool_call>, </tool_call>, <|tool_calls_section_begin|>,
    <|tool_calls_section_end|>, [TOOL_CALLS], [/TOOL_CALLS], <function_call>.
  If you would have emitted a tool call, instead write a plain-language
  sentence describing what you would have done and tell the user that no
  agents are enabled — never the raw token form.
- Do NOT fabricate tool output, pretend to have searched/fetched/created anything,
  or invent file/database/API results. If you don't actually know it, say so.
- If the user asks for an action that would normally require an agent (reading
  a file, searching a system, creating/modifying anything outside this chat),
  briefly note that no agents are currently enabled and suggest the user enable
  one from the Agents panel. Then offer the best help you can with text alone.
- For conversational questions, reasoning, summarization, drafting, or general
  knowledge — answer normally as a text-only chat assistant.
"""


# Patterns that represent tool-call tokens leaked into text content. Some
# open-weight LLMs (Llama-style, Qwen-style, etc.) emit these even when
# instructed not to — we strip them post-hoc so the user never sees a raw
# `<|tool_call|>...` artifact in the chat. Order matters only for
# coverage; each pattern is independent.
_LEAKED_TOOL_CALL_PATTERNS = [
    # Llama-style with optional pipe variations:
    #   <|tool_call|> ... <|tool_call|>
    #   <|tool_call> ... <tool_call|>
    re.compile(r"<\|?tool_call\|?>.*?<\|?/?tool_call\|?>", re.IGNORECASE | re.DOTALL),
    # Qwen / generic XML-style tool call wrappers
    re.compile(r"<tool_call>.*?</tool_call>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<function_call>.*?</function_call>", re.IGNORECASE | re.DOTALL),
    # Llama 3 tool-calls-section markers
    re.compile(
        r"<\|tool_calls_section_begin\|>.*?<\|tool_calls_section_end\|>",
        re.IGNORECASE | re.DOTALL,
    ),
    # Mistral / generic bracket form
    re.compile(r"\[TOOL_CALLS\].*?\[/TOOL_CALLS\]", re.IGNORECASE | re.DOTALL),
    # Stray dangling open tags with no close
    re.compile(r"<\|?tool_call\|?>", re.IGNORECASE),
    re.compile(r"<\|tool_calls_section_(?:begin|end)\|>", re.IGNORECASE),
    re.compile(r"\[/?TOOL_CALLS\]", re.IGNORECASE),
]


def _sanitize_text_response(content: str) -> str:
    """Strip leaked tool-call tokens from a text response.

    Some LLMs (especially open-weight Llama-style models) emit their
    tool-call tokenization as plain text when they're asked to invoke a
    tool but no tools are available — leaving the user staring at raw
    `<|tool_call|>...<tool_call|>` markup. The system prompt addendum
    asks the LLM not to do this, but we cannot rely on prompt
    compliance, so we strip the patterns here as a defensive layer.

    If the entire response was a leaked tool call (nothing useful left
    after stripping), returns a friendly fallback so the user gets an
    actionable message instead of an empty bubble.
    """
    if not content:
        return content
    cleaned = content
    for pat in _LEAKED_TOOL_CALL_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return (
            "No agents are currently enabled, so I can't run that for you. "
            "Open the Tools & Agents picker (wrench icon next to the send "
            "button) and re-enable an agent, then try again."
        )
    return cleaned


class Orchestrator:
    def __init__(self):
        self.agents: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.ui_clients: List[websockets.WebSocketServerProtocol] = []
        self.ui_sessions: Dict[websockets.WebSocketServerProtocol, Dict] = {}
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_capabilities: Dict[str, List[Dict]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.pending_ui_sockets: Dict[str, Any] = {}  # request_id -> UI websocket (for progress forwarding)
        self.cancelled_sessions: Dict[str, bool] = {}  # websocket id -> cancelled flag
        self._chat_locks: Dict[int, asyncio.Lock] = {}  # per-websocket lock for chat serialization
        self._registered_events: Dict[int, asyncio.Event] = {}  # gate non-register messages until auth completes

        # Live streaming subscriptions (existing POLLING path — kept for tools
        # that declare streaming_kind == "poll")
        self._stream_tasks: Dict[int, Dict[str, asyncio.Task]] = {}   # ws_id -> {tool_name -> Task}
        self._stream_subs: Dict[int, Dict[str, Dict]] = {}            # ws_id -> {tool_name -> config}
        self._streamable_tools: Dict[str, Dict] = {}                  # tool_name -> {agent_id, default_interval, min_interval, max_interval, kind}
        self._MAX_STREAM_SUBSCRIPTIONS = 10

        # 001-tool-stream-ui: PUSH streaming via StreamManager. Constructed
        # below after self.rote is initialized; the manager wires into
        # _safe_send and ui_sessions for per-subscriber authorization.
        self.stream_manager: Optional[StreamManager] = None  # populated post-init

        # 001-tool-stream-ui: per-ws "currently active chat" tracker. Used by
        # pause_chat / resume on load_chat transitions so the stream manager
        # knows which chat to pause for THIS websocket (each tab has its own
        # active chat — pausing/resuming one tab must not affect others).
        # Keyed by id(websocket).
        self._ws_active_chat: Dict[int, str] = {}

        # Feature 014 — per-active-turn step recorders, keyed by id(websocket).
        # Created at the start of handle_chat_message and torn down at the end
        # of _serialized_chat. The cancel_task handler reads this map to invoke
        # cancel_all_in_flight() (FR-020/021).
        self._chat_recorders: Dict[int, Any] = {}

        # A2A external agent connections (JSON-RPC transport)
        self.a2a_clients: Dict[str, Any] = {}  # agent_id -> A2A client
        self.a2a_agent_cards: Dict[str, Any] = {}  # agent_id -> official A2A AgentCard
        self.agent_urls: Dict[str, str] = {}  # agent_id -> base URL (for peer registry)

        # LLM Client (feature 006-user-llm-config)
        # ----------------------------------------------------------------
        # The operator's .env-supplied credentials are used as the
        # *default* for users who have not configured their own. A user
        # who has configured personal credentials sees those credentials
        # used exclusively (no runtime fallback — FR-003 / FR-009).
        # Per-user credentials are NEVER persisted server-side; they
        # live in `_session_llm_creds`, keyed by id(websocket), and are
        # cleared on socket disconnect (FR-002).
        from llm_config import (
            OperatorDefaultCreds,
            SessionCredentialStore,
            build_llm_client,
            CredentialSource,
            LLMUnavailable,
            ResolvedConfig,
        )
        from llm_config.audit_events import (
            record_llm_call,
            record_llm_unconfigured,
        )
        self._operator_creds = OperatorDefaultCreds.from_env()
        self._session_llm_creds = SessionCredentialStore()
        # Cache the imports as instance attributes so the hot _call_llm
        # path doesn't re-import on every call.
        self._build_llm_client = build_llm_client
        self._CredentialSource = CredentialSource
        self._LLMUnavailable = LLMUnavailable
        self._ResolvedConfig = ResolvedConfig
        self._record_llm_call = record_llm_call
        self._record_llm_unconfigured = record_llm_unconfigured

        # Default model name — used when the operator default is the
        # active credential set. Personal-config callers supply their
        # own model via SessionCreds.model.
        self.llm_model = self._operator_creds.model or os.getenv(
            "LLM_MODEL", "meta-llama/Llama-3.2-90B-Vision-Instruct"
        )

        # Pre-built default OpenAI client. Used directly only for the
        # legacy `_combine_components_llm` call site that does not
        # accept a websocket; user-initiated calls go through
        # `_resolve_llm_client_for(websocket)` instead. May be None when
        # the operator has not provided default credentials, in which
        # case unconfigured users will see the FR-004a "LLM unavailable"
        # prompt.
        if self._operator_creds.is_complete:
            self.llm_client = OpenAI(
                api_key=self._operator_creds.api_key,
                base_url=self._operator_creds.base_url,
                timeout=Timeout(90.0, connect=10.0),
                max_retries=0,  # We handle retries in _call_llm — disable SDK-internal retries
            )
            logger.info(
                f"Operator-default LLM configured: {self._operator_creds.base_url} "
                f"model={self.llm_model}"
            )
        else:
            self.llm_client = None
            logger.warning(
                "No operator-default LLM configured — users without personal "
                "config will see the 'LLM unavailable' prompt"
            )

        # History Manager
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        data_dir = os.path.join(backend_dir, 'data')
        self.history = HistoryManager(data_dir=data_dir)

        # File-tool DB wiring (feature 002-file-uploads). Lets the
        # in-process tool functions resolve attachments without going
        # through HTTP.
        try:
            from agents.general.file_tools import register_database as _register_file_tools_db
            _register_file_tools_db(self.history.db)
        except Exception as _exc:  # pragma: no cover - non-fatal
            logger.warning(f"file_tools DB wiring skipped: {_exc}")

        # Tool Permission Manager (RFC 8693 delegation) — backed by same PostgreSQL DB
        self.tool_permissions = ToolPermissionManager(db=self.history.db, data_dir=data_dir)

        # Per-user credential storage (encrypted API keys for agents)
        self.credential_manager = CredentialManager(db=self.history.db, data_dir=data_dir)

        # Delegation Service (RFC 8693 token exchange)
        self.delegation = DelegationService()

        # Tool Security Analyzer — proactive security review of agent tools
        self.security_analyzer = ToolSecurityAnalyzer()
        self.security_flags: Dict[str, Dict[str, Any]] = {}  # agent_id -> {tool_name: flag_dict}

        # LLM Token Usage Tracking — per-conversation accumulation
        self.token_usage: Dict[str, Dict[str, int]] = {}  # chat_id -> {prompt_tokens, completion_tokens, total_tokens}

        # ROTE — Response Output Translation Engine
        self.rote = ROTE()

        # 001-tool-stream-ui: instantiate the push-streaming manager now that
        # ROTE exists. Wires _safe_send for per-subscriber delivery,
        # ui_sessions for the per-chunk authorization invariant
        # (data-model.md §8), and the streaming agent dispatcher / canceller
        # methods defined below for routing MCPRequest with _stream=True.
        self.stream_manager = StreamManager(
            rote=self.rote,
            send_to_ws=self._safe_send,
            get_user_session=lambda ws: self.ui_sessions.get(ws),
            agent_dispatcher=self._dispatch_stream_request,
            agent_canceller=self._cancel_stream_request,
            validate_chat_ownership=self._validate_chat_ownership_for_stream,
        )

        # Hook/Event System — extensible lifecycle events
        self.hooks = HookManager()

        # Audit log (003-agent-audit-log) — repository, recorder, publisher
        from audit.repository import AuditRepository
        from audit.recorder import Recorder, set_recorder
        from audit.ws_publisher import make_publish_callable
        self.audit_repo = AuditRepository(self.history.db)
        self.audit_recorder = Recorder(self.audit_repo)
        self.audit_recorder.set_publisher(make_publish_callable(self))
        set_recorder(self.audit_recorder)

        # Feature 004 — component feedback & tool-improvement loop
        from feedback.repository import FeedbackRepository
        from feedback.recorder import Recorder as FeedbackRecorder
        self.feedback_repo = FeedbackRepository(self.history.db)
        self.feedback_recorder = FeedbackRecorder(self.feedback_repo)

        # Feature 005 — tool tips and getting started tutorial
        from onboarding.repository import OnboardingRepository
        from onboarding.seed import seed_tutorial_steps
        self.onboarding_repo = OnboardingRepository(self.history.db)
        try:
            seed_tutorial_steps(self.history.db)
        except Exception as exc:  # pragma: no cover — never block startup
            logger.warning(f"Tutorial seed loader failed (non-fatal): {exc}")
        # Publish self as the module-level singleton so the feedback CLI
        # and the pre-pass entrypoint can find the synthesizer without
        # going through FastAPI app.state.
        global _ORCH_INSTANCE
        _ORCH_INSTANCE = self

        # Task State Machine — tracks Re-Act loop execution state
        self.task_manager = TaskManager()

        # Agent Lifecycle Manager — handles user-created draft agents
        from orchestrator.agent_lifecycle import AgentLifecycleManager
        self.lifecycle_manager = AgentLifecycleManager(db=self.history.db, orchestrator=self)

        # Knowledge Synthesis ("Dreamer") — learns from tool interactions
        if flags.is_enabled("knowledge_synthesis"):
            from orchestrator.knowledge_synthesis import (
                InteractionCollector, KnowledgeSynthesizer, KnowledgeIndex,
            )
            knowledge_dir = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..')),
                "knowledge",
            )
            self.knowledge_index = KnowledgeIndex(knowledge_dir)
            self._interaction_collector = InteractionCollector(db=self.history.db)
            self._knowledge_synthesizer = KnowledgeSynthesizer(
                db=self.history.db,
                knowledge_dir=knowledge_dir,
                knowledge_index=self.knowledge_index,
            )
            self.hooks.register(HookEvent.POST_TOOL_USE, self._interaction_collector.on_tool_use)
            self.hooks.register(HookEvent.POST_TOOL_FAILURE, self._interaction_collector.on_tool_use)
            logger.info("Knowledge synthesis system initialized")

    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================

    async def register_agent(self, websocket, msg: RegisterAgent):
        """Register a specialist agent and store its capabilities."""
        card = msg.agent_card
        if not card:
            logger.warning("RegisterAgent with no card")
            return

        if websocket is not None:
            self.agents[card.agent_id] = websocket
        self.agent_cards[card.agent_id] = card

        # Extract capabilities for routing and tool→scope mapping
        caps = []
        tool_scope_map = {}
        for skill in card.skills:
            caps.append({
                "name": skill.id,
                "description": skill.description,
                "input_schema": skill.input_schema
            })
            # Store tool→scope mapping from agent-declared scopes
            tool_scope_map[skill.id] = getattr(skill, 'scope', '') or 'tools:read'
        self.agent_capabilities[card.agent_id] = caps

        # Register tool→scope mapping in the permission manager
        self.tool_permissions.register_tool_scopes(card.agent_id, tool_scope_map)

        # Prune tool_overrides rows for tools no longer in the agent's live
        # registry. Best-effort — a transient DB error must not block agent
        # registration. Idempotent: subsequent calls find nothing to delete.
        try:
            self.tool_permissions.cleanup_stale_tool_overrides(
                card.agent_id, list(tool_scope_map.keys())
            )
        except Exception as e:
            logger.warning(f"Stale tool_override cleanup failed for {card.agent_id}: {e}")

        # Extract streamable tool metadata for live streaming.
        # Two paths: legacy POLL streaming (orchestrator drives cadence) and
        # 001-tool-stream-ui PUSH streaming (tool is an async generator).
        for skill in card.skills:
            skill_metadata = getattr(skill, 'metadata', {}) or {}
            # Validate streaming metadata up front (001-tool-stream-ui T016).
            # Catches misconfigured tools at registration time with a clear
            # error rather than silently accepting and failing at subscribe.
            try:
                validate_streaming_metadata(skill_metadata)
            except ValueError as e:
                logger.warning(
                    f"Agent '{card.agent_id}' tool '{skill.id}' rejected: "
                    f"invalid streaming metadata: {e}"
                )
                continue

            # Legacy single-bool form: metadata.streamable is a config dict
            # (poll path). New form: metadata.streamable is True with
            # streaming_kind set to "push" or "poll".
            streamable_value = skill_metadata.get("streamable")
            if not streamable_value:
                continue
            if skill.scope not in ("tools:read", "tools:system"):
                continue

            # Determine kind: explicit metadata.streaming_kind wins; legacy
            # dict form (no kind) defaults to "poll".
            kind = skill_metadata.get("streaming_kind")
            if kind not in ("push", "poll"):
                kind = "poll"

            entry: Dict[str, Any] = {
                "agent_id": card.agent_id,
                "kind": kind,
            }
            # Poll path config
            if isinstance(streamable_value, dict):
                entry["default_interval"] = streamable_value.get("default_interval", 2)
                entry["min_interval"] = streamable_value.get("min_interval", 1)
                entry["max_interval"] = streamable_value.get("max_interval", 30)
            else:
                entry["default_interval"] = skill_metadata.get("default_interval_s", 2)
                entry["min_interval"] = 1
                entry["max_interval"] = 30
            # Push path bounds
            if kind == "push":
                entry["max_fps"] = skill_metadata.get("max_fps", 30)
                entry["min_fps"] = skill_metadata.get("min_fps", 5)
                entry["max_chunk_bytes"] = skill_metadata.get("max_chunk_bytes", 65536)
            self._streamable_tools[skill.id] = entry

        # Extract agent's ECIES public key for E2E credential encryption
        public_key_jwk = getattr(card, 'metadata', {}).get("public_key_jwk") if getattr(card, 'metadata', None) else None
        if public_key_jwk:
            self.credential_manager.register_agent_public_key(card.agent_id, public_key_jwk)
            logger.info(f"Registered ECIES public key for agent '{card.agent_id}'")

        logger.info(f"Agent registered: {card.agent_id} ({card.name}) with {len(caps)} tools")

        # Proactive security review: analyze all tools for threats
        raw_flags = self.security_analyzer.analyze_agent(card)
        if raw_flags:
            self.security_flags[card.agent_id] = {
                name: flag.to_dict() for name, flag in raw_flags.items()
            }
            logger.warning(
                f"Security review flagged {len(raw_flags)} tool(s) for agent "
                f"'{card.agent_id}': {list(raw_flags.keys())}"
            )
        else:
            self.security_flags[card.agent_id] = {}

        # Auto-assign ownership if this agent has no owner yet
        tool_names = [c["name"] for c in caps]
        ownership = self.history.db.get_agent_ownership(card.agent_id)
        if not ownership:
            default_owner = os.environ.get("DEFAULT_AGENT_OWNER", "")
            if default_owner:
                self.history.db.set_agent_ownership(card.agent_id, default_owner, is_public=False)
                ownership = self.history.db.get_agent_ownership(card.agent_id) or {}
                logger.info(f"Auto-assigned agent '{card.agent_id}' to {default_owner}")
            else:
                ownership = {}

        # Hook: AGENT_REGISTERED
        if flags.is_enabled("hook_system"):
            await self.hooks.emit(HookContext(
                event=HookEvent.AGENT_REGISTERED,
                agent_id=card.agent_id,
                metadata={"agent_name": card.name, "tool_count": len(caps)},
            ))

        # Don't broadcast draft agents to UI — they only appear in the Drafts tab
        if self._is_draft_agent(card.agent_id):
            return

        # Notify all UI clients (include per-user scopes, tool_scope_map, and security flags)
        for ui in self.ui_clients:
            try:
                user_id = self._get_user_id(ui)
                scopes = self.tool_permissions.get_agent_scopes(user_id, card.agent_id)
                permissions = self.tool_permissions.get_effective_permissions(
                    user_id, card.agent_id, tool_names
                )
                msg = {
                    "type": "agent_registered",
                    "agent_id": card.agent_id,
                    "name": card.name,
                    "description": card.description,
                    "tools": tool_names,
                    "permissions": permissions,
                    "scopes": scopes,
                    "tool_scope_map": tool_scope_map,
                    "security_flags": self.security_flags.get(card.agent_id, {}),
                    "owner_email": ownership.get("owner_email"),
                    "is_public": bool(ownership.get("is_public", False)),
                }
                if getattr(card, 'metadata', None):
                    msg["metadata"] = card.metadata
                await self._safe_send(ui, json.dumps(msg))
            except Exception:
                pass

    async def discover_agent(self, base_url: str):
        """Discover an agent by fetching its A2A agent card and connecting via WebSocket."""
        try:
            # Fetch agent card
            card_url = f"{base_url}/.well-known/agent-card.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(card_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        # Log as INFO during discovery to avoid noise during startup
                        logger.info(f"Agent card not ready yet at {card_url} (status: {resp.status})")
                        return
                    card_data = await resp.json()

            card = AgentCard.from_dict(card_data)
            agent_id = card.agent_id

            if agent_id in self.agents:
                logger.debug(f"Agent {agent_id} already connected")
                return

            # Connect via WebSocket with no size limit to allow large files
            ws_url = f"ws://{base_url.replace('http://', '').replace('https://', '')}/agent"
            ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)

            # Listen for RegisterAgent message
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = Message.from_json(raw)
            if isinstance(parsed, RegisterAgent):
                await self.register_agent(ws, parsed)

            # Store agent URL for peer registry
            self.agent_urls[agent_id] = base_url

            # Start listening loop
            asyncio.create_task(self._agent_listen_loop(ws, agent_id))

            logger.info(f"Connected to agent: {agent_id} at {base_url}")

        except Exception as e:
            logger.debug(f"Discovery attempt to {base_url} skipped: {e}")

    async def discover_a2a_agent(self, base_url: str, notify_ui: bool = True):
        """Discover an external agent — tries WebSocket first, falls back to A2A JSON-RPC.

        Strategy:
        1. Try to connect via WebSocket (fastest, bidirectional, preferred)
        2. If WebSocket fails, fall back to official A2A protocol (JSON-RPC)
        """
        # Step 1: Try WebSocket first
        try:
            await self.discover_agent(base_url)
            # Check if WebSocket discovery succeeded
            for aid, url in self.agent_urls.items():
                if url == base_url and aid in self.agents:
                    logger.info(f"External agent at {base_url} connected via WebSocket (preferred)")
                    # Also set up A2A client as backup
                    await self._setup_a2a_client_for_agent(base_url, aid)
                    return
        except Exception as e:
            logger.debug(f"WebSocket discovery to {base_url} failed: {e}")

        # Step 2: Fall back to A2A JSON-RPC
        try:
            import httpx
            from a2a.client import A2ACardResolver
            from shared.a2a_bridge import a2a_card_to_custom

            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(http_client, base_url)
                a2a_card = await resolver.get_agent_card()

            custom_card = a2a_card_to_custom(a2a_card)
            agent_id = custom_card.agent_id

            if agent_id in self.agents or agent_id in self.a2a_clients:
                logger.debug(f"A2A agent {agent_id} already connected")
                return

            # Track this agent as reachable via hand-rolled JSON-RPC (v1.0 client
            # is bypassed because we POST per-call with a per-request Bearer token).
            self.a2a_clients[agent_id] = base_url
            self.a2a_agent_cards[agent_id] = a2a_card
            self.agent_urls[agent_id] = base_url

            register_msg = RegisterAgent(agent_card=custom_card)
            await self.register_agent(None, register_msg)

            logger.info(f"External agent discovered via A2A (WebSocket unavailable): {agent_id} at {base_url}")

        except Exception as e:
            logger.debug(f"A2A discovery to {base_url} also failed: {e}")

    async def _setup_a2a_client_for_agent(self, base_url: str, agent_id: str):
        """Set up an A2A backup transport for a WebSocket-connected agent.

        Records the agent's base URL so tool calls can fall back to hand-rolled
        JSON-RPC if WebSocket transport fails.
        """
        try:
            import httpx
            from a2a.client import A2ACardResolver

            a2a_url = f"{base_url}/a2a"
            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(http_client, a2a_url)
                a2a_card = await resolver.get_agent_card()

            self.a2a_clients[agent_id] = base_url
            self.a2a_agent_cards[agent_id] = a2a_card
            logger.info(f"A2A backup client set up for {agent_id}")
        except Exception as e:
            logger.debug(f"A2A backup setup for {agent_id} failed (non-critical): {e}")

    async def _agent_listen_loop(self, ws, agent_id: str):
        """Listen for messages from a connected agent."""
        try:
            async for message in ws:
                await self.handle_agent_message(ws, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Agent {agent_id} disconnected")
        finally:
            if agent_id in self.agents:
                del self.agents[agent_id]
            if agent_id in self.agent_cards:
                del self.agent_cards[agent_id]
                logger.info(f"Agent {agent_id} deregistered")
            if agent_id in self.security_flags:
                del self.security_flags[agent_id]

    # =========================================================================
    # MESSAGE HANDLING
    # =========================================================================

    async def handle_agent_message(self, websocket, message: str):
        """Handle message from an agent."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterAgent):
                await self.register_agent(websocket, msg)

            elif isinstance(msg, MCPResponse):
                req_id = msg.request_id
                if req_id in self.pending_requests:
                    self.pending_requests[req_id].set_result(msg)
                else:
                    logger.warning(f"Received response for unknown request: {req_id}")

            elif isinstance(msg, ToolProgress) and flags.is_enabled("progress_streaming"):
                # Forward tool progress to the UI client that initiated the request
                # The agent includes a request_id in metadata so we can route it
                req_id = msg.metadata.get("request_id", "")
                ui_ws = self.pending_ui_sockets.get(req_id)
                if ui_ws:
                    await self._safe_send(ui_ws, json.dumps({
                        "type": "tool_progress",
                        "tool_name": msg.tool_name,
                        "agent_id": msg.agent_id,
                        "message": msg.message,
                        "percentage": msg.percentage,
                    }))

            # 001-tool-stream-ui: forward streaming tool chunks to subscribers
            # via StreamManager. Gated on the feature flag — when off, agents
            # never send these messages so the branches are never taken.
            elif isinstance(msg, ToolStreamData) and flags.is_enabled("tool_streaming"):
                if self.stream_manager is not None:
                    try:
                        await self.stream_manager.handle_agent_chunk(msg)
                    except NotImplementedError:
                        # Phase 2 foundational: handlers are stubs until US1
                        # implements the routing. Drop the chunk silently
                        # while we're still building the feature.
                        logger.debug(
                            f"ToolStreamData received but stream_manager handler "
                            f"not yet implemented (stream_id={msg.stream_id})"
                        )

            elif isinstance(msg, ToolStreamEnd) and flags.is_enabled("tool_streaming"):
                if self.stream_manager is not None:
                    try:
                        await self.stream_manager.handle_agent_end(msg)
                    except NotImplementedError:
                        logger.debug(
                            f"ToolStreamEnd received but stream_manager handler "
                            f"not yet implemented (stream_id={msg.stream_id})"
                        )

        except Exception as e:
            logger.error(f"Error handling agent message: {e}")

    async def _safe_handle_ui_message(self, websocket, message: str):
        """Wrapper that catches exceptions from fire-and-forget UI message tasks.
        Non-register messages wait for registration to complete first."""
        try:
            # Quick parse to check if this is a register_ui message
            is_register = '"register_ui"' in message
            if not is_register:
                evt = self._registered_events.get(id(websocket))
                if evt and not evt.is_set():
                    await evt.wait()
            await self.handle_ui_message(websocket, message)
        except Exception as e:
            logger.error(f"UI message task error: {e}", exc_info=True)

    async def handle_ui_message(self, websocket, message: str):
        """Handle message from a UI client."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterUI):
                token = msg.token
                user_data = None
                
                # Check for token validation (skip if not configured or in debug/dev mode if desired, but we want security)
                if token:
                    user_data = await self.validate_token(token)
                
                if user_data:
                    logger.info(f"UI registered: {user_data.get('preferred_username', 'unknown')}")
                    user_data["_raw_token"] = token  # Store raw token for RFC 8693 delegation
                    self.ui_sessions[websocket] = user_data

                    # Persist user profile to database
                    self._save_user_profile(user_data)

                    # Audit: WebSocket login lifecycle event (auth.ws_register)
                    try:
                        from audit.hooks import record_auth_event
                        await record_auth_event(
                            claims=user_data,
                            action="ws_register",
                            description=f"WebSocket session established for {user_data.get('preferred_username', user_data.get('sub', 'unknown'))}",
                        )
                    except Exception as _e:
                        logger.debug(f"WS register audit record failed: {_e}")

                    # Feature 006: pick up any LLM credentials the browser
                    # forwarded with this register_ui (the user's browser
                    # localStorage is the source of truth for personal config).
                    try:
                        from llm_config.ws_handlers import populate_from_register_ui
                        await populate_from_register_ui(
                            websocket=websocket,
                            llm_config=msg.llm_config,
                            actor_user_id=user_data.get("sub", "legacy"),
                            auth_principal=(
                                user_data.get("preferred_username")
                                or user_data.get("sub")
                                or "unknown"
                            ),
                            creds_store=self._session_llm_creds,
                            recorder=self.audit_recorder,
                        )
                    except Exception as _e:  # pragma: no cover — non-fatal
                        logger.debug(f"register_ui llm_config seeding failed (non-fatal): {_e}")

                    # ROTE: register device capabilities and send profile back
                    device_info = msg.device or {}
                    rote_profile = self.rote.register_device(websocket, device_info)
                    await self._safe_send(websocket, json.dumps({
                        "type": "rote_config",
                        "device_profile": rote_profile.to_dict(),
                        "speech_server_available": bool(os.getenv("SPEACHES_URL", "").strip()),
                    }))

                    # Send stored user preferences (theme, etc.)
                    user_id = user_data.get("sub", "legacy")
                    try:
                        prefs = self.history.db.get_user_preferences(user_id)
                        if prefs:
                            await self._safe_send(websocket, json.dumps({
                                "type": "user_preferences",
                                "preferences": prefs,
                            }))
                    except Exception as e:
                        logger.warning(f"Failed to load user preferences: {e}")

                    # Mark registration complete so queued messages can proceed
                    evt = self._registered_events.get(id(websocket))
                    if evt:
                        evt.set()

                    # Notify UI of success (optional, or just send dashboard)
                    await self.send_dashboard(websocket)
                else:
                    logger.warning("UI registration failed: Invalid or missing token")
                    # Ungate waiting tasks so they hit the auth check naturally
                    evt = self._registered_events.get(id(websocket))
                    if evt:
                        evt.set()
                    await self.send_ui_render(websocket, [
                        Alert(message="Authentication failed. Please log in again.", variant="error").to_json()
                    ])
                    # We might want to close, but let's let the UI handle the error alert
                    return

            elif msg.type in ("llm_config_set", "llm_config_clear"):
                # Feature 006-user-llm-config: per-user LLM credential
                # set/clear over WS. Both require an authenticated socket.
                if websocket not in self.ui_sessions:
                    await self._safe_send(websocket, json.dumps({
                        "type": "error",
                        "code": "unauthenticated",
                        "message": "register_ui must complete before llm_config_*",
                    }))
                    return
                claims = self.ui_sessions.get(websocket) or {}
                actor_user_id = claims.get("sub") or "legacy"
                auth_principal = (
                    claims.get("preferred_username")
                    or claims.get("sub")
                    or "unknown"
                )
                from llm_config.ws_handlers import (
                    handle_llm_config_set,
                    handle_llm_config_clear,
                )
                if msg.type == "llm_config_set":
                    await handle_llm_config_set(
                        safe_send=self._safe_send,
                        websocket=websocket,
                        config=getattr(msg, "config", {}) or {},
                        actor_user_id=actor_user_id,
                        auth_principal=auth_principal,
                        creds_store=self._session_llm_creds,
                        recorder=self.audit_recorder,
                    )
                else:
                    await handle_llm_config_clear(
                        safe_send=self._safe_send,
                        websocket=websocket,
                        actor_user_id=actor_user_id,
                        auth_principal=auth_principal,
                        creds_store=self._session_llm_creds,
                        recorder=self.audit_recorder,
                    )

            elif isinstance(msg, UIEvent):
                # Ensure authenticated
                if websocket not in self.ui_sessions:
                    await self.send_ui_render(websocket, [
                        Alert(message="Unauthorized. Please refresh.", variant="error").to_json()
                    ])
                    return

                user_id = self._get_user_id(websocket)

                # Audit: record the WS UI action in the user's audit log
                try:
                    from audit.hooks import record_ws_action
                    _action_chat_id = msg.session_id or (msg.payload or {}).get("chat_id")
                    asyncio.create_task(record_ws_action(
                        claims=self.ui_sessions.get(websocket),
                        action=str(msg.action or ""),
                        chat_id=_action_chat_id,
                        payload=msg.payload or {},
                    ))
                except Exception as _e:
                    logger.debug(f"WS action audit record failed: {_e}")

                if msg.action == "chat_message":
                    user_message = msg.payload.get("message", "")
                    chat_id = msg.session_id or msg.payload.get("chat_id")
                    draft_agent_id = msg.payload.get("draft_agent_id")
                    # Feature 013 / FR-018, FR-024: in-chat tool picker
                    # selection narrows the orchestrator's tool list. None
                    # / absent ≡ no narrowing (existing default behavior).
                    # An empty list reaching this point is a defensive
                    # case (UI gate FR-021 should have blocked send) —
                    # logged at WARN below in handle_chat_message.
                    selected_tools_raw = msg.payload.get("selected_tools")
                    if selected_tools_raw is None or selected_tools_raw == "":
                        selected_tools = None
                    elif isinstance(selected_tools_raw, list):
                        selected_tools = [str(t) for t in selected_tools_raw]
                    else:
                        selected_tools = None

                    # If no chat_id provided, create one
                    if not chat_id:
                        chat_id = self.history.create_chat(user_id=user_id)
                        from_message = True
                        # Inform UI about new chat ID
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_created",
                            "payload": {"chat_id": chat_id, "from_message": True}
                        }))
                    else:
                        if not self.history.get_chat(chat_id, user_id=user_id):
                            self.history.create_chat(chat_id, user_id=user_id)
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_created",
                                "payload": {"chat_id": chat_id, "from_message": True}
                            }))

                    display_message = msg.payload.get("display_message")
                    self.cancelled_sessions[id(websocket)] = False
                    # Use serialized wrapper so concurrent chat messages
                    # for the same session are processed one at a time.
                    await self._serialized_chat(
                        websocket, user_message, chat_id, display_message,
                        user_id=user_id, draft_agent_id=draft_agent_id,
                        selected_tools=selected_tools,
                    )

                elif msg.action == "cancel_task":
                    self.cancelled_sessions[id(websocket)] = True
                    # Feature 014 (FR-020/021): mark every in-flight step as
                    # cancelled so the persistent step trail reflects user
                    # intent immediately. Best-effort — late-arriving tool
                    # results are dropped via recorder.is_terminal() checks.
                    recorder = self._chat_recorders.get(id(websocket))
                    if recorder is not None:
                        try:
                            await recorder.cancel_all_in_flight()
                        except Exception:  # pragma: no cover — defensive
                            logger.debug("cancel_all_in_flight failed", exc_info=True)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": "Cancelled"
                    }))

                elif msg.action == "component_feedback":
                    # Feature 004 — submit feedback for a rendered component.
                    from feedback.ws_handlers import handle_component_feedback
                    claims = self.ui_sessions.get(websocket) or {}
                    auth_principal = claims.get("preferred_username") or claims.get("sub") or "unknown"
                    chat_id = msg.session_id or msg.payload.get("chat_id")
                    await handle_component_feedback(
                        safe_send=self._safe_send,
                        websocket=websocket,
                        payload=msg.payload or {},
                        actor_user_id=user_id,
                        auth_principal=auth_principal,
                        recorder=self.feedback_recorder,
                        conversation_id=chat_id,
                    )

                elif msg.action == "feedback_retract":
                    from feedback.ws_handlers import handle_feedback_retract
                    claims = self.ui_sessions.get(websocket) or {}
                    auth_principal = claims.get("preferred_username") or claims.get("sub") or "unknown"
                    await handle_feedback_retract(
                        safe_send=self._safe_send,
                        websocket=websocket,
                        payload=msg.payload or {},
                        actor_user_id=user_id,
                        auth_principal=auth_principal,
                        recorder=self.feedback_recorder,
                    )

                elif msg.action == "feedback_amend":
                    from feedback.ws_handlers import handle_feedback_amend
                    claims = self.ui_sessions.get(websocket) or {}
                    auth_principal = claims.get("preferred_username") or claims.get("sub") or "unknown"
                    await handle_feedback_amend(
                        safe_send=self._safe_send,
                        websocket=websocket,
                        payload=msg.payload or {},
                        actor_user_id=user_id,
                        auth_principal=auth_principal,
                        recorder=self.feedback_recorder,
                    )

                elif msg.action == "get_dashboard":
                    await self.send_dashboard(websocket)

                elif msg.action == "discover_agents":
                    await self.send_agent_list(websocket)

                elif msg.action == "register_external_agent":
                    # Register an external A2A agent by URL (entered by user in frontend)
                    agent_url = msg.payload.get("url", "").strip().rstrip("/")
                    if not agent_url:
                        await self.send_ui_render(websocket, [
                            Alert(message="Please provide an agent URL", variant="error").to_json()
                        ])
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status",
                            "status": "thinking",
                            "message": f"Discovering agent at {agent_url}..."
                        }))
                        await self.discover_a2a_agent(agent_url)
                        if any(aid for aid, card in self.agent_cards.items()
                               if card.metadata.get("a2a_url") == agent_url):
                            await self.send_agent_list(websocket)
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "done",
                                "message": f"External agent registered from {agent_url}"
                            }))
                        else:
                            await self.send_ui_render(websocket, [
                                Alert(message=f"Could not discover A2A agent at {agent_url}", variant="error").to_json()
                            ])
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "done",
                                "message": "Discovery failed"
                            }))

                elif msg.action == "get_history":
                    chats = self.history.get_recent_chats(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "history_list",
                        "chats": chats
                    }))

                elif msg.action == "load_chat":
                    chat_id = msg.payload.get("chat_id")
                    chat = self.history.get_chat(chat_id, user_id=user_id)
                    if chat:
                        # 001-tool-stream-ui (US2 T042): pause any push
                        # streams this websocket has in its previous chat
                        # before sending chat_loaded. The streams transition
                        # to DORMANT and become eligible for US3 resume on
                        # return.
                        ws_id = id(websocket)
                        old_chat_id = self._ws_active_chat.get(ws_id)
                        if old_chat_id and old_chat_id != chat_id and self.stream_manager is not None:
                            try:
                                await self.stream_manager.pause_chat(websocket, old_chat_id)
                            except Exception as e:
                                logger.warning(f"pause_chat failed: {e}")
                        self._ws_active_chat[ws_id] = chat_id

                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_loaded",
                            "chat": chat
                        }))

                        # 001-tool-stream-ui (US3 T054): after chat_loaded
                        # is sent, resume any DORMANT streams for this chat.
                        # Each resumed stream gets a stream_subscribed reply
                        # so the frontend re-registers it in pushStreamsRef
                        # and starts merging chunks again.
                        if self.stream_manager is not None:
                            try:
                                resumed = await self.stream_manager.resume(
                                    websocket, user_id, chat_id,
                                )
                                for resumed_stream_id, resumed_tool_name in resumed:
                                    cfg = self._streamable_tools.get(resumed_tool_name, {})
                                    await self._safe_send(websocket, json.dumps({
                                        "type": "stream_subscribed",
                                        "stream_id": resumed_stream_id,
                                        "tool_name": resumed_tool_name,
                                        "agent_id": cfg.get("agent_id", ""),
                                        "session_id": chat_id,
                                        "max_fps": cfg.get("max_fps", 30),
                                        "min_fps": cfg.get("min_fps", 5),
                                        "attached": False,
                                    }))
                            except Exception as e:
                                logger.warning(f"stream_manager.resume failed: {e}")
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Chat not found", variant="error").to_json()
                        ])

                elif msg.action == "new_chat":
                    chat_id = self.history.create_chat(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_created",
                        "payload": {"chat_id": chat_id, "from_message": False}
                    }))

                # Saved components actions
                elif msg.action == "save_component":
                    chat_id = msg.payload.get("chat_id")
                    component_data = msg.payload.get("component_data")
                    component_type = msg.payload.get("component_type")
                    title = msg.payload.get("title")
                    
                    if not chat_id or not component_data:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing required fields for saving component", variant="error").to_json()
                        ])
                        return
                    
                    try:
                        component_id = self.history.save_component(
                            chat_id, component_data, component_type, title, user_id=user_id
                        )
                        
                        # Send success response
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_saved",
                            "component": {
                                "id": component_id,
                                "chat_id": chat_id,
                                "component_data": component_data,
                                "component_type": component_type,
                                "title": title or component_type.replace('_', ' ').title(),
                                "created_at": int(time.time() * 1000)
                            }
                        }))
                        
                        # Broadcast updated chat history (each user gets their own)
                        await self._broadcast_user_history()

                    except Exception as e:
                        logger.error(f"Failed to save component: {e}")
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_save_error",
                            "error": str(e)
                        }))

                elif msg.action == "get_saved_components":
                    chat_id = msg.payload.get("chat_id")
                    components = self.history.get_saved_components(chat_id, user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "saved_components_list",
                        "components": components
                    }))

                elif msg.action == "delete_saved_component":
                    component_id = msg.payload.get("component_id")
                    if not component_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing component ID", variant="error").to_json()
                        ])
                        return
                    
                    success = self.history.delete_component(component_id, user_id=user_id)
                    if success:
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_deleted",
                            "component_id": component_id
                        }))
                        
                        # Broadcast updated chat history (each user gets their own)
                        await self._broadcast_user_history()
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_save_error",
                            "error": "Component not found"
                        }))

                elif msg.action == "combine_components":
                    source_id = msg.payload.get("source_id")
                    target_id = msg.payload.get("target_id")
                    
                    if not source_id or not target_id:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "Both source and target component IDs are required"
                        }))
                        return
                    
                    source = self.history.get_component_by_id(source_id, user_id=user_id)
                    target = self.history.get_component_by_id(target_id, user_id=user_id)
                    
                    if not source or not target:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "One or both components not found"
                        }))
                        return
                    
                    # Send progress
                    await self._safe_send(websocket, json.dumps({
                        "type": "combine_status",
                        "status": "combining",
                        "message": f"Combining {source['title']} with {target['title']}..."
                    }))
                    
                    try:
                        result = await self._combine_components_llm(
                            [source, target],
                            mode="combine"
                        )
                        
                        if result.get("error"):
                            await websocket.send(json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = source["chat_id"]
                            # Collect source metadata from original components
                            source_tools = set()
                            source_agents = set()
                            for comp in [source, target]:
                                cd = comp.get("component_data", {})
                                if cd.get("_source_tool"):
                                    source_tools.add(cd["_source_tool"])
                                if cd.get("_source_agent"):
                                    source_agents.add(cd["_source_agent"])

                            new_components = self.history.replace_components(
                                [source_id, target_id],
                                result["components"],
                                chat_id,
                                user_id=user_id
                            )

                            # Tag combined components with source metadata so live streaming continues
                            if source_tools:
                                for nc in new_components:
                                    cd = nc.get("component_data")
                                    if isinstance(cd, dict):
                                        cd["_source_tool"] = next(iter(source_tools))
                                        if source_agents:
                                            cd["_source_agent"] = next(iter(source_agents))

                            await self._safe_send(websocket, json.dumps({
                                "type": "components_combined",
                                "removed_ids": [source_id, target_id],
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Combine failed: {e}", exc_info=True)
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to combine components: {str(e)}"
                        }))

                elif msg.action == "get_agent_permissions":
                    agent_id = msg.payload.get("agent_id")
                    if not agent_id:
                        return
                    # Build available tools list for this agent
                    card = self.agent_cards.get(agent_id)
                    if not card:
                        return
                    available_tools = [s.id for s in card.skills]
                    tool_descriptions = {s.id: s.description for s in card.skills}
                    scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
                    tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
                    permissions = self.tool_permissions.get_effective_permissions(
                        user_id, agent_id, available_tools
                    )
                    tool_overrides = self.tool_permissions.get_tool_overrides(user_id, agent_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "agent_permissions",
                        "agent_id": agent_id,
                        "agent_name": card.name,
                        "scopes": scopes,
                        "tool_scope_map": tool_scope_map,
                        "permissions": permissions,
                        "tool_overrides": tool_overrides,
                        "tool_descriptions": tool_descriptions,
                        "security_flags": self.security_flags.get(agent_id, {})
                    }))

                elif msg.action == "set_agent_permissions":
                    agent_id = msg.payload.get("agent_id")
                    scopes = msg.payload.get("scopes", {})
                    tool_overrides_payload = msg.payload.get("tool_overrides")
                    if not agent_id or not isinstance(scopes, dict):
                        return
                    self.tool_permissions.set_agent_scopes(
                        user_id, agent_id, scopes
                    )
                    if isinstance(tool_overrides_payload, dict):
                        self.tool_permissions.set_tool_overrides(
                            user_id, agent_id, tool_overrides_payload
                        )
                    logger.info(f"Scopes updated: user={user_id} agent={agent_id} scopes={scopes}")
                    # Compute effective per-tool permissions from new scopes + overrides
                    card = self.agent_cards.get(agent_id)
                    available_tools = [s.id for s in card.skills] if card else []
                    permissions = self.tool_permissions.get_effective_permissions(
                        user_id, agent_id, available_tools
                    )
                    tool_overrides = self.tool_permissions.get_tool_overrides(user_id, agent_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "agent_permissions_updated",
                        "agent_id": agent_id,
                        "scopes": scopes,
                        "permissions": permissions,
                        "tool_overrides": tool_overrides
                    }))

                    # Also broadcast an updated dashboard to all UI clients for this user
                    # so their total tools count updates immediately. Feature 008:
                    # also re-broadcast agent_list so the per-user
                    # `tools_available_for_user` flag stays in sync with the new
                    # permissions — this drives the persistent text-only banner
                    # (FR-005, FR-007a).
                    for client in self.ui_clients:
                        client_user_id = self._get_user_id(client)
                        if client_user_id == user_id:
                            asyncio.create_task(self.send_dashboard(client))
                            asyncio.create_task(self.send_agent_list(client))


                elif msg.action == "update_device":
                    # ROTE: viewport / capability change from the frontend
                    device_info = msg.payload.get("device") or {}
                    new_profile, re_adapted = self.rote.update_device(websocket, device_info)
                    await self._safe_send(websocket, json.dumps({
                        "type": "rote_config",
                        "device_profile": new_profile.to_dict(),
                        "speech_server_available": bool(os.getenv("SPEACHES_URL", "").strip()),
                    }))
                    # If the profile changed and we have cached components, re-send them.
                    # Use UIUpdate (not UIRender) so the frontend replaces the last
                    # components in-place instead of appending a duplicate message.
                    if re_adapted is not None:
                        msg_out = UIUpdate(components=re_adapted)
                        await self._safe_send(websocket, msg_out.to_json())

                elif msg.action == "save_theme":
                    # Persist theme colors to user preferences
                    theme_data = msg.payload.get("theme")
                    if theme_data:
                        try:
                            self.history.db.set_user_preferences(user_id, {"theme": theme_data})
                        except Exception as e:
                            logger.warning(f"Failed to save theme for {user_id}: {e}")

                elif msg.action == "condense_components":
                    component_ids = msg.payload.get("component_ids", [])
                    logger.info(f"Condense requested: {len(component_ids)} component IDs for user={user_id}")

                    try:
                        if len(component_ids) < 2:
                            await self._safe_send(websocket, json.dumps({
                                "type": "combine_error",
                                "error": "At least 2 components are required to condense"
                            }))
                            return

                        components = []
                        for cid in component_ids:
                            comp = self.history.get_component_by_id(cid, user_id=user_id)
                            if comp:
                                components.append(comp)

                        if len(components) < 2:
                            logger.warning(f"Condense: only {len(components)} of {len(component_ids)} components found in DB")
                            await self._safe_send(websocket, json.dumps({
                                "type": "combine_error",
                                "error": "Not enough valid components found"
                            }))
                            return

                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_status",
                            "status": "condensing",
                            "message": f"Condensing {len(components)} components..."
                        }))

                        result = await self._combine_components_llm(
                            components,
                            mode="condense"
                        )

                        if result.get("error"):
                            await self._safe_send(websocket, json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = components[0]["chat_id"]
                            # Collect source metadata from original components to carry forward
                            source_tools = set()
                            source_agents = set()
                            for comp in components:
                                cd = comp.get("component_data", {})
                                if cd.get("_source_tool"):
                                    source_tools.add(cd["_source_tool"])
                                if cd.get("_source_agent"):
                                    source_agents.add(cd["_source_agent"])

                            new_components = self.history.replace_components(
                                component_ids,
                                result["components"],
                                chat_id,
                                user_id=user_id
                            )

                            # Tag condensed components with source metadata so live streaming continues
                            if source_tools:
                                for nc in new_components:
                                    cd = nc.get("component_data")
                                    if isinstance(cd, dict):
                                        cd["_source_tool"] = next(iter(source_tools))
                                        if source_agents:
                                            cd["_source_agent"] = next(iter(source_agents))

                            await self._safe_send(websocket, json.dumps({
                                "type": "components_condensed",
                                "removed_ids": component_ids,
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Condense failed: {e}", exc_info=True)
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to condense components: {str(e)}"
                        }))

                elif msg.action == "table_paginate":
                    # Re-invoke a tool with updated pagination params
                    tool_name = msg.payload.get("tool_name")
                    agent_id = msg.payload.get("agent_id")
                    params = msg.payload.get("params", {})

                    if not tool_name or not agent_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing tool_name or agent_id for pagination", variant="error").to_json()
                        ])
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status", "status": "done", "message": ""
                        }))
                        return

                    # Inject per-user credentials (E2E encrypted — only agent can decrypt)
                    args = dict(params)
                    if user_id and agent_id:
                        creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
                        if creds:
                            args["_credentials"] = creds
                            args["_credentials_encrypted"] = True

                    try:
                        result = await self._execute_with_retry(websocket, agent_id, tool_name, args)
                        if result and result.ui_components:
                            await self.send_ui_render(websocket, result.ui_components)
                        elif result and result.error:
                            await self.send_ui_render(websocket, [
                                Alert(message=result.error.get("message", "Pagination failed"), variant="error").to_json()
                            ])
                    except Exception as e:
                        logger.error(f"table_paginate failed: {e}", exc_info=True)
                        await self.send_ui_render(websocket, [
                            Alert(message=f"Pagination failed: {e}", variant="error").to_json()
                        ])
                    finally:
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status", "status": "done", "message": ""
                        }))

                # --- Live Streaming ---
                elif msg.action == "stream_subscribe":
                    # 001-tool-stream-ui: route based on the tool's declared
                    # kind. PUSH tools go through StreamManager (the new
                    # async-generator path); POLL tools stay on the existing
                    # _handle_stream_subscribe path. The kind comes from the
                    # tool's metadata, populated at register_agent time.
                    tool_name = msg.payload.get("tool_name", "")
                    tool_cfg = self._streamable_tools.get(tool_name, {})
                    kind = tool_cfg.get("kind", "poll")

                    if kind == "push":
                        if not flags.is_enabled("tool_streaming"):
                            await self._safe_send(websocket, json.dumps({
                                "type": "stream_error",
                                "request_action": "stream_subscribe",
                                "session_id": msg.session_id,
                                "payload": {
                                    "tool_name": tool_name,
                                    "code": "not_streamable",
                                    "message": "Push streaming is not enabled (FF_TOOL_STREAMING)",
                                },
                            }))
                        else:
                            await self._handle_push_stream_subscribe(
                                websocket, msg.session_id, msg.payload, user_id
                            )
                    elif flags.is_enabled("live_streaming"):
                        await self._handle_stream_subscribe(websocket, msg.payload)
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "stream_error", "tool_name": tool_name,
                            "error": "Live streaming is not enabled"
                        }))

                elif msg.action == "stream_unsubscribe":
                    # 001-tool-stream-ui: dual routing as above. The push
                    # path takes a stream_id; the poll path takes a tool_name.
                    payload = msg.payload or {}
                    if payload.get("stream_id") and flags.is_enabled("tool_streaming"):
                        await self._handle_push_stream_unsubscribe(
                            websocket, msg.session_id, payload, user_id
                        )
                    elif flags.is_enabled("live_streaming"):
                        await self._handle_stream_unsubscribe(websocket, payload)

                elif msg.action == "stream_list":
                    if flags.is_enabled("live_streaming"):
                        await self._handle_stream_list(websocket)

        except Exception as e:
            import traceback
            logger.error(f"Error handling UI message: {e}\n{traceback.format_exc()}")

    # =========================================================================
    # COMPONENT COMBINING (LLM-powered)
    # =========================================================================

    async def _combine_components_llm(self, components: list, mode: str = "combine") -> dict:
        """Use LLM to combine/condense UI components.
        
        Args:
            components: List of component dicts with component_data, title, etc.
            mode: 'combine' for merging 2 components, 'condense' for reducing many.
        
        Returns:
            {"components": [...]} on success, {"error": "..."} on failure.
        """
        # Feature 006: this is a system-initiated combine (websocket=None
        # is passed to _call_llm below), so it relies on the operator's
        # .env defaults — per-user credentials don't apply here (FR-011).
        # The downstream _call_llm will emit llm_unconfigured if the
        # operator default is also absent; this fast-path return just
        # avoids building a long prompt that would never be sent.
        if not self._operator_creds.is_complete:
            return {"error": "LLM not configured"}

        # Build the component descriptions for the prompt
        component_descriptions = []
        for i, comp in enumerate(components):
            component_descriptions.append(
                f"Component {i+1} (title: \"{comp['title']}\", type: \"{comp['component_type']}\"):\n"
                f"```json\n{json.dumps(comp['component_data'], indent=2)}\n```"
            )
        
        components_text = "\n\n".join(component_descriptions)

        schema_description = """Available UI primitive types and their JSON structure:
- "text": {type: "text", content: "...", variant: "body|h1|h2|h3|caption|markdown"}
- "card": {type: "card", title: "...", content: [...child components...]}
- "metric": {type: "metric", title: "...", value: "...", subtitle: "...", progress: 0.0-1.0, variant: "default|warning|error|success"}
- "table": {type: "table", title: "...", headers: [...], rows: [[...],...]}
- "grid": {type: "grid", columns: 2, gap: 16, children: [...child components...]}
- "container": {type: "container", children: [...child components...]}
- "list": {type: "list", items: [...], ordered: false, variant: "default|detailed"}
- "alert": {type: "alert", message: "...", title: "...", variant: "info|success|warning|error"}
- "progress": {type: "progress", value: 0.0-1.0, label: "...", show_percentage: true}
- "bar_chart": {type: "bar_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "line_chart": {type: "line_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "pie_chart": {type: "pie_chart", title: "...", labels: [...], data: [...], colors: [...]}
- "code": {type: "code", code: "...", language: "..."}
- "divider": {type: "divider"}
- "collapsible": {type: "collapsible", title: "...", content: [...child components...], default_open: false}"""

        if mode == "combine":
            prompt = f"""You are a UI component combiner. You are given 2 UI components and must merge them into a single cohesive component.

{schema_description}

RULES:
1. Analyze whether these components can be meaningfully combined.
2. If they contain RELATED data (e.g., patient data + disease chart, or multiple system metrics), combine them into a unified component using cards, grids, or tables.
3. If they are UNRELATED or incompatible, respond ONLY with: ERROR: <brief reason>
4. Preserve ALL data — do not lose any information from either component.
5. Use grid layouts to arrange related metrics side-by-side.
6. Use cards with descriptive titles to group related content.

COMPONENTS TO COMBINE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...the merged component tree...}},
      "component_type": "card",
      "title": "Descriptive Title For Merged Component"
    }}
  ]
}}

Or if they cannot be combined:
ERROR: <reason>"""
        else:  # condense
            prompt = f"""You are a UI component condenser. You are given {len(components)} UI components and must combine as many as possible into fewer cohesive components.

{schema_description}

RULES:
1. Group RELATED components together (e.g., all system metrics into one dashboard card, all patient data into one view).
2. Keep UNRELATED components separate — don't force unrelated data together.
3. Preserve ALL data — do not lose any information.
4. Use grid layouts to arrange related metrics side-by-side.
5. Use cards with descriptive titles to group related content.
6. The goal is to REDUCE the total number of components while maintaining clarity.

COMPONENTS TO CONDENSE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...component tree...}},
      "component_type": "card",
      "title": "Descriptive Title"
    }}
  ]
}}"""

        try:
            # Use _call_llm for built-in retries (important for transient 502s)
            llm_msg, _usage = await self._call_llm(
                None,  # no websocket needed for combine
                [
                    {"role": "system", "content": "You are a precise UI component combiner. Output ONLY valid JSON or an ERROR message. No explanations, no markdown fences."},
                    {"role": "user", "content": prompt}
                ],
                tools_desc=None,
                temperature=0.1
            )

            if not llm_msg:
                return {"error": "LLM returned no response"}
            
            content = (llm_msg.content or "").strip()
            logger.info(f"LLM combine response ({len(content)} chars): {content[:200]}...")
            
            # Check for ERROR response
            if content.upper().startswith("ERROR"):
                error_msg = content.split(":", 1)[1].strip() if ":" in content else content
                return {"error": error_msg}
            
            # Try to parse JSON
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"error": f"Failed to parse LLM response as JSON"}
            
            if "components" not in result or not isinstance(result["components"], list):
                return {"error": "LLM response missing 'components' array"}
            
            # Known valid primitive types from primitives.py
            VALID_TYPES = {
                "container", "text", "button", "card", "table", "list",
                "alert", "progress", "metric", "code", "image", "grid",
                "tabs", "divider", "input", "bar_chart", "line_chart",
                "pie_chart", "plotly_chart", "collapsible", "chart"
            }
            
            # Validate each component
            for comp in result["components"]:
                if "component_data" not in comp:
                    return {"error": "LLM response component missing 'component_data'"}
                
                # Validate the component type
                comp_data = comp["component_data"]
                comp_type = comp_data.get("type", "")
                if comp_type and comp_type not in VALID_TYPES:
                    logger.warning(f"LLM produced unknown component type '{comp_type}', wrapping in card")
                    # Wrap unknown types in a card to ensure they render
                    comp["component_data"] = {
                        "type": "card",
                        "title": comp_data.get("title", "Combined Component"),
                        "content": [comp_data] if comp_type else []
                    }
                    comp_type = "card"
                
                # Recursively validate children
                self._validate_component_tree(comp_data, VALID_TYPES)
                
                if "component_type" not in comp:
                    comp["component_type"] = comp_type or "card"
                if "title" not in comp:
                    comp["title"] = comp["component_data"].get("title", "Combined Component")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM combine error: {e}", exc_info=True)
            return {"error": f"LLM error: {str(e)}"}

    def _validate_component_tree(self, node: dict, valid_types: set):
        """Recursively validate component tree, fixing invalid types."""
        if not isinstance(node, dict):
            return
        
        raw_type = node.get("type", "")
        node_type = raw_type.strip().lower()
        # Map generic 'chart' to 'plotly_chart' regardless of validity
        if node_type == "chart":
            logger.info(f"Mapping generic component type 'chart' -> 'plotly_chart'")
            node["type"] = "plotly_chart"
            node_type = "plotly_chart"  # update variable for subsequent checks
        
        if node_type and node_type not in valid_types:
            logger.warning(f"Fixing unknown component type '{node_type}' -> 'container'")
            node["type"] = "container"
        
        # Validate children arrays
        for key in ("children", "content"):
            children = node.get(key, [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        self._validate_component_tree(child, valid_types)
        
        # Validate tab items
        tabs = node.get("tabs", [])
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    for child in tab.get("content", []):
                        if isinstance(child, dict):
                            self._validate_component_tree(child, valid_types)

    # Component types that carry no rich visual content (just text wrappers)
    _TEXT_ONLY_TYPES = {"text", "card", "container", "collapsible", "divider", "list", "alert"}

    def _is_text_only_components(self, components: list) -> bool:
        """Return True if all components in the tree contain only text-based content.

        Used to decide whether parsed UI JSON should go to the canvas (rich content)
        or the chat panel only (text-only content).
        """
        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_type = comp.get("type", "").strip().lower()
            if comp_type not in self._TEXT_ONLY_TYPES:
                return False
            for key in ("children", "content"):
                children = comp.get(key, [])
                if isinstance(children, list):
                    child_dicts = [c for c in children if isinstance(c, dict) and "type" in c]
                    if child_dicts and not self._is_text_only_components(child_dicts):
                        return False
        return True

    def _map_file_paths(self, chat_id: str, args: Dict, user_id: str = 'legacy') -> Dict:
        """Replace original filenames in tool arguments with backend paths.
        
        Uses file mappings stored in history for the given chat.
        """
        if not chat_id:
            return args
        
        mappings = self.history.get_file_mappings(chat_id, user_id=user_id)
        if not mappings:
            return args
        
        # Build mapping dict: original_name -> backend_path
        mapping_dict = {m["original_name"]: m["backend_path"] for m in mappings}
        
        # Recursively traverse args dict and replace strings that match original names
        def replace_in_dict(obj):
            if isinstance(obj, dict):
                return {k: replace_in_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_in_dict(item) for item in obj]
            elif isinstance(obj, str):
                # Check if the string matches any original name (exact match)
                for orig, backend in mapping_dict.items():
                    if obj == orig:
                        logger.info(f"Mapping file path: '{orig}' -> '{backend}'")
                        return backend
                return obj
            else:
                return obj
        
        new_args = replace_in_dict(args)
        if new_args != args:
            logger.info(f"Mapped file paths in tool arguments for chat {chat_id}")
        return new_args

    # =========================================================================
    # LLM-POWERED TOOL ROUTING
    # =========================================================================

    async def _start_heartbeat(self, websocket) -> asyncio.Task:
        """Start sending heartbeat messages every 5s to keep UI informed during long operations."""
        async def _heartbeat_loop():
            while True:
                await asyncio.sleep(5)
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "heartbeat",
                        "timestamp": time.time()
                    }))
                except Exception:
                    break
        return asyncio.create_task(_heartbeat_loop())

    async def _serialized_chat(self, websocket, message, chat_id, display_message, *, user_id=None, draft_agent_id=None, selected_tools=None):
        """Run handle_chat_message under a per-websocket lock so messages
        are serialized but the WS receive loop is never blocked."""
        ws_id = id(websocket)
        lock = self._chat_locks.setdefault(ws_id, asyncio.Lock())
        async with lock:
            try:
                await self.handle_chat_message(
                    websocket, message, chat_id, display_message,
                    user_id=user_id, draft_agent_id=draft_agent_id,
                    selected_tools=selected_tools,
                )
            except Exception as e:
                # Full details (including any upstream HTML payload, stack
                # trace, etc.) go to structured logs only. The user-facing
                # message is a generic, safe string — never str(e), which
                # may contain raw HTML, secrets, or PHI from upstream.
                logger.error(f"Chat task error: {e}", exc_info=True)
                # Feature 014: a mid-turn exception left some steps in-flight
                # with no chance to complete. Mark them cancelled so the UI
                # does not show a stuck spinner. (The success path does NOT
                # cancel — every step lifecycle call has already fired by
                # the time handle_chat_message returns; auto-cancelling on
                # the success path produced false-cancel labels on
                # successfully-completed steps.)
                recorder = self._chat_recorders.get(ws_id)
                if recorder is not None:
                    try:
                        await recorder.cancel_all_in_flight()
                    except Exception:  # pragma: no cover — defensive
                        logger.debug("ChatStepRecorder exception flush failed", exc_info=True)
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status", "status": "done",
                    "message": "Something went wrong while processing your request. Please try again."
                }))
                # Surface a clean Alert in the chat so the user sees a
                # tangible response in the message area, matching the
                # FR-008 / FR-009 (006) "LLM unavailable" pattern.
                try:
                    await self.send_ui_render(websocket, [
                        Alert(
                            message="Something went wrong while processing your request. Please try again.",
                            variant="error",
                        ).to_json()
                    ])
                except Exception:  # pragma: no cover — defensive
                    pass
            finally:
                # Feature 014: clear the per-turn step recorder reference.
                # We do NOT flush in-flight steps here — the success path
                # has already terminated them, and the exception path above
                # explicitly flushes. The cancel_task handler (line ~959)
                # also flushes for genuine user-initiated cancellations.
                # If a programmer error left a step in_progress, the
                # GET /api/chats/{id}/steps endpoint heals stale rows
                # (>30 s old, no active task) into 'interrupted' on the
                # next chat load.
                self._chat_recorders.pop(ws_id, None)

    async def handle_chat_message(self, websocket, message: str, chat_id: str, display_message: str = None, user_id: str = None, draft_agent_id: str = None, selected_tools=None):
        """Process a chat message: LLM determines which tools to call (Multi-Turn Re-Act Loop).

        Feature 013 / FR-018, FR-020, FR-023: ``selected_tools`` is the
        user's in-chat tool-picker subset. When not None, the per-turn
        filter loop excludes any tool not in the subset — narrowing only,
        never widening (scope/per-tool permissions are still enforced).
        """
        logger.info(f"Processing chat message: '{message}' for chat_id {chat_id}")
        if user_id is None:
            user_id = self._get_user_id(websocket)
        # Feature 013 defensive: a stray empty selection from the WS
        # payload is treated as "no narrowing" for this single request,
        # logged so operators can see if the UI gate (FR-021) ever leaks.
        if selected_tools is not None and len(selected_tools) == 0:
            logger.warning(
                "Chat dispatch received empty selected_tools (chat_id=%s user_id=%s) "
                "reason=empty_selection_received — treating as no narrowing.",
                chat_id,
                user_id,
            )
            selected_tools = None
        # If the user has not narrowed in the WS payload, fall back to
        # their saved per-user preference (FR-024).
        if selected_tools is None and user_id is not None and not draft_agent_id:
            try:
                # Resolve the chat's bound agent so the saved selection
                # for THAT agent is applied; if the chat is unbound, no
                # agent-specific selection applies and the orchestrator
                # uses its full default.
                bound_agent_id = self.history.db.get_chat_agent(chat_id) if chat_id else None
                if bound_agent_id is not None:
                    saved = self.history.db.get_user_tool_selection(user_id, bound_agent_id)
                    if saved is not None and len(saved) > 0:
                        selected_tools = saved
            except Exception as e:  # pragma: no cover — defensive
                logger.debug(f"Could not resolve saved tool selection: {e}")
        if not message:
            logger.warning("Empty message received")
            return

        # Feature 006: pre-flight check — surface the FR-004a "LLM
        # unavailable" prompt up-front when neither the user's personal
        # config nor the operator default is usable, instead of letting
        # the user wait through the loading state for an inevitable failure.
        # The per-call resolver in _call_llm will also catch this, but
        # exiting early avoids the extra UX latency.
        try:
            self._resolve_llm_client_for(websocket)
        except self._LLMUnavailable:
            actor_user_id, auth_principal = self._llm_audit_principals(websocket)
            await self._record_llm_unconfigured(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature="chat_dispatch",
            )
            await self.send_ui_render(websocket, [
                Alert(
                    message="LLM unavailable — set your own provider in settings.",
                    variant="error",
                ).to_json()
            ])
            return

        # Send loading state to UI
        await self._safe_send(websocket, json.dumps({
            "type": "chat_status",
            "status": "thinking",
            "message": "Analyzing request and planning actions..."
        }))
        
        # Save User Message to History. If display_message is provided, save that instead.
        msg_to_save = display_message if display_message else message
        self.history.add_message(chat_id, "user", msg_to_save, user_id=user_id)

        # Feature 014: create a per-turn ChatStepRecorder. The recorder's
        # WebSocket emits and persistence are PHI-redacted at the boundary
        # via shared.phi_redactor (FR-009b). Stored on the orchestrator so
        # the cancel_task handler can flush in-flight steps (FR-020/021)
        # and execute_tool_and_wait can record per-tool lifecycle events.
        turn_message_id = None
        try:
            from orchestrator.chat_steps import ChatStepRecorder

            turn_message_id = self.history.get_latest_message_id(chat_id, user_id)
            recorder = ChatStepRecorder(
                db=self.history.db,
                websocket=websocket,
                safe_send=self._safe_send,
                chat_id=chat_id,
                user_id=user_id or "legacy",
                turn_message_id=turn_message_id,
            )
            self._chat_recorders[id(websocket)] = recorder
        except Exception:  # pragma: no cover — defensive; never block a turn
            logger.warning("Failed to create ChatStepRecorder", exc_info=True)

        # Feature 014: send the persisted message_id back to the frontend so
        # it can stamp its locally-appended user message and group incoming
        # `chat_step` events under the correct turn (steps' turn_message_id
        # FK matches this id). Without this stamp, the frontend cannot
        # interleave step lines under the right turn in multi-turn chats.
        if turn_message_id is not None:
            await self._safe_send(websocket, json.dumps({
                "type": "user_message_acked",
                "chat_id": chat_id,
                "message_id": turn_message_id,
            }))

        # Capture File Upload Mapping
        upload_match = re.search(r"I have uploaded (.*?) to the backend at: `(.*?)`" , message)
        if upload_match:
            original_name = upload_match.group(1)
            backend_path = upload_match.group(2)
            logger.info(f"Captured file upload mapping: {original_name} -> {backend_path}")
            self.history.add_file_mapping(chat_id, original_name, backend_path, user_id=user_id)

        # Async title summarization for new chats
        chat_data = self.history.get_chat(chat_id, user_id=user_id)
        if chat_data and len(chat_data.get("messages", [])) == 1:
            asyncio.create_task(
                self.summarize_chat_title(chat_id, msg_to_save, user_id=user_id, websocket=websocket)
            )

        # Build tool definitions from registered agents
        # Filter by user's per-agent tool permissions (RFC 8693 delegation)
        # Draft test chats: only expose the draft agent's tools
        if draft_agent_id:
            logger.info(f"Draft test chat — filtering tools to agent: {draft_agent_id}")
        else:
            logger.info(f"Building tool definitions from {len(self.agent_cards)} agents...")
        tools_desc = []
        tool_to_agent = {}  # Map tool name → agent_id

        # Feature 013 follow-up: resolve this user's per-agent disabled
        # set once so we can skip disabled agents wholesale below. The
        # draft-test path bypasses this — testing your own draft must
        # always work even if you've disabled the live version.
        try:
            disabled_agents = (
                set(self.history.db.get_user_disabled_agents(user_id))
                if user_id and not draft_agent_id
                else set()
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.debug(f"Could not resolve user disabled-agent list: {e}")
            disabled_agents = set()

        for agent_id, card in self.agent_cards.items():
            if agent_id not in self.agents:
                continue

            # Draft test: only include tools from the draft agent being tested
            if draft_agent_id and agent_id != draft_agent_id:
                continue

            # Per-user agent disable (Feature 013 follow-up): user has
            # muted this agent; skip ALL its tools without touching
            # scope/permission state. Logged so operators can see when
            # it kicks in.
            if agent_id in disabled_agents:
                logger.debug(
                    f"Agent '{agent_id}' excluded user={user_id} reason=user_disabled_agent"
                )
                continue

            # Draft test (Feature 013 follow-up): when the user is testing
            # THEIR OWN draft agent, bypass scope/per-tool permission checks
            # so they can exercise the agent's tools without first granting
            # themselves scopes. Strictly isolated to the draft being tested
            # — `agent_id == draft_agent_id` is the only way this branch
            # fires, so other agents (live or otherwise) are unaffected.
            in_draft_test_for_this_agent = (
                draft_agent_id is not None and agent_id == draft_agent_id
            )

            for skill in card.skills:
                # System-level security block always wins, even in draft test
                # — security flags reflect proactive review and we never
                # want a draft to short-circuit a flagged tool.
                agent_flags = self.security_flags.get(agent_id, {})
                if skill.id in agent_flags and agent_flags[skill.id].get("blocked"):
                    logger.debug(
                        f"Tool '{skill.id}' excluded user={user_id} agent={agent_id} reason=system_blocked"
                    )
                    continue

                # Check if the user has allowed this tool for this agent
                # (Feature 013 / FR-013: per-(tool, kind) row > legacy
                # NULL-kind override > agent_scopes fallback). Skipped
                # for the draft being tested — see the comment above.
                if not in_draft_test_for_this_agent and not self.tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
                    logger.debug(
                        f"Tool '{skill.id}' excluded user={user_id} agent={agent_id} reason=scope_or_override"
                    )
                    continue

                # Feature 013 / FR-018, FR-020, FR-023: in-chat tool
                # picker narrowing. Only ever subtracts — applied AFTER
                # the scope/permission checks so it cannot widen.
                if selected_tools is not None and skill.id not in selected_tools:
                    logger.debug(
                        f"Tool '{skill.id}' excluded user={user_id} agent={agent_id} reason=user_selection"
                    )
                    continue

                schema = self._sanitize_tool_schema(skill.input_schema or {"type": "object", "properties": {}})
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": skill.id,
                        "description": skill.description,
                        "parameters": schema
                    }
                }
                tools_desc.append(tool_def)
                tool_to_agent[skill.id] = agent_id

        # Feature 008-llm-text-only-chat (FR-001/FR-002/FR-010).
        # When zero tools survive the filter stack, fall through to a
        # plain LLM chat (text-only mode) instead of the legacy
        # "No agents connected" warning. Three exclusions:
        #  - draft test chats (FR-010): preserve the existing
        #    draft-diagnostic path so misconfigured drafts surface.
        #  - LLM unavailable: already short-circuited at the top of
        #    handle_chat_message (FR-003).
        # The dispatch loop below already accepts an empty tools list
        # cleanly — _call_llm omits the `tools` kwarg when tools_desc
        # is falsy. We tag the audit/log signal so operators can
        # distinguish text-only fallback turns (FR-009).
        is_text_only = not tools_desc and not draft_agent_id
        if not tools_desc and draft_agent_id:
            await self.send_ui_render(websocket, [
                Alert(
                    message=(
                        "Draft agent has no usable tools yet. Configure tools "
                        "and permissions before testing it."
                    ),
                    variant="warning",
                ).to_json()
            ])
            return
        if is_text_only:
            logger.info(
                "Chat dispatch entering text-only mode "
                f"(chat_id={chat_id} user_id={user_id} tools_attempted=0)"
            )

        try:
            # ------------------------------------------------------------------
            # SYSTEM PROMPT
            # ------------------------------------------------------------------
            # Fetch file mappings for this chat
            file_mappings = self.history.get_file_mappings(chat_id, user_id=user_id)
            file_context = ""
            if file_mappings:
                file_context = "\nFILES ACCESSED IN THIS CHAT (Original Name -> Backend Path):\n"
                for mapping in file_mappings:
                    file_context += f"- {mapping['original_name']} -> {mapping['backend_path']}\n"
                file_context += "\nIMPORTANT: You MUST use the absolute backend path (right side) when calling tools for these files. Never use just the original filename.\n"

            # Fetch saved canvas components for context-aware updates
            canvas_saved = self.history.get_saved_components(chat_id, user_id=user_id)
            canvas_context = ""
            if canvas_saved:
                canvas_context = "\nCOMPONENTS CURRENTLY ON CANVAS:\n"
                for sc in canvas_saved:
                    cd = sc.get("component_data", {})
                    source_tool = cd.get("_source_tool", "unknown")
                    source_agent = cd.get("_source_agent", "unknown")
                    canvas_context += (
                        f"- ID: {sc['id']} | Title: {sc['title']} "
                        f"| Type: {sc['component_type']} | Tool: {source_tool} | Agent: {source_agent}\n"
                    )

            system_prompt = f"""You are an AI orchestrator. Your goal is to simplify complex tasks for the user by intelligently using available tools.

{file_context}

AVAILABLE TOOLS: sent in the `tools` parameter.

PROCESS (Re-Act Loop):
1. **Analyze**: Break down the user's request into logical steps.
2. **Plan & Execute**:
   - If you need data, call the appropriate tool.
   - You can call multiple tools in parallel if they are independent.
   - If a step depends on previous output (e.g., "search patients" -> "graph their age"), wait for the first tool's result before calling the next.
3. **Observe**: You will receive the tool's output in the next turn.
4. **Iterate**:
   - IF the task is not complete or you need more data (e.g., now you have the patients, need to graph them), call the next tool.
   - IF you have all necessary information, provide a final answer.

CRITICAL RULES:
- **VERIFY**: Check if tool outputs actually contain the data you expect before stating it exists. If a search returns 0 results, do NOT try to graph them.
- **FINAL RESPONSE**: When you have finished all actions, provide a natural language summary of what you did and what was found.
- **VISUALIZATIONS**: If the user asks for a graph, YOU MUST call the graphing tool. Do not just describe the data.
{canvas_context}
COMPONENT UPDATE RULES:
- The user's canvas already has the components listed above under COMPONENTS CURRENTLY ON CANVAS.
- When the user asks to MODIFY, UPDATE, REMOVE items from, or CHANGE existing displayed data, re-call the SAME tool that originally created it with the corrected/updated parameters. Do NOT create duplicates.
- When the user asks for something completely NEW and unrelated, call the appropriate tool normally.
"""

            # Feature 008-llm-text-only-chat (FR-006a). When this turn
            # is dispatching with no tools, append the text-only
            # addendum so the LLM (a) does not emit tool calls,
            # (b) does not fabricate tool output, and (c) tells the
            # user to enable an agent for action-style requests.
            if is_text_only:
                system_prompt += TEXT_ONLY_SYSTEM_PROMPT_ADDENDUM

            # Inject knowledge-based routing hints if available
            if flags.is_enabled("knowledge_synthesis") and hasattr(self, 'knowledge_index'):
                routing_hints = self.knowledge_index.get_routing_hints()
                if routing_hints:
                    system_prompt += f"\n{routing_hints}\n"

            # ------------------------------------------------------------------
            # MULTI-TURN LOOP
            # ------------------------------------------------------------------
            # Fetch recent history
            history_messages = []
            chat_data = self.history.get_chat(chat_id, user_id=user_id)
            if chat_data and "messages" in chat_data:
                # Get last 10 messages (excluding the one we just added)
                raw_history = chat_data["messages"][:-1]
                for h_msg in raw_history[-10:]:
                    role = h_msg.get("role")
                    content = h_msg.get("content")
                    
                    # If content is UI component list, stringify it or summarize it
                    if isinstance(content, list):
                        # Try to find text content or just stringify the whole thing
                        content_str = json.dumps(content)
                        # Optional: limit size of historical UI components
                        if len(content_str) > 2000:
                            content_str = content_str[:2000] + "... [TRUNCATED]"
                    else:
                        content_str = str(content)
                        
                    history_messages.append({"role": role, "content": content_str})

            messages = [
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user", "content": message}
            ]

            MAX_TURNS = 10
            turn_count = 0
            heartbeat_task = await self._start_heartbeat(websocket)

            # Denial loop detection: track tools denied by permission checks
            denial_tracker: Dict[str, int] = {}  # tool_name -> denial count
            DENIAL_THRESHOLD = 2  # remove tool from prompt after this many denials

            # Task state machine: create and track this Re-Act execution
            task = None
            if flags.is_enabled("task_state_machine"):
                task = self.task_manager.create_task(chat_id, user_id or "", message=message)
                task.transition(TaskState.RUNNING)

            while turn_count < MAX_TURNS:
                # Check for cancellation
                if self.cancelled_sessions.get(id(websocket)):
                    if task:
                        task.transition(TaskState.CANCELLED)
                    logger.info(f"Processing cancelled by user for chat_id {chat_id}")
                    await self.send_ui_render(websocket, [
                        Alert(message="Processing was cancelled.", variant="info").to_json()
                    ])
                    self.history.add_message(chat_id, "assistant", [
                        Alert(message="Processing was cancelled.", variant="info").to_json()
                    ], user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    return

                turn_count += 1
                logger.info(f"--- Turn {turn_count}/{MAX_TURNS} ---")

                # Message compaction: summarize older turns if context budget exceeded
                if flags.is_enabled("message_compaction"):
                    messages, was_compacted = await compact_messages(
                        messages, self.llm_model, self._call_llm
                    )
                    if was_compacted:
                        logger.info("Context compacted before LLM call")

                # Call LLM. Feature 008: text-only turns tag the audit
                # event with feature="chat_dispatch_text_only" so
                # operators can distinguish fallback dispatches from
                # tool-augmented ones (FR-009).
                call_feature = "chat_dispatch_text_only" if is_text_only else "tool_dispatch"
                llm_msg, usage = await self._call_llm(
                    websocket, messages, tools_desc, feature=call_feature
                )
                self._accumulate_usage(chat_id, usage)
                if not llm_msg:
                    logger.error("LLM returned None, stopping loop.")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message="Failed to get a response from the AI model. Please try again.", variant="error").to_json()
                    ])
                    return

                # Check for reasoning content (DeepSeek, o1, etc.)
                reasoning = getattr(llm_msg, 'reasoning_content', None)
                if reasoning:
                    logger.info(f"LLM returned reasoning content ({len(reasoning)} chars)")
                    reasoning_components = [
                        Collapsible(title="Reasoning", content=[
                            Text(content=reasoning, variant="markdown")
                        ]).to_json()
                    ]
                    await self.send_ui_render(websocket, reasoning_components)
                    self.history.add_message(chat_id, "assistant", reasoning_components, user_id=user_id)

                # Check if LLM wants to call tools
                if llm_msg.tool_calls:
                    logger.info(f"LLM requested {len(llm_msg.tool_calls)} tool(s)")
                    
                    # Notify UI
                    tool_names = [tc.function.name for tc in llm_msg.tool_calls]
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "executing",
                        "message": f"Running: {', '.join(tool_names)}..."
                    }))

                    # Add assistant's message (with tool calls) to history
                    messages.append(llm_msg)

                    # Execute tools
                    if task:
                        tool_names_for_task = [tc.function.name for tc in llm_msg.tool_calls]
                        task.transition(TaskState.AWAITING_TOOL,
                                       current_tool=", ".join(tool_names_for_task),
                                       turn_count=turn_count)
                    tool_results = []
                    if len(llm_msg.tool_calls) == 1:
                        tc = llm_msg.tool_calls[0]
                        res = await self.execute_single_tool(websocket, tc, tool_to_agent, chat_id, user_id=user_id)
                        if res: tool_results.append(res)
                    else:
                        res_list = await self.execute_parallel_tools(websocket, llm_msg.tool_calls, tool_to_agent, chat_id, user_id=user_id)
                        tool_results.extend(res_list)

                    # Collect tool UI components and tag each (recursively) with source metadata
                    def _tag_source(comp, agent_id, tool_name, tool_params=None, correlation_id=None):
                        """Recursively tag a component dict and all nested children.

                        `tool_params` is only tagged on the top-level node — the
                        frontend auto-subscribe path reads it there to replay the
                        same arguments on `stream_subscribe`.

                        Feature 004: `correlation_id` is the audit-log id of the
                        originating tool dispatch. When present, every component
                        (including nested children) carries it so the frontend
                        can scope user feedback to the originating dispatch.
                        """
                        if not isinstance(comp, dict):
                            return
                        comp["_source_agent"] = agent_id
                        comp["_source_tool"] = tool_name
                        if tool_params is not None:
                            comp["_source_params"] = tool_params
                        if correlation_id is not None:
                            comp["_source_correlation_id"] = correlation_id
                        for key in ("content", "children"):
                            nested = comp.get(key)
                            if isinstance(nested, list):
                                for child in nested:
                                    _tag_source(child, agent_id, tool_name, correlation_id=correlation_id)

                    tool_ui_components = []
                    for i_tc, res in enumerate(tool_results):
                        if res and res.ui_components and not res.error:
                            tc = llm_msg.tool_calls[i_tc] if i_tc < len(llm_msg.tool_calls) else None
                            t_name = tc.function.name if tc else ""
                            a_id = tool_to_agent.get(t_name, "")
                            t_params: Dict[str, Any] = {}
                            if tc is not None:
                                try:
                                    raw_args = tc.function.arguments
                                    if isinstance(raw_args, str):
                                        t_params = json.loads(raw_args) if raw_args else {}
                                    elif isinstance(raw_args, dict):
                                        t_params = raw_args
                                except (ValueError, TypeError):
                                    t_params = {}
                            corr_id = getattr(res, "correlation_id", None)
                            for comp in res.ui_components:
                                _tag_source(comp, a_id, t_name, tool_params=t_params, correlation_id=corr_id)
                                tool_ui_components.append(comp)

                    if tool_ui_components:
                        # Send components, auto-replacing any that match existing canvas components
                        await self._send_or_replace_components(
                            websocket, tool_ui_components, chat_id, user_id=user_id
                        )
                        if chat_id:
                            self.history.add_message(chat_id, "assistant", tool_ui_components, user_id=user_id)

                    # Append tool outputs to LLM conversation history
                    for i, tc in enumerate(llm_msg.tool_calls):
                        res = tool_results[i] if i < len(tool_results) else None
                        
                        content_str = "No output"
                        if res:
                            if res.error:
                                content_str = f"Error: {res.error.get('message')}"
                            elif res.result:
                                if isinstance(res.result, dict) and "_data" in res.result:
                                    content_str = json.dumps(res.result["_data"])
                                else:
                                    content_str = json.dumps(res.result)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": content_str
                        })

                    # Denial loop detection: track permission-denied tool results
                    if flags.is_enabled("denial_loop_detection"):
                        for i, tc in enumerate(llm_msg.tool_calls):
                            res = tool_results[i] if i < len(tool_results) else None
                            if res and res.error and "restricted" in res.error.get("message", "").lower():
                                name = tc.function.name
                                denial_tracker[name] = denial_tracker.get(name, 0) + 1
                                if denial_tracker[name] >= DENIAL_THRESHOLD:
                                    logger.info(f"Denial loop: removing '{name}' from tools after {denial_tracker[name]} denials")
                                    tools_desc = [t for t in tools_desc if t["function"]["name"] != name]
                                    # Inject a system hint so the LLM stops trying
                                    messages.append({
                                        "role": "system",
                                        "content": f"IMPORTANT: The tool '{name}' is not available due to permission restrictions. Do NOT attempt to use it again. Find an alternative approach or inform the user."
                                    })
                        # If ALL tools have been removed, break early
                        if not tools_desc:
                            logger.warning("All tools denied — breaking Re-Act loop")
                            await self.send_ui_render(websocket, [
                                Alert(message="All available tools are restricted by your permission settings. Please update your agent permissions.", variant="warning").to_json()
                            ])
                            break

                    # Update task state and track tool calls
                    if task:
                        for tc in llm_msg.tool_calls:
                            task.tool_calls_made.append(tc.function.name)
                        task.transition(TaskState.RUNNING, current_tool=None)

                    # Loop continues to next turn to let LLM analyze results
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "thinking",
                        "message": "Analyzing results..."
                    }))
                
                else:
                    # No tool calls -> Final Response
                    if task:
                        task.transition(TaskState.COMPLETED, turn_count=turn_count)
                    # Strip any tool-call tokens that leaked into the
                    # text response — see _sanitize_text_response. This
                    # defends against open-weight LLMs that emit raw
                    # `<|tool_call|>...` markup even when asked not to,
                    # which is what users see when they disable all
                    # agents and the LLM still tries to invoke a tool.
                    raw_content = llm_msg.content or ""
                    content = _sanitize_text_response(raw_content)
                    if content != raw_content.strip():
                        logger.warning(
                            "Stripped leaked tool-call tokens from text response "
                            "(chat_id=%s user_id=%s is_text_only=%s raw_len=%d clean_len=%d)",
                            chat_id, user_id, is_text_only, len(raw_content), len(content),
                        )
                    if not content:
                        content = "I'm not sure how to help with that."
                    
                    parsed_components = None
                    needs_retry = False
                    error_msg = ""
                    
                    # Heuristic: if it looks like JSON containing a component
                    stripped = content.strip()
                    looks_like_json = stripped.startswith("{") or stripped.startswith("[") or "```json" in content

                    if looks_like_json:
                        raw_json = content
                        if "```json" in content:
                            match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
                            if match:
                                raw_json = match.group(1)
                            else:
                                match = re.search(r'```(.*?)```', content, re.DOTALL)
                                if match:
                                    raw_json = match.group(1).strip()
                    else:
                        # Fallback: LLM may have output text before JSON components
                        # Search for a JSON array or object containing a "type" field
                        json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})\s*$', content)
                        if json_match:
                            raw_json = json_match.group(1)
                            looks_like_json = True
                            logger.info("Extracted trailing JSON from mixed text+JSON response")

                    if looks_like_json:
                        try:
                            # Try to parse and find valid components
                            # Using the same technique as the _combine_components_llm parser
                            # First try to parse directly
                            try:
                                data = json.loads(raw_json)
                            except json.JSONDecodeError:
                                # Strip markdown code fences if present
                                if raw_json.startswith("```"):
                                    raw_json = raw_json.split("\n", 1)[1] if "\n" in raw_json else raw_json[3:]
                                    if raw_json.endswith("```"):
                                        raw_json = raw_json[:-3]
                                    raw_json = raw_json.strip()

                                try:
                                    data = json.loads(raw_json)
                                except json.JSONDecodeError:
                                    # Fallback: regex search for JSON
                                    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw_json)
                                    if json_match:
                                        data = json.loads(json_match.group())
                                    else:
                                        raise
                            
                            if isinstance(data, dict):
                                # Unwrap common LLM wrapper patterns:
                                # {"components": [...]}, {"ui_components": [...]}, {"content": [...]}
                                for wrapper_key in ("components", "ui_components", "content"):
                                    if wrapper_key in data and isinstance(data[wrapper_key], list):
                                        inner = data[wrapper_key]
                                        # Verify at least one inner item looks like a component
                                        if any(isinstance(x, dict) and "type" in x for x in inner):
                                            data = inner
                                            break
                                else:
                                    data = [data]
                            
                            valid_components = []
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and "type" in item:
                                        # Recursively validate component structure to ensure frontend won't crash
                                        self._validate_component_tree(item, {
                                            "container", "text", "button", "card", "table", "list",
                                            "alert", "progress", "metric", "code", "image", "grid",
                                            "tabs", "divider", "input", "bar_chart", "line_chart",
                                            "pie_chart", "plotly_chart", "collapsible",
                                            "file_upload", "file_download"
                                        })
                                        valid_components.append(item)
                            
                            if valid_components:
                                parsed_components = valid_components
                            else:
                                needs_retry = True
                                error_msg = "JSON parsed successfully but no valid UI components found. Each component MUST be an object with at least a 'type' field (e.g., {'type': 'card', 'title': '...', 'content': [...]})."
                                
                        except Exception as e:
                            needs_retry = True
                            error_msg = f"Failed to parse UI components. The output is not valid JSON. Error: {str(e)}. Please respond ONLY with valid JSON, with NO surrounding text or markdown formatting."
                    
                    if needs_retry and turn_count < MAX_TURNS:
                        logger.warning(f"UI component generation failed parsing. Retrying. Error: {error_msg}")
                        messages.append(llm_msg)
                        messages.append({
                            "role": "user",
                            "content": f"SYSTEM RECOVERY ERROR: {error_msg}\nRemember, you MUST output ONLY valid JSON without Markdown formatting, enclosing explanations, or preamble. Return the complete corrected component array."
                        })
                        
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status",
                            "status": "thinking",
                            "message": "Fixing formatting errors in UI component..."
                        }))
                        continue
                    
                    logger.info("LLM provided final response. conversation complete.")
                    
                    if parsed_components:
                        response_components = parsed_components

                        if self._is_text_only_components(parsed_components):
                            # Text-only components -- route to chat panel only
                            await self.send_ui_render(websocket, response_components, target="chat")
                        else:
                            # Rich UI components -- send to canvas + chat summary
                            await self._send_or_replace_components(
                                websocket, response_components, chat_id, user_id=user_id
                            )
                            chat_summary = [
                                Card(title="Analysis", content=[
                                    Text(content=content, variant="markdown")
                                ]).to_json()
                            ]
                            await self.send_ui_render(websocket, chat_summary, target="chat")
                    else:
                        response_components = [
                            Card(title="Analysis", content=[
                                Text(content=content, variant="markdown")
                            ]).to_json()
                        ]
                        # Pure text response goes to chat panel
                        await self.send_ui_render(websocket, response_components, target="chat")

                    # Save complete interaction to history
                    self.history.add_message(chat_id, "assistant", response_components, user_id=user_id)

                    # Signal that processing is complete
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    return

            # If loop exits without final response — generate LLM summary
            if turn_count >= MAX_TURNS:
                logger.info(f"Max turns ({turn_count}) reached. Generating summary of tool outputs.")
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "thinking",
                    "message": "Generating summary..."
                }))

                summary_components = await self._generate_tool_summary(
                    websocket, messages, chat_id, user_id=user_id
                )
                if summary_components:
                    await self.send_ui_render(websocket, summary_components)
                    if chat_id:
                        self.history.add_message(chat_id, "assistant", summary_components, user_id=user_id)
                else:
                    # Fallback if LLM summary fails
                    await self.send_ui_render(websocket, [
                        Card(title="Summary", content=[
                            Text(content="Multiple tool operations were completed. Review the results above for details.", variant="body")
                        ]).to_json()
                    ])

                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "done",
                    "message": ""
                }))

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"WebSocket closed during chat processing for chat_id {chat_id} — client likely reconnected")
        except Exception as e:
            logger.error(f"LLM routing error: {e}", exc_info=True)
            error_text = str(e)

            # Auto-fix: if this is a draft agent test chat and the error is a bad tool schema,
            # trigger auto-fix so the agent code gets corrected automatically.
            if draft_agent_id and hasattr(self, 'lifecycle_manager') and ("invalid" in error_text.lower() and "schema" in error_text.lower()):
                logger.info(f"Bad tool schema for draft agent {draft_agent_id} — triggering auto-fix")
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "fixing",
                        "message": f"Invalid tool schema detected — auto-fixing agent code..."
                    }))
                    fixed = await self.lifecycle_manager.auto_fix_tool_error(
                        draft_agent_id, "_schema_validation",
                        f"The agent's TOOL_REGISTRY has invalid input_schema definitions. "
                        f"The LLM API rejected the tool schemas with this error: {error_text}\n"
                        f"Common cause: using 'required': True on individual properties instead of "
                        f"a 'required': ['field1', 'field2'] array at the object level.",
                        websocket
                    )
                    if fixed:
                        await self.send_ui_render(websocket, [
                            Alert(message="Tool schema fixed. Agent restarted — please try your message again.", variant="info").to_json()
                        ])
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Auto-fix could not resolve the schema issue. Try refining the agent.", variant="warning").to_json()
                        ])
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "done", "message": ""
                    }))
                except Exception as fix_err:
                    logger.warning(f"Auto-fix for schema error failed: {fix_err}")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "done", "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message=f"Tool schema error and auto-fix failed: {error_text}", variant="error", title="Error").to_json()
                    ])
            else:
                # Clear the 'thinking' spinner so the UI doesn't hang
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "done",
                    "message": ""
                }))
                # Show a user-friendly error message
                if "424" in error_text or "Failed Dependency" in error_text or "Repository Not Found" in error_text:
                    error_text = f"The LLM server cannot find the configured model '{self.llm_model}'. Please verify the model name in your .env file and that the vLLM server has this model loaded."
                elif "502" in error_text or "Bad Gateway" in error_text:
                    error_text = "The AI model returned a 502 Bad Gateway error. It may be overloaded or restarting. Please try again in a moment."
                elif "504" in error_text or "Gateway Time-out" in error_text:
                    error_text = "The AI model timed out. It may be overloaded or still warming up. Please try again in a moment."
                elif "timeout" in error_text.lower():
                    error_text = "Request timed out waiting for the AI model. Please try again."
                await self.send_ui_render(websocket, [
                    Alert(message=error_text, variant="error", title="Error").to_json()
                ])
        finally:
            heartbeat_task.cancel()

    def _accumulate_usage(self, chat_id: Optional[str], usage):
        """Accumulate LLM token usage for a conversation.

        Args:
            chat_id: Conversation identifier. Skipped if None.
            usage: The ``usage`` object from an OpenAI-compatible response.
        """
        if not usage or not chat_id:
            return
        if chat_id not in self.token_usage:
            self.token_usage[chat_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        self.token_usage[chat_id]["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        self.token_usage[chat_id]["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        self.token_usage[chat_id]["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
        logger.info(
            f"Token usage for chat {chat_id}: {self.token_usage[chat_id]}"
        )

    # ------------------------------------------------------------------
    # Feature 006 — credential resolution helpers
    # ------------------------------------------------------------------

    def _resolve_llm_client_for(self, websocket):
        """Resolve the (client, source, resolved) tuple for a per-call LLM
        invocation on behalf of the user behind ``websocket``.

        - If the user has saved personal credentials in their browser and
          forwarded them on register_ui or via llm_config_set, those are
          used (CredentialSource.USER).
        - Otherwise, if the operator has supplied .env defaults, those
          are used (CredentialSource.OPERATOR_DEFAULT).
        - Otherwise, raises LLMUnavailable. Callers handle this by
          emitting an llm_unconfigured audit event and surfacing the
          'LLM unavailable' UI prompt (FR-004a).

        ``websocket`` may be None for server-initiated background jobs
        (e.g. the daily feedback quality / proposals job from feature 004).
        Such jobs always use the operator default — no individual user is
        the caller. (FR-011)
        """
        ws_id = id(websocket) if websocket is not None else None
        session_creds = (
            self._session_llm_creds.get(ws_id) if ws_id is not None else None
        )
        return self._build_llm_client(session_creds, self._operator_creds)

    def _llm_audit_principals(self, websocket):
        """Return ``(actor_user_id, auth_principal)`` for audit-event emission
        on behalf of ``websocket``.

        Mirrors the convention used elsewhere in the orchestrator
        (handle_ui_message lines 743/758/771). Background-job calls with
        websocket=None get ``actor_user_id='system'`` per FR-011 wiring
        in audit-events.md.
        """
        if websocket is None:
            return ("system", "system")
        claims = self.ui_sessions.get(websocket) or {}
        actor_user_id = claims.get("sub") or "legacy"
        auth_principal = (
            claims.get("preferred_username") or claims.get("sub") or "unknown"
        )
        return (actor_user_id, auth_principal)

    @staticmethod
    def _classify_llm_upstream_error(exc) -> str:
        """Map an upstream OpenAI-SDK exception to one of the audit-event
        ``upstream_error_class`` taxonomy values defined in
        contracts/audit-events.md §3.
        """
        s = str(exc)
        if "401" in s or "auth" in s.lower():
            return "auth_failed"
        if "429" in s or "rate" in s.lower():
            return "rate_limit"
        if "404" in s or "not found" in s.lower() or "model" in s.lower() and "not" in s.lower():
            return "model_not_found"
        if any(k in s.lower() for k in ("connection", "timeout", "network", "dns")):
            return "transport_error"
        return "other"

    async def _call_llm(self, websocket, messages, tools_desc=None, temperature=None,
                        feature: str = "tool_dispatch"):
        """Helper to call LLM with retries and exponential backoff.

        Only retries on transient errors (502, 503, 504). Fails fast on
        non-transient errors like 424 (model not found) or 401 (auth).

        Feature 006: credential resolution happens here. The caller's
        credentials (or operator default) are picked up from the
        per-WebSocket credential store via ``_resolve_llm_client_for``.
        Every call emits an ``llm_call`` audit event with
        ``credential_source`` so SC-006 invariants can be verified;
        ``LLMUnavailable`` (no credentials anywhere) emits
        ``llm_unconfigured`` instead and returns ``(None, None)``.

        Returns:
            Tuple of (message, usage) where usage is the token usage object
            from the API response, or (None, None) on complete failure.
        """
        actor_user_id, auth_principal = self._llm_audit_principals(websocket)
        try:
            client, source, resolved = self._resolve_llm_client_for(websocket)
        except self._LLMUnavailable:
            await self._record_llm_unconfigured(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
            )
            return None, None
        # The resolved.model is the user's chosen model when source=USER,
        # else the operator default model (== self.llm_model).
        call_model = resolved.model
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": call_model,
                    "messages": messages
                }
                if tools_desc:
                    kwargs["tools"] = tools_desc
                    kwargs["tool_choice"] = "auto"
                if temperature is not None:
                    kwargs["temperature"] = temperature

                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    **kwargs
                )
                # Defensive: some upstream proxies return a 200 status with
                # an HTML maintenance page body (e.g. an Apache 503/502 from
                # an in-front load balancer that swallowed the upstream
                # error). The OpenAI client happily passes this through as
                # message content, and it would render as the assistant's
                # reply. Detect the shape and treat it as a transient
                # failure so the existing retry + clean-Alert path runs.
                _msg = response.choices[0].message if response.choices else None
                _content = (getattr(_msg, "content", None) or "").lstrip()
                if _content and _content[:200].lower().startswith(
                    ("<!doctype html", "<html", "<head", "<body")
                ):
                    raise RuntimeError(
                        "LLM upstream returned an HTML page instead of a "
                        "model response (likely a provider maintenance "
                        "page); treating as transient."
                    )
                usage = getattr(response, "usage", None)
                # Audit: successful llm_call
                total_tokens = getattr(usage, "total_tokens", None) if usage else None
                await self._record_llm_call(
                    self.audit_recorder,
                    actor_user_id=actor_user_id,
                    auth_principal=auth_principal,
                    feature=feature,
                    credential_source=source,
                    resolved=resolved,
                    total_tokens=total_tokens,
                    outcome="success",
                )
                # Feature 006: emit llm_usage_report WS message ONLY when
                # the call was served with the user's personal credentials
                # (FR-016 — operator-default calls are NOT attributed to
                # the user's per-device counters).
                if source == self._CredentialSource.USER and websocket is not None:
                    await self._emit_llm_usage_report(
                        websocket,
                        feature=feature,
                        model=call_model,
                        usage=usage,
                        outcome="success",
                    )
                return response.choices[0].message, usage
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_transient = any(code in error_str for code in ["502", "503", "504", "Bad Gateway", "Service Unavailable", "Connection", "timeout"])
                is_fatal = any(code in error_str for code in ["424", "401", "403", "Repository Not Found", "Invalid username"])

                logger.warning(f"LLM Attempt {attempt}/{self.MAX_RETRIES} failed: {e}")

                # Don't retry fatal errors — they won't resolve with retries
                if is_fatal:
                    logger.error(f"Fatal LLM error (no retry): {e}")
                    await self._record_llm_call(
                        self.audit_recorder,
                        actor_user_id=actor_user_id,
                        auth_principal=auth_principal,
                        feature=feature,
                        credential_source=source,
                        resolved=resolved,
                        total_tokens=None,
                        outcome="failure",
                        upstream_error_class=self._classify_llm_upstream_error(e),
                    )
                    if source == self._CredentialSource.USER and websocket is not None:
                        await self._emit_llm_usage_report(
                            websocket, feature=feature, model=call_model,
                            usage=None, outcome="failure",
                        )
                    raise e

                if attempt == self.MAX_RETRIES:
                    await self._record_llm_call(
                        self.audit_recorder,
                        actor_user_id=actor_user_id,
                        auth_principal=auth_principal,
                        feature=feature,
                        credential_source=source,
                        resolved=resolved,
                        total_tokens=None,
                        outcome="failure",
                        upstream_error_class=self._classify_llm_upstream_error(e),
                    )
                    if source == self._CredentialSource.USER and websocket is not None:
                        await self._emit_llm_usage_report(
                            websocket, feature=feature, model=call_model,
                            usage=None, outcome="failure",
                        )
                    # Return (None, None) so callers fall through to the
                    # existing user-friendly "Failed to get a response from
                    # the AI model" Alert. Raising here would surface raw
                    # upstream payloads (e.g. a provider's 503 HTML page)
                    # in chat error text — the structured log + audit
                    # event above retain the full details for operators.
                    return None, None

                # Exponential backoff: 1s, 2s, 4s, 8s
                backoff = min(2 ** (attempt - 1), 8)
                if is_transient:
                    logger.info(f"Transient error detected, retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        # Defensive: should be unreachable since the MAX_RETRIES branch raises.
        return None, None

    async def _emit_llm_usage_report(self, websocket, *, feature, model, usage, outcome):
        """Send an ``llm_usage_report`` message to ``websocket`` carrying the
        token-usage tally for one LLM-dependent call (feature 006 FR-014).

        Only invoked when the call's credential source was ``user`` —
        operator-default calls are NOT reported to the per-device
        token-usage counters (FR-016). Best-effort fire-and-forget;
        failures here never affect the LLM call's user-facing result.
        """
        try:
            from datetime import datetime, timezone
            payload = {
                "type": "llm_usage_report",
                "feature": feature,
                "model": model,
                "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
                "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "outcome": outcome,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            await self._safe_send(websocket, json.dumps(payload))
        except Exception as exc:  # pragma: no cover — best-effort delivery
            logger.debug(f"llm_usage_report send failed (non-fatal): {exc}")

    async def _generate_tool_summary(self, websocket, messages, chat_id=None, user_id=None):
        """
        Generate an LLM summary/analysis of accumulated tool results.
        Called when the Re-Act loop ends (max turns or completion) to ensure
        the user always gets a meaningful summary rather than a 'stopped' message.

        Feature 006: routes through the per-user / operator-default
        credential resolver. ``LLMUnavailable`` (no credentials available)
        emits an llm_unconfigured audit event and returns None silently —
        a missing summary is non-fatal and the user already has the
        primary tool output.
        """
        feature = "tool_summary"
        actor_user_id, auth_principal = self._llm_audit_principals(websocket)
        try:
            client, source, resolved = self._resolve_llm_client_for(websocket)
        except self._LLMUnavailable:
            await self._record_llm_unconfigured(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
            )
            return None

        try:
            # Build a summary-focused prompt from the conversation so far
            summary_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are summarizing the results of tool operations that were just performed. "
                        "Provide a concise, insightful analysis of what was accomplished and the key findings. "
                        "Focus on actionable insights, important numbers, and recommendations. "
                        "Do NOT mention internal details like tool names, turn counts, or system mechanics. "
                        "Write as if you are presenting results to the user directly. "
                        "Keep it to 2-4 sentences."
                    ),
                },
            ]

            # Include relevant parts of the conversation (last several messages)
            for msg in messages[-8:]:
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role in ("user", "tool", "assistant") and content:
                        # Truncate long tool outputs
                        if len(str(content)) > 1500:
                            content = str(content)[:1500] + "..."
                        summary_messages.append({"role": role if role != "tool" else "user", "content": str(content)})

            summary_messages.append({
                "role": "user",
                "content": "Based on the tool results above, provide a brief summary and analysis."
            })

            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=resolved.model,
                messages=summary_messages,
                max_tokens=300,
            )
            usage = getattr(response, "usage", None)
            self._accumulate_usage(chat_id, usage)
            total_tokens = getattr(usage, "total_tokens", None) if usage else None
            await self._record_llm_call(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
                credential_source=source,
                resolved=resolved,
                total_tokens=total_tokens,
                outcome="success",
            )
            if source == self._CredentialSource.USER and websocket is not None:
                await self._emit_llm_usage_report(
                    websocket, feature=feature, model=resolved.model,
                    usage=usage, outcome="success",
                )

            summary_text = response.choices[0].message.content or ""
            summary_text = summary_text.strip()

            if summary_text:
                return [
                    Card(title="Summary", content=[
                        Text(content=summary_text, variant="body")
                    ]).to_json()
                ]

        except Exception as e:
            logger.warning(f"Failed to generate tool summary: {e}")
            await self._record_llm_call(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
                credential_source=source,
                resolved=resolved,
                total_tokens=None,
                outcome="failure",
                upstream_error_class=self._classify_llm_upstream_error(e),
            )
            if source == self._CredentialSource.USER and websocket is not None:
                await self._emit_llm_usage_report(
                    websocket, feature=feature, model=resolved.model,
                    usage=None, outcome="failure",
                )

        return None

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1.0, 2.0, 4.0]  # exponential backoff

    async def execute_single_tool(self, websocket, tool_call, tool_to_agent: Dict, chat_id: str = None, user_id: str = None) -> Optional[MCPResponse]:
        """Execute a single tool call and render its UI components. Returns the Result object."""
        tool_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        except json.JSONDecodeError:
            args = {}

        # System-level security block (proactive security review)
        agent_id = tool_to_agent.get(tool_name)
        agent_flags = self.security_flags.get(agent_id, {}) if agent_id else {}
        if agent_id and tool_name in agent_flags and agent_flags[tool_name].get("blocked"):
            reason = agent_flags[tool_name].get("reason", "Security threat detected")
            err_msg = f"Tool '{tool_name}' is system-blocked: {reason}"
            logger.warning(f"Security block: agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="error")
            await self.send_ui_render(websocket, [alert.to_json()], target="chat")
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_json()]
            )

        # Permission enforcement gate (RFC 8693 delegation)
        if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
            err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
            logger.warning(f"Permission denied: user={user_id} agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="warning")
            await self.send_ui_render(websocket, [alert.to_json()])
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_json()]
            )

        # Map file paths if chat_id provided
        if chat_id:
            args = self._map_file_paths(chat_id, args, user_id=user_id)
            args["session_id"] = chat_id
            if user_id:
                args["user_id"] = user_id

        # Inject per-user credentials (E2E encrypted — only agent can decrypt)
        if user_id and agent_id:
            creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
            if creds:
                args["_credentials"] = creds
                args["_credentials_encrypted"] = True

        # Feature 006: surface the user's personal LLM credentials (if
        # any) so agent-side tools that fall back to OPENAI_* env vars
        # pick them up instead. We use a separate kwarg
        # (``_session_llm_credentials``) to avoid colliding with the
        # encrypted ``_credentials`` bundle above — agent code that
        # wants the user's LLM creds reads ``_session_llm_credentials``
        # in preference to env. mcp_tools.py with its existing
        # ``creds.get("OPENAI_API_KEY") or os.getenv(...)`` pattern is
        # NOT modified by this feature; it continues to work against
        # the operator-default env. Future agent-side wiring may opt
        # into reading ``_session_llm_credentials`` first.
        session_llm = (
            self._session_llm_creds.get(id(websocket))
            if websocket is not None else None
        )
        if session_llm is not None:
            args["_session_llm_credentials"] = {
                "OPENAI_API_KEY": session_llm.api_key,
                "OPENAI_BASE_URL": session_llm.base_url,
                "LLM_MODEL": session_llm.model,
            }

        if not agent_id or (agent_id not in self.agents and agent_id not in self.a2a_clients):
            err_msg = f"No agent available for tool '{tool_name}'"
            await self.send_ui_render(websocket, [
                Alert(message=err_msg, variant="error").to_json()
            ], target="chat")
            return MCPResponse(error={"message": err_msg})

        # RFC 8693 delegation: generate a scoped token excluding system-blocked tools
        # The delegation token constrains what the agent can do even if it's compromised
        if user_id and agent_id:
            delegation_token = await self._get_delegation_token(websocket, agent_id, user_id)
            if delegation_token:
                args["_delegation_token"] = delegation_token

        # Hook: PRE_TOOL_USE — allows handlers to block or modify tool args
        if flags.is_enabled("hook_system"):
            hook_ctx = HookContext(
                event=HookEvent.PRE_TOOL_USE,
                user_id=user_id or "",
                agent_id=agent_id or "",
                tool_name=tool_name,
                tool_args=args,
            )
            hook_resp = await self.hooks.emit(hook_ctx)
            if hook_resp.action == "block":
                err_msg = f"Tool '{tool_name}' blocked by hook: {hook_resp.reason or 'no reason given'}"
                logger.info(f"Hook blocked tool: {tool_name}")
                return MCPResponse(error={"message": err_msg, "retryable": False})
            if hook_resp.action == "modify" and hook_resp.modified_args:
                args = hook_resp.modified_args

        # Audit: record the tool dispatch (in_progress → success/failure)
        from audit.hooks import ToolDispatchAudit
        claims = self.ui_sessions.get(websocket) if websocket is not None else None
        async with ToolDispatchAudit(
            claims=claims,
            agent_id=agent_id,
            tool_name=tool_name,
            chat_id=chat_id,
            args_meta={k: v for k, v in args.items() if not (isinstance(k, str) and k.startswith("_"))},
        ) as _audit_ctx:
            result = await self._execute_with_retry(websocket, agent_id, tool_name, args)
            if result and result.error:
                _audit_ctx.set_outcome("failure", str(result.error.get("message", ""))[:1000])
            elif result is None:
                _audit_ctx.set_outcome("interrupted", "no result returned")
            else:
                _audit_ctx.set_outputs_meta({"has_ui_components": bool(result.ui_components)})
            # Feature 004: propagate the audit correlation_id onto the response
            # so the caller can tag every produced UI component with the
            # originating dispatch's id. The frontend's component_feedback
            # flow uses this to scope a user's feedback to a specific dispatch.
            if result is not None:
                try:
                    result.correlation_id = _audit_ctx.correlation_id
                except Exception:
                    pass

        # Hook: POST_TOOL_USE or POST_TOOL_FAILURE
        if flags.is_enabled("hook_system"):
            post_event = HookEvent.POST_TOOL_FAILURE if (result and result.error) else HookEvent.POST_TOOL_USE
            await self.hooks.emit(HookContext(
                event=post_event,
                user_id=user_id or "",
                agent_id=agent_id or "",
                tool_name=tool_name,
                tool_args=args,
                tool_result=result.result if result else None,
                error=result.error.get("message") if (result and result.error) else None,
            ))

        # Don't render tool results immediately — the caller (handle_chat_message)
        # batches all tool results into a single collapsible section.
        if result and result.error:
            # Errors are still shown immediately so the user knows something went wrong
            err_msg = result.error.get('message', 'Unknown error')
            await self.send_ui_render(websocket, [
                Alert(message=f"Tool '{tool_name}' failed: {err_msg}", variant="error").to_json()
            ], target="chat")

            # Auto-fix: if this is a draft agent, attempt to fix the tool error automatically
            if agent_id and hasattr(self, 'lifecycle_manager'):
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "fixing",
                        "message": f"Auto-fixing tool '{tool_name}'..."
                    }))
                    fixed = await self.lifecycle_manager.auto_fix_tool_error(
                        agent_id, tool_name, err_msg, websocket
                    )
                    if fixed:
                        logger.info(f"Auto-fix attempted for draft agent {agent_id} tool '{tool_name}'")
                        await self.send_ui_render(websocket, [
                            Alert(message=f"Auto-fix applied for '{tool_name}'. Agent restarted — try again.", variant="info").to_json()
                        ])
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "thinking",
                        "message": "Continuing after fix..."
                    }))
                except Exception as e:
                    logger.warning(f"Auto-fix failed for {agent_id}: {e}")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "thinking",
                        "message": "Continuing..."
                    }))

        return result

    # Scopes considered safe for concurrent execution (read-only operations)
    _PARALLEL_SAFE_SCOPES = frozenset({"tools:read", "tools:search"})
    _MAX_PARALLEL_CONCURRENCY = 10

    async def execute_parallel_tools(self, websocket, tool_calls, tool_to_agent: Dict, chat_id: str = None, user_id: str = None) -> List[Optional[MCPResponse]]:
        """Execute multiple tool calls with concurrency safety.

        When tool_concurrency_safety is enabled, read-only tools (tools:read,
        tools:search scopes) run in parallel while write/system tools run serially
        after the parallel batch completes.  This prevents race conditions when
        two write tools target the same agent.
        """
        # Phase 1: Prepare all tool calls (args, permissions, credentials)
        prepared = []  # list of (index, tc, tool_name, agent_id, args | None, error_coro | None)

        for idx, tc in enumerate(tool_calls):
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            if chat_id:
                args = self._map_file_paths(chat_id, args, user_id=user_id)
                args["session_id"] = chat_id
                if user_id:
                    args["user_id"] = user_id

            agent_id = tool_to_agent.get(tool_name)

            if user_id and agent_id:
                creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
                if creds:
                    args["_credentials"] = creds
                    args["_credentials_encrypted"] = True

            # System-level security block
            agent_flags = self.security_flags.get(agent_id, {}) if agent_id else {}
            if agent_id and tool_name in agent_flags and agent_flags[tool_name].get("blocked"):
                reason = agent_flags[tool_name].get("reason", "Security threat detected")
                err_msg = f"Tool '{tool_name}' is system-blocked: {reason}"
                logger.warning(f"Security block (parallel): agent={agent_id} tool={tool_name}")
                async def _sec_err(msg=err_msg):
                    return MCPResponse(error={"message": msg, "retryable": False},
                                       ui_components=[Alert(message=msg, variant="error").to_json()])
                prepared.append((idx, tc, tool_name, agent_id, None, _sec_err()))
                continue

            # Permission check
            if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
                err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
                logger.warning(f"Permission denied (parallel): user={user_id} agent={agent_id} tool={tool_name}")
                async def _perm_err(msg=err_msg):
                    return MCPResponse(error={"message": msg, "retryable": False},
                                       ui_components=[Alert(message=msg, variant="error").to_json()])
                prepared.append((idx, tc, tool_name, agent_id, None, _perm_err()))
                continue

            if not agent_id or (agent_id not in self.agents and agent_id not in self.a2a_clients):
                async def _no_agent(tn=tool_name):
                    return MCPResponse(error={"message": f"No agent for {tn}"})
                prepared.append((idx, tc, tool_name, agent_id, None, _no_agent()))
                continue

            prepared.append((idx, tc, tool_name, agent_id, args, None))

        if not prepared:
            return []

        # Phase 2: Partition into parallel-safe vs serial based on scope
        use_concurrency_safety = flags.is_enabled("tool_concurrency_safety")

        parallel_items = []  # (idx, tool_name, coro)
        serial_items = []    # (idx, tool_name, agent_id, args)
        error_items = []     # (idx, coro)

        for idx, tc, tool_name, agent_id, args, err_coro in prepared:
            if err_coro is not None:
                error_items.append((idx, err_coro))
            elif use_concurrency_safety:
                scope = self.tool_permissions.get_tool_scope(agent_id, tool_name)
                if scope in self._PARALLEL_SAFE_SCOPES:
                    parallel_items.append((idx, tool_name, self._execute_with_retry(websocket, agent_id, tool_name, args)))
                else:
                    serial_items.append((idx, tool_name, agent_id, args))
            else:
                parallel_items.append((idx, tool_name, self._execute_with_retry(websocket, agent_id, tool_name, args)))

        # Collect results in original order
        results_by_idx: Dict[int, Any] = {}

        # Execute error items immediately
        for idx, coro in error_items:
            results_by_idx[idx] = await coro

        # Execute parallel-safe tools concurrently (capped)
        if parallel_items:
            sem = asyncio.Semaphore(self._MAX_PARALLEL_CONCURRENCY)
            async def _sem_wrap(coro):
                async with sem:
                    return await coro
            par_results = await asyncio.gather(
                *[_sem_wrap(coro) for _, _, coro in parallel_items],
                return_exceptions=True
            )
            for (idx, _, _), res in zip(parallel_items, par_results):
                results_by_idx[idx] = res

        # Execute serial (write/system) tools one at a time
        for idx, tool_name, agent_id, args in serial_items:
            try:
                results_by_idx[idx] = await self._execute_with_retry(websocket, agent_id, tool_name, args)
            except Exception as e:
                results_by_idx[idx] = e

        if serial_items:
            logger.info(f"Concurrency safety: {len(parallel_items)} parallel, {len(serial_items)} serial")

        # Reassemble in original order
        ordered = [results_by_idx.get(i) for i in range(len(tool_calls))]
        tool_names = [tc.function.name for tc in tool_calls]

        results = ordered
        
        # Process results — don't render here, caller batches into collapsible
        final_results = []
        error_components = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                err_res = MCPResponse(error={"message": str(result)})
                final_results.append(err_res)
                error_components.append(Alert(message=f"Tool error: {str(result)}", variant="error").to_json())
            else:
                final_results.append(result)
                if result and result.error:
                    error_components.append(Alert(message=f"Tool '{tool_names[i]}' failed: {result.error.get('message')}", variant="error").to_json())

        # Only render errors immediately — successful results are batched by caller
        if error_components:
            await self.send_ui_render(websocket, error_components)

        # Auto-fix: attempt to fix draft agent tool errors
        if hasattr(self, 'lifecycle_manager'):
            for i, result in enumerate(final_results):
                if result and result.error:
                    t_name = tool_names[i] if i < len(tool_names) else None
                    a_id = tool_to_agent.get(t_name) if t_name else None
                    if a_id:
                        try:
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "fixing",
                                "message": f"Auto-fixing tool '{t_name}'..."
                            }))
                            await self.lifecycle_manager.auto_fix_tool_error(
                                a_id, t_name, result.error.get('message', ''), websocket
                            )
                            await self.send_ui_render(websocket, [
                                Alert(message=f"Auto-fix applied for '{t_name}'. Agent restarted — try again.", variant="info").to_json()
                            ])
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "thinking",
                                "message": "Continuing after fix..."
                            }))
                        except Exception as e:
                            logger.warning(f"Auto-fix failed for {a_id}: {e}")
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "thinking",
                                "message": "Continuing..."
                            }))

        return final_results

    async def _execute_with_retry(
        self, websocket, agent_id: str, tool_name: str, args: Dict,
        max_retries: int = None
    ) -> Optional[MCPResponse]:
        """Execute a tool call with up to max_retries attempts.

        On retryable errors, sends status updates to the UI and waits
        with exponential backoff before trying again.
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_result = None

        for attempt in range(1, max_retries + 1):
            result = await self.execute_tool_and_wait(agent_id, tool_name, args, ui_websocket=websocket)
            last_result = result

            # Success: no error at all
            if result and not result.error:
                if attempt > 1:
                    logger.info(f"Tool '{tool_name}' succeeded on attempt {attempt}/{max_retries}")
                return result

            # Check if error is retryable
            is_retryable = True
            error_msg = "Unknown error"
            if result and result.error:
                is_retryable = result.error.get("retryable", True)
                error_msg = result.error.get("message", "Unknown error")

            if not is_retryable:
                logger.info(f"Tool '{tool_name}' failed with non-retryable error: {error_msg}")
                return result

            # Retryable error — try again if attempts remain
            if attempt < max_retries:
                backoff = self.RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(self.RETRY_BACKOFF) else 2.0
                logger.warning(
                    f"Tool '{tool_name}' failed (attempt {attempt}/{max_retries}): {error_msg}. "
                    f"Retrying in {backoff}s..."
                )
                # Notify UI about the retry
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "retrying",
                        "message": f"Tool '{tool_name.replace('_', ' ').title()}' failed. "
                                   f"Retrying... (attempt {attempt + 1}/{max_retries})"
                    }))
                except Exception:
                    pass  # Don't let status notification failure break retry logic

                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"Tool '{tool_name}' failed after {max_retries} attempts: {error_msg}"
                )

        return last_result

    async def execute_tool_and_wait(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0, ui_websocket=None) -> Optional[MCPResponse]:
        """Send an MCP tool call to an agent and wait for the response.

        Strategy: Always try WebSocket first (fastest, bidirectional), then
        fall back to A2A JSON-RPC if WebSocket is unavailable or fails.

        Feature 014: every tool call is recorded as a persistent step entry
        via :class:`orchestrator.chat_steps.ChatStepRecorder` so users see
        what was called in the chat. Recording is purely observational —
        a missing recorder (e.g. no UI websocket) is not an error.
        """
        # Feature 014: look up the active per-turn recorder for this UI
        # websocket so we can stamp start/complete/error around the call.
        recorder = self._chat_recorders.get(id(ui_websocket)) if ui_websocket is not None else None
        step_id = None
        if recorder is not None:
            try:
                step_id = await recorder.start("tool_call", tool_name, args)
            except Exception:  # pragma: no cover — defensive
                logger.debug("recorder.start failed", exc_info=True)
                step_id = None

        try:
            result = await self._dispatch_tool_call(agent_id, tool_name, args, timeout, ui_websocket)
            if recorder is not None and step_id is not None:
                # R6: if the step was cancelled mid-flight, drop the result
                # silently so the assistant reply does not include it.
                if recorder.is_terminal(step_id):
                    logger.info(
                        "tool_call result discarded (step terminal)",
                        extra={"step_id": step_id, "tool_name": tool_name},
                    )
                else:
                    if result is not None and result.error:
                        await recorder.error(step_id, result.error.get("message", "tool error"))
                    else:
                        # Surface a small result preview if present.
                        preview = result.result if (result is not None and result.result is not None) else None
                        await recorder.complete(step_id, preview)
            return result
        except Exception as exc:
            if recorder is not None and step_id is not None and not recorder.is_terminal(step_id):
                try:
                    await recorder.error(step_id, exc)
                except Exception:  # pragma: no cover — defensive
                    pass
            raise

    async def _dispatch_tool_call(self, agent_id: str, tool_name: str, args: Dict, timeout: float, ui_websocket) -> Optional[MCPResponse]:
        """Internal: actually dispatch the tool call (WebSocket → A2A fallback)."""
        # Try WebSocket first
        if agent_id in self.agents:
            result = await self._execute_via_websocket(agent_id, tool_name, args, timeout, ui_websocket=ui_websocket)
            if result and not (result.error and result.error.get("retryable")):
                return result
            # WebSocket failed with a retryable error — fall back to A2A if available
            if agent_id in self.a2a_clients:
                logger.info(f"WebSocket call failed for {agent_id}, falling back to A2A")
                return await self._execute_via_a2a(agent_id, tool_name, args, timeout)
            return result

        # No WebSocket connection — try A2A
        if agent_id in self.a2a_clients:
            return await self._execute_via_a2a(agent_id, tool_name, args, timeout)

        # Agent has a known URL but no active connection — attempt WebSocket reconnect then A2A
        if agent_id in self.agent_urls:
            base_url = self.agent_urls[agent_id]
            logger.info(f"Agent {agent_id} disconnected, attempting WebSocket reconnect to {base_url}")
            try:
                await self.discover_agent(base_url)
                if agent_id in self.agents:
                    return await self._execute_via_websocket(agent_id, tool_name, args, timeout, ui_websocket=ui_websocket)
            except Exception as e:
                logger.debug(f"WebSocket reconnect failed for {agent_id}: {e}")

            # WebSocket reconnect failed — try A2A discovery as fallback
            logger.info(f"WebSocket reconnect failed for {agent_id}, attempting A2A fallback")
            try:
                await self.discover_a2a_agent(base_url, notify_ui=False)
                if agent_id in self.a2a_clients:
                    return await self._execute_via_a2a(agent_id, tool_name, args, timeout)
            except Exception as e:
                logger.debug(f"A2A fallback discovery failed for {agent_id}: {e}")

        return MCPResponse(
            request_id=f"req_{tool_name}_{int(time.time() * 1000)}",
            error={"message": f"Agent {agent_id} not connected via WebSocket or A2A", "retryable": False},
        )

    async def _execute_via_websocket(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0, ui_websocket=None) -> Optional[MCPResponse]:
        """Execute a tool call via WebSocket (internal agents)."""
        request_id = f"req_{tool_name}_{int(time.time() * 1000)}"

        request = MCPRequest(
            request_id=request_id,
            method="tools/call",
            params={"name": tool_name, "arguments": args}
        )

        # Create a future for the response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        # Register UI socket for progress forwarding
        if ui_websocket and flags.is_enabled("progress_streaming"):
            self.pending_ui_sockets[request_id] = ui_websocket

        try:
            agent_ws = self.agents[agent_id]
            await agent_ws.send(request.to_json())
            logger.info(f"Sent tool call (WS): {tool_name} → {agent_id}")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.error(f"Tool call timed out: {tool_name}")
            return MCPResponse(request_id=request_id,
                               error={"message": "Tool call timed out", "retryable": True})
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return MCPResponse(request_id=request_id,
                               error={"message": str(e), "retryable": True})
        finally:
            self.pending_requests.pop(request_id, None)
            self.pending_ui_sockets.pop(request_id, None)

    async def _execute_via_a2a(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0) -> Optional[MCPResponse]:
        """Execute a tool call via A2A JSON-RPC (external agents).

        Posts a hand-rolled JSON-RPC `message/send` request to the agent's /a2a
        endpoint so the per-call delegation token can be forwarded as a Bearer
        Authorization header. Avoids the v1.0 SDK Client which routes auth
        through interceptors rather than per-call metadata.
        """
        import uuid
        import httpx
        from google.protobuf.json_format import ParseDict, MessageToDict
        from a2a.types import Message as A2AMessage, Role, Task, Message as A2AMsg
        from shared.a2a_bridge import make_data_part, a2a_response_to_mcp_response

        request_id = f"a2a_{tool_name}_{int(time.time() * 1000)}"

        base_url = self.a2a_clients.get(agent_id) or self.agent_urls.get(agent_id)
        if not base_url:
            return MCPResponse(
                request_id=request_id,
                error={"message": f"No A2A endpoint registered for {agent_id}", "retryable": False},
            )
        a2a_url = base_url if base_url.rstrip("/").endswith("/a2a") else f"{base_url.rstrip('/')}/a2a"

        clean_args = {k: v for k, v in args.items() if not k.startswith("_")}
        if args.get("_credentials_encrypted"):
            clean_args["_credentials"] = args["_credentials"]
            clean_args["_credentials_encrypted"] = args["_credentials_encrypted"]

        msg = A2AMessage(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[make_data_part({
                "method": "tools/call",
                "name": tool_name,
                "arguments": clean_args,
            })],
        )

        headers = {"Content-Type": "application/json"}
        delegation_token = args.get("_delegation_token")
        if delegation_token:
            headers["Authorization"] = f"Bearer {delegation_token}"

        jsonrpc_payload = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": request_id,
            "params": {"message": MessageToDict(msg, preserving_proto_field_name=True)},
        }

        try:
            logger.info(f"Sent tool call (A2A): {tool_name} → {agent_id}")
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(a2a_url, json=jsonrpc_payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if "error" in data:
                err = data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
                return MCPResponse(
                    request_id=request_id,
                    error={"message": err.get("message", "A2A error"), "retryable": False},
                )

            result = data.get("result")
            if isinstance(result, dict):
                # Try to parse the result as a Task; fall back to Message; else raw dict.
                try:
                    return a2a_response_to_mcp_response(ParseDict(result, Task()), request_id)
                except Exception:
                    pass
                try:
                    return a2a_response_to_mcp_response(ParseDict(result, A2AMsg()), request_id)
                except Exception:
                    pass
                return MCPResponse(request_id=request_id, result=result)

            if result is None:
                return MCPResponse(
                    request_id=request_id,
                    error={"message": "No response from A2A agent", "retryable": True},
                )
            return MCPResponse(request_id=request_id, result=str(result))

        except httpx.TimeoutException:
            logger.error(f"A2A tool call timed out: {tool_name}")
            return MCPResponse(request_id=request_id,
                               error={"message": "A2A tool call timed out", "retryable": True})
        except Exception as e:
            logger.error(f"A2A tool execution error: {e}")
            return MCPResponse(request_id=request_id,
                               error={"message": str(e), "retryable": True})

    async def _get_delegation_token(self, websocket, agent_id: str, user_id: str) -> Optional[str]:
        """Generate an RFC 8693 delegation token scoped to safe, allowed tools.

        The scope excludes system-blocked tools (from security review) and
        user-disabled tools (from permission manager), so the agent can only
        act within the constrained tool set.
        """
        try:
            card = self.agent_cards.get(agent_id)
            if not card:
                return None
            session = self.ui_sessions.get(websocket, {})
            raw_token = session.get("_raw_token")
            if not raw_token:
                return None

            # Build the effective scope: only tools that pass BOTH checks
            agent_flags = self.security_flags.get(agent_id, {})
            allowed_tools = []
            for skill in card.skills:
                # Exclude system-blocked
                if skill.id in agent_flags and agent_flags[skill.id].get("blocked"):
                    continue
                # Exclude user-disabled
                if not self.tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
                    continue
                allowed_tools.append(skill.id)

            # Get enabled scope names for the delegation token
            enabled_scopes = self.tool_permissions.get_enabled_scope_names(user_id, agent_id)

            result = await self.delegation.exchange_token_for_agent(
                raw_token, agent_id, allowed_tools, user_id, enabled_scopes
            )
            if "error" in result:
                logger.warning(f"Delegation token exchange failed for agent={agent_id}: {result}")
                return None
            return result.get("access_token")
        except Exception as e:
            logger.warning(f"Delegation token generation failed: {e}")
            return None

    # =========================================================================
    # LIVE STREAMING SUBSCRIPTIONS
    # =========================================================================

    # =========================================================================
    # PUSH STREAMING (001-tool-stream-ui)
    # =========================================================================

    def _validate_chat_ownership_for_stream(
        self, websocket, user_id: str, chat_id: str,
    ) -> bool:
        """Callback used by StreamManager to verify that ``chat_id`` belongs
        to ``user_id``. Reuses the existing history.get_chat ownership
        check that all other chat-scoped operations go through.
        Returns True if the chat exists AND is owned by the user.
        """
        try:
            chat = self.history.get_chat(chat_id, user_id=user_id)
            return chat is not None
        except Exception as e:
            logger.warning(f"chat ownership check failed: {e}")
            return False

    async def _dispatch_stream_request(
        self,
        agent_id: str,
        tool_name: str,
        args: Dict[str, Any],
        stream_id: str,
        user_id: Optional[str],
    ) -> str:
        """Dispatch a streaming tool call to an agent. Returns the
        ``request_id`` so StreamManager can populate ``_request_to_key``.

        Unlike ``_execute_via_websocket`` (the synchronous response path),
        this fire-and-forgets the request. The chunks arrive asynchronously
        as ``ToolStreamData`` messages and are routed back via
        ``handle_agent_message`` → ``stream_manager.handle_agent_chunk``.

        Per RFC 8693 (constitution VII), if user credentials are stored for
        this user/agent pair we inject them encrypted alongside the args
        before sending — exactly like the polling path.
        """
        if agent_id not in self.agents:
            raise RuntimeError(f"agent {agent_id!r} is not connected")

        request_id = f"stream_{tool_name}_{int(time.time() * 1000)}_{stream_id[-6:]}"

        # Inject per-user credentials (E2E encrypted — only the agent can decrypt)
        full_args = dict(args)
        if user_id and agent_id:
            try:
                creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
                if creds:
                    full_args["_credentials"] = creds
                    full_args["_credentials_encrypted"] = True
            except Exception as e:
                logger.debug(f"credential injection skipped for {agent_id}: {e}")

        request = MCPRequest(
            request_id=request_id,
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": full_args,
                "_stream": True,
                "_stream_id": stream_id,
            },
        )
        agent_ws = self.agents[agent_id]
        await agent_ws.send(request.to_json())
        logger.info(
            f"Dispatched streaming tool call: {tool_name} → {agent_id} "
            f"(stream_id={stream_id}, request_id={request_id})"
        )
        return request_id

    async def _cancel_stream_request(
        self, agent_id: str, request_id: str, stream_id: str,
    ) -> None:
        """Send a ``ToolStreamCancel`` to the agent for an in-flight stream.
        The agent's BaseA2AAgent loop closes the underlying generator and
        sends a final ``ToolStreamData`` with ``terminal: true``.
        """
        if agent_id not in self.agents:
            logger.debug(
                f"_cancel_stream_request: agent {agent_id} not connected, "
                f"nothing to cancel"
            )
            return
        cancel_msg = ToolStreamCancel(request_id=request_id, stream_id=stream_id)
        try:
            await self.agents[agent_id].send(cancel_msg.to_json())
            logger.info(
                f"Sent ToolStreamCancel: stream_id={stream_id} → {agent_id}"
            )
        except Exception as e:
            logger.warning(f"_cancel_stream_request failed: {e}")

    async def _handle_push_stream_subscribe(
        self, websocket, session_id: Optional[str], payload: Dict, user_id: str
    ) -> None:
        """Handle a stream_subscribe action for a PUSH-streaming tool.

        Delegates to ``self.stream_manager.subscribe(...)``. Translates
        ``ValueError`` into a ``stream_error`` reply per
        contracts/protocol-messages.md §A6. On success replies with
        ``stream_subscribed``.

        US1 implementation: subscribe() actually creates a subscription and
        the agent dispatcher fires the request. agent_id is looked up from
        the orchestrator's _streamable_tools registry so the client doesn't
        need to know it (mirrors the legacy poll path).
        """
        tool_name = payload.get("tool_name", "")
        params = payload.get("params", {})
        chat_id = session_id or ""

        if not tool_name or not chat_id:
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error",
                "request_action": "stream_subscribe",
                "session_id": session_id,
                "payload": {
                    "tool_name": tool_name,
                    "code": "params_invalid",
                    "message": "tool_name and session_id are required",
                },
            }))
            return

        tool_cfg = self._streamable_tools.get(tool_name)
        if tool_cfg is None or tool_cfg.get("kind") != "push":
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error",
                "request_action": "stream_subscribe",
                "session_id": session_id,
                "payload": {
                    "tool_name": tool_name,
                    "code": "not_streamable",
                    "message": f"tool {tool_name!r} is not push-streamable",
                },
            }))
            return

        agent_id = tool_cfg["agent_id"]

        # Permission check (mirrors legacy poll path)
        if not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error",
                "request_action": "stream_subscribe",
                "session_id": session_id,
                "payload": {
                    "tool_name": tool_name,
                    "code": "unauthorized",
                    "message": "permission denied for this tool",
                },
            }))
            return

        try:
            stream_id, attached = await self.stream_manager.subscribe(
                ws=websocket,
                user_id=user_id,
                chat_id=chat_id,
                tool_name=tool_name,
                agent_id=agent_id,
                params=params,
                tool_metadata=tool_cfg,
            )
        except ValueError as e:
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error",
                "request_action": "stream_subscribe",
                "session_id": session_id,
                "payload": {
                    "tool_name": tool_name,
                    "code": "params_invalid",
                    "message": str(e),
                },
            }))
            return

        # Success — reply with stream_subscribed including the FPS bounds and
        # the FR-009a `attached` flag so the client knows whether this was a
        # fresh subscribe or an attach to an existing deduplicated stream.
        cfg = self._streamable_tools.get(tool_name, {})
        await self._safe_send(websocket, json.dumps({
            "type": "stream_subscribed",
            "stream_id": stream_id,
            "tool_name": tool_name,
            "agent_id": agent_id,
            "session_id": session_id,
            "max_fps": cfg.get("max_fps", 30),
            "min_fps": cfg.get("min_fps", 5),
            "attached": attached,
        }))

    async def _handle_push_stream_unsubscribe(
        self, websocket, session_id: Optional[str], payload: Dict, user_id: str
    ) -> None:
        """Handle a stream_unsubscribe for a push-streamed subscription.

        Per FR-009a per-subscriber semantics, removing this websocket from
        the subscription's ``subscribers`` list does NOT necessarily stop
        the stream — only when the list becomes empty does the stream
        transition to STOPPED. The actual logic is in
        ``StreamManager.unsubscribe`` (US4 T066).
        """
        stream_id = payload.get("stream_id", "")
        if not stream_id:
            return  # silent: malformed unsubscribe is not worth a reply
        try:
            await self.stream_manager.unsubscribe(websocket, stream_id)
        except NotImplementedError:
            logger.debug(
                f"push stream_unsubscribe received but unsubscribe() not yet "
                f"implemented (stream_id={stream_id})"
            )
        except ValueError as e:
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error",
                "request_action": "stream_unsubscribe",
                "session_id": session_id,
                "payload": {
                    "stream_id": stream_id,
                    "code": "unauthorized",
                    "message": str(e),
                },
            }))

    async def _handle_stream_subscribe(self, websocket, payload: Dict):
        """Subscribe a UI client to a live-streaming tool."""
        tool_name = payload.get("tool_name")
        interval = payload.get("interval_seconds")
        params = payload.get("params", {})

        if not tool_name or tool_name not in self._streamable_tools:
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error", "tool_name": tool_name or "",
                "error": f"Tool '{tool_name}' is not available for streaming"
            }))
            return

        tool_cfg = self._streamable_tools[tool_name]
        agent_id = tool_cfg["agent_id"]

        # Permission check
        user_id = self._get_user_id(websocket)
        if not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error", "tool_name": tool_name,
                "error": "Permission denied for this tool"
            }))
            return

        # Clamp interval to tool's allowed range
        if interval is None:
            interval = tool_cfg["default_interval"]
        interval = max(tool_cfg["min_interval"], min(tool_cfg["max_interval"], interval))

        ws_id = id(websocket)

        # Enforce max subscription limit
        current_subs = self._stream_subs.get(ws_id, {})
        if tool_name not in current_subs and len(current_subs) >= self._MAX_STREAM_SUBSCRIPTIONS:
            await self._safe_send(websocket, json.dumps({
                "type": "stream_error", "tool_name": tool_name,
                "error": f"Maximum {self._MAX_STREAM_SUBSCRIPTIONS} concurrent streams exceeded"
            }))
            return

        # Cancel existing task for this tool if re-subscribing
        existing_task = self._stream_tasks.get(ws_id, {}).get(tool_name)
        if existing_task:
            existing_task.cancel()

        # Store subscription config
        self._stream_subs.setdefault(ws_id, {})[tool_name] = {
            "interval": interval, "params": params, "agent_id": agent_id,
        }

        # Create streaming task
        task = asyncio.create_task(
            self._stream_loop(websocket, tool_name, agent_id, interval, params)
        )
        self._stream_tasks.setdefault(ws_id, {})[tool_name] = task

        await self._safe_send(websocket, json.dumps({
            "type": "stream_subscribed", "tool_name": tool_name,
            "interval_seconds": interval,
        }))
        logger.info(f"Stream subscribed: user={user_id} tool={tool_name} interval={interval}s")

    async def _handle_stream_unsubscribe(self, websocket, payload: Dict):
        """Unsubscribe a UI client from a live-streaming tool."""
        tool_name = payload.get("tool_name")
        ws_id = id(websocket)

        task = self._stream_tasks.get(ws_id, {}).pop(tool_name, None)
        if task:
            task.cancel()
        self._stream_subs.get(ws_id, {}).pop(tool_name, None)

        await self._safe_send(websocket, json.dumps({
            "type": "stream_unsubscribed", "tool_name": tool_name,
        }))
        logger.info(f"Stream unsubscribed: tool={tool_name}")

    async def _handle_stream_list(self, websocket):
        """Return the list of active stream subscriptions for this client."""
        ws_id = id(websocket)
        subs = self._stream_subs.get(ws_id, {})
        items = [
            {"tool_name": name, "interval_seconds": cfg["interval"], "agent_id": cfg["agent_id"]}
            for name, cfg in subs.items()
        ]
        await self._safe_send(websocket, json.dumps({
            "type": "stream_list", "subscriptions": items,
        }))

    async def _stream_loop(self, websocket, tool_name: str, agent_id: str, interval: float, params: Dict):
        """Core streaming loop — periodically executes a tool and pushes results to the UI client."""
        user_id = self._get_user_id(websocket)
        while True:
            try:
                # Re-check permission each iteration (user may revoke mid-stream)
                if not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
                    await self._safe_send(websocket, json.dumps({
                        "type": "stream_error", "tool_name": tool_name,
                        "error": "Permission revoked"
                    }))
                    break

                # Execute tool via existing agent WebSocket channel
                result = await self._execute_via_websocket(agent_id, tool_name, dict(params), timeout=interval + 5)

                if result and not result.error:
                    # Tag components with source metadata (same as regular tool flow)
                    # Feature 004: also tag with correlation_id when available
                    # so streamed components are linkable to their dispatch.
                    stream_corr_id = getattr(result, "correlation_id", None)

                    def _tag(comp):
                        if not isinstance(comp, dict):
                            return
                        comp["_source_agent"] = agent_id
                        comp["_source_tool"] = tool_name
                        if stream_corr_id is not None:
                            comp["_source_correlation_id"] = stream_corr_id
                        for key in ("content", "children"):
                            nested = comp.get(key)
                            if isinstance(nested, list):
                                for child in nested:
                                    _tag(child)

                    tagged_components = list(result.ui_components or [])
                    for comp in tagged_components:
                        _tag(comp)
                    await self._safe_send(websocket, json.dumps({
                        "type": "stream_data",
                        "tool_name": tool_name,
                        "agent_id": agent_id,
                        "timestamp": time.time(),
                        "components": tagged_components,
                        "data": result.result or {},
                    }))
                elif result and result.error:
                    logger.warning(f"Stream tool error ({tool_name}): {result.error}")
                    # Don't break on transient errors; continue loop

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream loop error for {tool_name}: {e}")
                await asyncio.sleep(interval)

        # Cleanup on exit
        ws_id = id(websocket)
        self._stream_tasks.get(ws_id, {}).pop(tool_name, None)
        self._stream_subs.get(ws_id, {}).pop(tool_name, None)

    def _cleanup_streams(self, websocket):
        """Cancel all streaming tasks for a disconnected websocket."""
        ws_id = id(websocket)
        for tool_name, task in self._stream_tasks.pop(ws_id, {}).items():
            task.cancel()
        self._stream_subs.pop(ws_id, None)

    # =========================================================================
    # UI HELPERS
    # =========================================================================

    async def _safe_send(self, websocket, data: str) -> bool:
        """Send data over a websocket, returning False if the connection is closed."""
        try:
            if hasattr(websocket, "send_text"):
                # FastAPI WebSocket
                await websocket.send_text(data)
            else:
                # websockets library WebSocket
                await websocket.send(data)
            return True
        except Exception as e:
            logger.debug(f"Failed to send message (connection likely closed): {e}")
            return False

    async def _broadcast_user_history(self):
        """Send each connected UI client their own user's recent chat history.

        Groups clients by user_id to avoid redundant DB queries when the
        same user has multiple tabs open.
        """
        if not self.ui_clients:
            return

        clients_by_user: Dict[str, list] = {}
        for client in self.ui_clients:
            uid = self._get_user_id(client)
            clients_by_user.setdefault(uid, []).append(client)

        tasks = []
        for uid, clients in clients_by_user.items():
            history_list = self.history.get_recent_chats(user_id=uid)
            msg = json.dumps({"type": "history_list", "chats": history_list})
            for c in clients:
                tasks.append(self._safe_send(c, msg))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_or_replace_components(self, websocket, components: List[Dict], chat_id: str, user_id: str):
        """Send components to canvas, auto-replacing existing ones from the same source tool.

        Components whose (_source_tool, _source_agent) match a saved canvas
        component are treated as updates — the old component is replaced in the
        DB and the frontend receives a 'components_replaced' message so it can
        swap in-place. Unmatched components flow through the normal ui_render
        path (frontend auto-saves them as new).
        """
        if not components:
            return

        replacement_ids = []
        replacement_comps = []
        new_only = []

        if chat_id:
            existing = self.history.get_saved_components(chat_id, user_id=user_id)
            # Build lookup: (source_tool, source_agent) -> [component_ids] (most recent first)
            existing_by_source: Dict[tuple, List[str]] = {}
            for ec in existing:
                cd = ec.get("component_data", {})
                key = (cd.get("_source_tool", ""), cd.get("_source_agent", ""))
                if key != ("", ""):
                    existing_by_source.setdefault(key, []).append(ec["id"])

            for comp in components:
                key = (comp.get("_source_tool", ""), comp.get("_source_agent", ""))
                matching_ids = existing_by_source.get(key, [])
                if matching_ids:
                    old_id = matching_ids.pop(0)
                    replacement_ids.append(old_id)
                    replacement_comps.append(comp)
                else:
                    new_only.append(comp)
        else:
            new_only = list(components)

        # Replace matched components via existing replace_components infra
        if replacement_ids:
            new_comp_dicts = [
                {
                    "component_data": comp,
                    "component_type": comp.get("type", "unknown"),
                    "title": comp.get("title", comp.get("type", "Component")),
                }
                for comp in replacement_comps
            ]
            replaced = self.history.replace_components(
                replacement_ids, new_comp_dicts, chat_id, user_id=user_id
            )
            await self._safe_send(websocket, json.dumps({
                "type": "components_replaced",
                "removed_ids": replacement_ids,
                "new_components": replaced,
            }))

        # Send truly new components through normal ui_render flow
        if new_only:
            await self.send_ui_render(websocket, new_only)

    async def send_ui_render(self, websocket, components: List, target: str = "canvas"):
        """Send a UIRender message to a UI client, adapted via ROTE."""
        # Auto-route error-only messages to the chat panel instead of the canvas
        if target == "canvas" and components and all(
            isinstance(c, dict) and c.get("type") == "alert" and c.get("variant") == "error"
            for c in components
        ):
            target = "chat"
        adapted = self.rote.adapt(websocket, components)
        msg = UIRender(components=adapted, target=target)
        await self._safe_send(websocket, msg.to_json())

    @staticmethod
    def _sanitize_tool_schema(schema: dict) -> dict:
        """Fix common agent-generated schema issues before sending to the LLM.

        Addresses: property-level "required": true/false (invalid in OpenAI tool
        schemas) — must be an array at the object level instead.
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        schema = dict(schema)  # shallow copy
        props = schema.get("properties")
        if isinstance(props, dict):
            required_fields = list(schema.get("required", []) if isinstance(schema.get("required"), list) else [])
            cleaned_props = {}
            for key, val in props.items():
                if isinstance(val, dict):
                    val = dict(val)  # shallow copy
                    prop_req = val.pop("required", None)
                    # If a property had "required": true, promote to object-level required array
                    if prop_req is True and key not in required_fields:
                        required_fields.append(key)
                    # Recurse for nested object properties
                    if val.get("type") == "object" and "properties" in val:
                        val = Orchestrator._sanitize_tool_schema(val)
                    cleaned_props[key] = val
                else:
                    cleaned_props[key] = val
            schema["properties"] = cleaned_props
            if required_fields:
                schema["required"] = required_fields
            elif "required" in schema and not isinstance(schema["required"], list):
                del schema["required"]

        # Ensure top-level type
        if "type" not in schema:
            schema["type"] = "object"

        return schema

    def _is_draft_agent(self, agent_id: str) -> bool:
        """Hide any agent whose agent_id maps to a non-live draft record."""
        if hasattr(self, 'lifecycle_manager'):
            draft = self.lifecycle_manager._find_draft_by_agent_id(agent_id)
            if draft and draft["status"] != "live":
                return True
        return False

    async def send_dashboard(self, websocket):
        """Send the initial dashboard view."""
        user_id = self._get_user_id(websocket)
        ownership_map = {o["agent_id"]: o for o in self.history.db.get_all_agent_ownership()}
        agent_list = []
        for agent_id, card in self.agent_cards.items():
            # Hide draft agents that aren't live yet — they only appear in the Drafts tab
            if self._is_draft_agent(agent_id):
                continue
            available_tools = [s.id for s in card.skills]
            scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
            tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
            permissions = self.tool_permissions.get_effective_permissions(
                user_id, agent_id, available_tools
            )
            ownership = ownership_map.get(agent_id, {})
            entry = {
                "id": card.agent_id,
                "name": card.name,
                "description": card.description,
                "tools": available_tools,
                "tool_descriptions": {s.id: s.description for s in card.skills},
                "scopes": scopes,
                "tool_scope_map": tool_scope_map,
                "permissions": permissions,
                "security_flags": self.security_flags.get(agent_id, {}),
                "status": "connected",
                "owner_email": ownership.get("owner_email"),
                "is_public": bool(ownership.get("is_public", False)),
            }
            if getattr(card, 'metadata', None):
                entry["metadata"] = card.metadata
            agent_list.append(entry)

        # Calculate total available tools for this user based on permissions
        total_tools = 0
        for agent in agent_list:
            if "permissions" in agent:
                total_tools += sum(1 for v in agent["permissions"].values() if v)
            else:
                total_tools += len(agent["tools"])

        # Build streamable tools list for live streaming. Includes BOTH the
        # legacy poll path (gated by FF_LIVE_STREAMING) AND the new push path
        # (001-tool-stream-ui, gated by FF_TOOL_STREAMING). The frontend
        # uses the `kind` field to decide which subscribe payload to send.
        streamable_list: Dict[str, Dict[str, Any]] = {}
        live_enabled = flags.is_enabled("live_streaming")
        push_enabled = flags.is_enabled("tool_streaming")
        for tool_name, cfg in self._streamable_tools.items():
            kind = cfg.get("kind", "poll")
            if kind == "push" and not push_enabled:
                continue
            if kind == "poll" and not live_enabled:
                continue
            streamable_list[tool_name] = {
                "agent_id": cfg["agent_id"],
                "default_interval": cfg.get("default_interval", 5),
                "kind": kind,
            }

        await self._safe_send(websocket, json.dumps({
            "type": "system_config",
            "config": {
                "agents": agent_list,
                "total_tools": total_tools,
                "streamable_tools": streamable_list,
            }
        }))

    def compute_tools_available_for_user(
        self, user_id: str, draft_agent_id: Optional[str] = None
    ) -> bool:
        """Return ``True`` iff at least one tool is currently dispatchable for ``user_id``.

        Mirrors the per-turn filter loop in :meth:`handle_chat_message`
        (registered agent + system security_flags + per-user
        :meth:`tool_permissions.is_tool_allowed`). Used by feature 008
        for two purposes:

        1. The orchestrator decides whether the next chat turn enters
           the text-only branch (caller passes ``draft_agent_id`` so a
           draft test chat is scoped correctly per FR-010).
        2. :meth:`send_agent_list` broadcasts the result as
           ``tools_available_for_user`` so the frontend can mount the
           persistent text-only banner (FR-007a).

        Args:
            user_id: The user whose permissions gate tool availability.
            draft_agent_id: When set, only that agent's tools are
                considered (matches the dispatch-time draft scoping).
                When ``None``, every connected non-draft agent is
                considered.

        Returns:
            ``True`` if at least one tool would survive the full filter
            stack for ``user_id``. ``False`` otherwise — this is the
            signal that the chat turn would dispatch in text-only mode.
        """
        for agent_id, card in self.agent_cards.items():
            if agent_id not in self.agents:
                continue
            if draft_agent_id and agent_id != draft_agent_id:
                continue
            agent_flags = self.security_flags.get(agent_id, {})
            for skill in card.skills:
                if skill.id in agent_flags and agent_flags[skill.id].get("blocked"):
                    continue
                if not self.tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
                    continue
                return True
        return False

    async def send_agent_list(self, websocket):
        """Send list of connected agents."""
        user_id = self._get_user_id(websocket)
        ownership_map = {o["agent_id"]: o for o in self.history.db.get_all_agent_ownership()}
        agents = []
        for agent_id, card in self.agent_cards.items():
            # Hide draft agents that aren't live yet
            if self._is_draft_agent(agent_id):
                continue
            available_tools = [s.id for s in card.skills]
            scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
            tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
            permissions = self.tool_permissions.get_effective_permissions(
                user_id, agent_id, available_tools
            )
            ownership = ownership_map.get(agent_id, {})
            entry = {
                "id": card.agent_id,
                "name": card.name,
                "description": card.description,
                "tools": [{"name": s.id, "description": s.description} for s in card.skills],
                "scopes": scopes,
                "tool_scope_map": tool_scope_map,
                "permissions": permissions,
                "security_flags": self.security_flags.get(agent_id, {}),
                "status": "connected",
                "owner_email": ownership.get("owner_email"),
                "is_public": bool(ownership.get("is_public", False)),
            }
            if getattr(card, 'metadata', None):
                entry["metadata"] = card.metadata
            agents.append(entry)

        # Feature 008-llm-text-only-chat (FR-007a, contracts/ws-agent-list.md).
        # Broadcast a single boolean for this user that collapses the
        # three reasons a chat would dispatch in text-only mode (no
        # agents connected, all tools blocked by user permissions, all
        # blocked by security flags). The frontend uses this to toggle
        # the persistent text-only banner.
        tools_available_for_user = self.compute_tools_available_for_user(user_id)

        await self._safe_send(websocket, json.dumps({
            "type": "agent_list",
            "tools_available_for_user": tools_available_for_user,
            "agents": agents,
        }))

    # =========================================================================
    # SERVER
    # =========================================================================

    async def handle_ui_connection_fastapi(self, websocket: WebSocket):
        """Handle a UI client WebSocket connection using FastAPI."""
        await websocket.accept()
        self.ui_clients.append(websocket)
        self._registered_events[id(websocket)] = asyncio.Event()
        logger.info(f"UI client connected (total: {len(self.ui_clients)})")

        # Hook: SESSION_START
        if flags.is_enabled("hook_system"):
            await self.hooks.emit(HookContext(
                event=HookEvent.SESSION_START,
                metadata={"websocket_id": id(websocket)},
            ))

        try:
            while True:
                message = await websocket.receive_text()
                # Fire as task so the receive loop stays responsive —
                # long-running handlers (chat, condense, combine, paginate)
                # won't block button clicks or cancel_task messages.
                asyncio.create_task(self._safe_handle_ui_message(websocket, message))
        except WebSocketDisconnect:
            logger.info("UI client disconnected")
        except Exception as e:
            # Only log interesting errors
            if "ConnectionClosed" not in str(e):
                logger.error(f"WebSocket error: {e}")
        finally:
            # Hook: SESSION_END
            if flags.is_enabled("hook_system"):
                user_data = self.ui_sessions.get(websocket, {})
                await self.hooks.emit(HookContext(
                    event=HookEvent.SESSION_END,
                    user_id=user_data.get("user_id", ""),
                    metadata={"websocket_id": id(websocket)},
                ))

            # Audit: WebSocket logout / disconnect
            try:
                _claims = self.ui_sessions.get(websocket)
                if _claims:
                    from audit.hooks import record_auth_event
                    await record_auth_event(
                        claims=_claims,
                        action="ws_disconnect",
                        description="WebSocket session ended",
                    )
            except Exception as _e:
                logger.debug(f"WS disconnect audit record failed: {_e}")

            self._cleanup_streams(websocket)
            # 001-tool-stream-ui (US2 T043): pause any push streams owned by
            # this websocket. They transition to DORMANT and become eligible
            # for resume on the user's return (US3).
            if self.stream_manager is not None:
                try:
                    await self.stream_manager.detach(websocket)
                except Exception as e:
                    logger.warning(f"stream_manager.detach failed: {e}")
            self._ws_active_chat.pop(id(websocket), None)
            if websocket in self.ui_clients:
                self.ui_clients.remove(websocket)
            if websocket in self.ui_sessions:
                del self.ui_sessions[websocket]
            self._chat_locks.pop(id(websocket), None)
            self._registered_events.pop(id(websocket), None)
            # Feature 006: clear per-WebSocket LLM credentials (in-memory only;
            # never persisted server-side per FR-002).
            self._session_llm_creds.clear(id(websocket))
            self.rote.cleanup(websocket)
            logger.info(f"UI client session cleaned up (total: {len(self.ui_clients)})")

    async def handle_ui_connection(self, websocket, path=None):
        """Handle a UI client WebSocket connection (legacy websockets lib)."""
        self.ui_clients.append(websocket)
        self._registered_events[id(websocket)] = asyncio.Event()
        logger.info(f"UI client connected (total: {len(self.ui_clients)})")
        try:
            async for message in websocket:
                asyncio.create_task(self._safe_handle_ui_message(websocket, message))
        except websockets.exceptions.ConnectionClosed:
            logger.info("UI client disconnected")
        finally:
            self._cleanup_streams(websocket)
            # 001-tool-stream-ui (US2 T043): same detach for the legacy path.
            if self.stream_manager is not None:
                try:
                    await self.stream_manager.detach(websocket)
                except Exception as e:
                    logger.warning(f"stream_manager.detach failed: {e}")
            self._ws_active_chat.pop(id(websocket), None)
            if websocket in self.ui_clients:
                self.ui_clients.remove(websocket)
            if websocket in self.ui_sessions:
                del self.ui_sessions[websocket]
            self._chat_locks.pop(id(websocket), None)
            self._registered_events.pop(id(websocket), None)
            # Feature 006: clear per-WebSocket LLM credentials (in-memory only;
            # never persisted server-side per FR-002).
            self._session_llm_creds.clear(id(websocket))
            self.rote.cleanup(websocket)
            logger.info(f"UI client session cleaned up (total: {len(self.ui_clients)})")

    async def start(self):
        logger.info(f"Orchestrator starting on port {PORT}")

        # Auto-discover agents (continuous monitor)
        agent_port = int(os.getenv("AGENT_PORT", 8003))
        max_agents = int(os.getenv("MAX_AGENTS", 10))
        asyncio.create_task(self._monitor_agents(agent_port, max_agents))

        # Start knowledge synthesis background loop
        if flags.is_enabled("knowledge_synthesis") and hasattr(self, '_knowledge_synthesizer'):
            asyncio.create_task(self._knowledge_synthesizer.run_loop())

        # Feature 004 — daily quality-signal job + proposal generation
        async def _feedback_quality_loop():
            from feedback.quality import compute_for_window
            from feedback.proposals import generate_for_underperforming
            interval_seconds = int(os.getenv("FEEDBACK_QUALITY_JOB_INTERVAL", str(24 * 3600)))
            # First run after a short warm-up so a freshly-restarted server
            # produces an initial snapshot quickly without colliding with startup.
            await asyncio.sleep(int(os.getenv("FEEDBACK_QUALITY_JOB_WARMUP", "60")))
            while True:
                try:
                    await compute_for_window(self.feedback_repo)
                    refine = None
                    if flags.is_enabled("knowledge_synthesis") and getattr(self, "_knowledge_synthesizer", None):
                        refine = getattr(self._knowledge_synthesizer, "refine_proposal", None)
                    await generate_for_underperforming(self.feedback_repo, refine_with_llm=refine)
                except Exception as exc:
                    logger.warning("feedback quality loop iteration failed: %s", exc)
                await asyncio.sleep(interval_seconds)

        asyncio.create_task(_feedback_quality_loop())

        # Import WebSocket protocol docs for OpenAPI description
        from orchestrator.models import WS_PROTOCOL_DOCS

        # OpenAPI tag metadata for grouping endpoints in /docs
        tags_metadata = [
            {"name": "Chat", "description": "Chat session management — create, list, load, delete chats and send messages."},
            {"name": "Components", "description": "Saved UI component management — save, list, delete, combine, and condense components."},
            {"name": "Agents", "description": "Connected agent discovery and information."},
            {"name": "System", "description": "System dashboard and configuration."},
            {"name": "Auth", "description": "Authentication token proxy (Keycloak BFF)."},
            {"name": "Files", "description": "File upload and download."},
            {"name": "Audit", "description": "Per-user audit log (HIPAA + NIST AU). Read-only; admin-blind."},
        ]

        # Create FastAPI app with rich OpenAPI documentation
        app = FastAPI(
            title="AstralBody Orchestrator API",
            description=(
                "REST API and WebSocket gateway for the AstralBody multi-agent system.\n\n"
                "## Overview\n\n"
                "The orchestrator provides two communication channels:\n\n"
                "1. **REST API** (documented below) — Request/response endpoints for CRUD operations\n"
                "2. **WebSocket** (`ws://<host>:<port>/ws`) — Real-time streaming for chat responses and live updates\n\n"
                "Both channels share the same authentication (Keycloak JWT Bearer tokens).\n\n"
                "---\n"
                + WS_PROTOCOL_DOCS
            ),
            version="1.0.0",
            openapi_tags=tags_metadata,
            docs_url="/api/docs",
            redoc_url=None,
            openapi_url="/api/openapi.json",
        )

        # CORS — configurable via CORS_ORIGINS env var (comma-separated)
        cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Store Orchestrator instance on app.state so REST API routes can access it
        app.state.orchestrator = self

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_ui_connection_fastapi(websocket)

        # Mount REST API routers
        from orchestrator.api import chat_router, component_router, agent_router, dashboard_router, draft_router, voice_router, task_router, user_router
        from orchestrator.auth import auth_router
        from orchestrator.attachments.router import attachments_router
        from audit.api import audit_router
        from audit.middleware import AuditHTTPMiddleware
        from feedback.api import feedback_user_router, feedback_admin_router
        from onboarding.api import onboarding_user_router, onboarding_admin_router
        from llm_config.api import llm_router  # Feature 006-user-llm-config
        app.include_router(chat_router)
        app.include_router(component_router)
        app.include_router(agent_router)
        app.include_router(user_router)  # Feature 013 — tool-selection prefs
        app.include_router(draft_router)
        app.include_router(dashboard_router)
        app.include_router(auth_router)
        app.include_router(attachments_router)
        app.include_router(voice_router)
        app.include_router(task_router)
        app.include_router(audit_router)
        # Feature 004 — component feedback & tool-improvement loop
        app.include_router(feedback_user_router)
        app.include_router(feedback_admin_router)
        # Feature 005 — tool tips and getting started tutorial
        app.include_router(onboarding_user_router)
        app.include_router(onboarding_admin_router)
        # Feature 006 — user-configurable LLM subscription (Test Connection)
        app.include_router(llm_router)

        # Audit HTTP middleware — records every authenticated REST request
        # in the caller's own log (FR-021). Added after CORS so OPTIONS
        # preflights are short-circuited before reaching the recorder.
        app.add_middleware(AuditHTTPMiddleware)

        # Mount A2A JSON-RPC server (orchestrator as A2A agent)
        try:
            from orchestrator.a2a_orchestrator_executor import setup_orchestrator_a2a
            setup_orchestrator_a2a(app, self)
            logger.info(f"A2A JSON-RPC endpoint mounted at /a2a/")
        except Exception as e:
            logger.warning(f"A2A server setup skipped: {e}")

        # Discover external A2A agents from env var
        external_agents = os.getenv("A2A_EXTERNAL_AGENTS", "")
        if external_agents:
            async def _discover_external():
                await asyncio.sleep(3)  # Wait for server to start
                for url in external_agents.split(","):
                    url = url.strip()
                    if url:
                        await self.discover_a2a_agent(url)
            asyncio.create_task(_discover_external())

        # Start combined server
        config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Consolidated server (Gateway) listening on http://0.0.0.0:{PORT}")
        logger.info(f"API docs available at http://localhost:{PORT}/docs")
        logger.info(f"A2A endpoint: http://localhost:{PORT}/a2a/")
        await server.serve()

    async def _monitor_agents(self, start_port: int, max_ports: int = 10):
        """Continuously monitor and discover agents across a range of ports."""
        logger.info(f"Starting agent monitor for ports {start_port} to {start_port + max_ports - 1}...")

        while True:
            for port in range(start_port, start_port + max_ports):
                agent_url = f"http://localhost:{port}"
                try:
                    # This will connect if not already connected
                    await self.discover_agent(agent_url)
                except Exception as e:
                    pass
            
            await asyncio.sleep(5)  # Check every 5 seconds

    async def summarize_chat_title(self, chat_id: str, message: str, user_id: str = 'legacy', websocket=None):
        """Generate a concise title for the chat using LLM.

        Feature 006: routes through the per-user / operator-default
        credential resolver. If the user has personal credentials
        configured, those are used; otherwise the operator default.
        ``LLMUnavailable`` (no credentials anywhere) returns silently —
        a missing chat title is non-fatal.
        """
        feature = "chat_title"
        actor_user_id, auth_principal = self._llm_audit_principals(websocket)
        try:
            client, source, resolved = self._resolve_llm_client_for(websocket)
        except self._LLMUnavailable:
            await self._record_llm_unconfigured(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
            )
            return

        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=resolved.model,
                messages=[
                    {"role": "system", "content": "Summarize the following user request into a concise 3-5 word title. Return ONLY the title, no quotes or other text."},
                    {"role": "user", "content": message}
                ],
                max_tokens=20
            )
            usage = getattr(response, "usage", None)
            total_tokens = getattr(usage, "total_tokens", None) if usage else None
            await self._record_llm_call(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
                credential_source=source,
                resolved=resolved,
                total_tokens=total_tokens,
                outcome="success",
            )
            if source == self._CredentialSource.USER and websocket is not None:
                await self._emit_llm_usage_report(
                    websocket, feature=feature, model=resolved.model,
                    usage=usage, outcome="success",
                )
            content = response.choices[0].message.content
            if not content:
                return
            title = content.strip().strip('"')

            # Update history and notify UI
            self.history.update_chat_title(chat_id, title, user_id=user_id)

            # Broadcast update (each user gets their own history)
            await self._broadcast_user_history()

        except Exception as e:
            logger.error(f"Failed to summarize chat title: {e}")
            await self._record_llm_call(
                self.audit_recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                feature=feature,
                credential_source=source,
                resolved=resolved,
                total_tokens=None,
                outcome="failure",
                upstream_error_class=self._classify_llm_upstream_error(e),
            )
            if source == self._CredentialSource.USER and websocket is not None:
                await self._emit_llm_usage_report(
                    websocket, feature=feature, model=resolved.model,
                    usage=None, outcome="failure",
                )

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    async def validate_token(self, token: str) -> Optional[Dict]:
        """Validate JWT token against KeyCloak."""
        if os.getenv("VITE_USE_MOCK_AUTH", "").lower() == "true":
            if token == "dev-token":
                logger.info("Mock Auth: Validated dev-token as test_user")
                return {
                    "sub": "test_user",
                    "preferred_username": "test_user",
                    "email": "test_user@local",
                    "realm_access": {"roles": ["admin", "user"]},
                    "resource_access": {"astral-frontend": {"roles": ["admin", "user"]}},
                }
            try:
                import base64
                parts = token.split('.')
                if len(parts) == 3:
                    payload_b64 = parts[1]
                    payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
                    payload_json = base64.b64decode(payload_b64).decode('utf-8')
                    return json.loads(payload_json)
            except Exception as e:
                logger.debug(f"Mock JWT decode failed, falling back to default test_user: {e}")
            logger.info("Mock Auth: Accepting token as test_user")
            return {
                "sub": "test_user",
                "preferred_username": "test_user",
                "email": "test_user@local",
                "realm_access": {"roles": ["admin", "user"]},
                "resource_access": {"astral-frontend": {"roles": ["admin", "user"]}},
            }

        try:
            authority = os.getenv("VITE_KEYCLOAK_AUTHORITY")
            expected_client = os.getenv("VITE_KEYCLOAK_CLIENT_ID")
            
            if not authority or not expected_client:
                logger.warning("Auth not configured (VITE_KEYCLOAK_AUTHORITY/CLIENT_ID missing)")
                return None

            # Fetch JWKS
            jwks_url = f"{authority}/protocol/openid-connect/certs"
            async with aiohttp.ClientSession() as session:
                async with session.get(jwks_url) as resp:
                    jwks = await resp.json()

            # Verify token — skip strict audience check since Keycloak
            # confidential clients set aud="account", not the client_id.
            # We validate azp (authorized party) instead.
            payload = jose_jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_at_hash": False}
            )

            # Verify authorized party matches our client
            azp = payload.get("azp")
            if azp and azp != expected_client:
                logger.warning(f"Token azp '{azp}' does not match expected client '{expected_client}'")
                return None

            # Extract Roles
            client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")
            roles = payload.get("realm_access", {}).get("roles", [])
            if "resource_access" in payload:
                if client_id in payload["resource_access"]:
                    client_roles = payload["resource_access"][client_id].get("roles", [])
                    roles.extend(client_roles)
                if "account" in payload["resource_access"]:
                    account_roles = payload["resource_access"]["account"].get("roles", [])
                    roles.extend(account_roles)
            
            logger.debug(f"Token validation: extracted roles {roles} from payload keys {list(payload.keys())}")
            
            if "admin" not in roles and "user" not in roles:
                logger.warning(f"Token unauthorized (Requires 'admin' or 'user' role). Found roles: {roles}")
                return None

            return payload
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None

    def _get_user_id(self, websocket) -> str:
        """Extract user_id from the UI session, default to 'legacy' if not authenticated."""
        if websocket not in self.ui_sessions:
            return 'legacy'
        user_data = self.ui_sessions[websocket]
        # user_data is the JWT payload, sub is the subject (user ID)
        return user_data.get('sub', 'legacy')

    def _save_user_profile(self, user_data: Dict) -> None:
        """Persist user profile from JWT claims to the database."""
        user_id = user_data.get("sub")
        if not user_id or user_id == "legacy":
            return
        try:
            # Extract roles from JWT claims
            roles = list(set(
                user_data.get("realm_access", {}).get("roles", []) +
                user_data.get("resource_access", {}).get(
                    os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend"), {}
                ).get("roles", [])
            ))
            self.history.db.upsert_user(
                user_id=user_id,
                email=user_data.get("email"),
                username=user_data.get("preferred_username"),
                display_name=user_data.get("name") or user_data.get("preferred_username"),
                roles=roles,
            )
        except Exception as e:
            logger.warning(f"Failed to save user profile for {user_id}: {e}")


if __name__ == "__main__":
    orch = Orchestrator()
    asyncio.run(orch.start())
