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
from enum import Enum
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

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
from orchestrator import context_engineering
from orchestrator import datamarking
from orchestrator import model_router
from orchestrator.hooks import HookManager, HookEvent, HookContext
from orchestrator.task_state import TaskManager, TaskState
from orchestrator.concurrency_cap import ConcurrencyCap

import uuid as _uuid

from shared.protocol import (
    Message, MCPRequest, MCPResponse, UIEvent, UIRender, UIUpdate,
    RegisterAgent, RegisterUI, AgentCard, ToolProgress,
    ToolStreamData, ToolStreamEnd, ToolStreamCancel,
    validate_streaming_metadata,
)
from astralprims import (
    Text, Card, Alert, Button, Collapsible
)
from rote.rote import ROTE
from shared.feature_flags import flags
from shared.llm_text import strip_reasoning_markup
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
        # Filter out uvicorn access logs for "poll" endpoints and the
        # container/orchestrator health probes (they fire every few seconds).
        msg = record.getMessage()
        return not any(path in msg for path in (
            "/.well-known/agent-card.json", "/healthz", "/readyz",
        ))

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
- When the user asks about recent literature, current events, news, prices, or
  anything time-sensitive: state clearly that NO live sources were retrieved and
  that your answer is general background from training data. Do NOT present
  specific dated findings, statistics, or "last N years" claims as if they were
  retrieved results, and do NOT enumerate citations you cannot source.
- If the user asks for an action that would normally require an agent (reading
  a file, searching a system, creating/modifying anything outside this chat),
  briefly note that no agents are currently enabled and suggest the user enable
  one from the Agents panel. Then offer the best help you can with text alone.
- For conversational questions, reasoning, summarization, drafting, or general
  knowledge — answer normally as a text-only chat assistant.
"""


# Chat system-prompt template. The two opaque marks are where the per-turn
# volatile sections (the file-mapping list, the live-canvas listing) are
# substituted. ``context_engineering.compose_system_prompt`` fills them in
# place by default (byte-identical to the legacy f-string), or — when
# FF_CONTEXT_ENGINEERING is on (033 Wave-0 C-N16) — blanks them here and
# appends them last so the stable instruction prefix stays cache-friendly.
CHAT_SYSTEM_TEMPLATE = """You are an AI orchestrator. Your goal is to simplify complex tasks for the user by intelligently using available tools.

%%ASTRAL_FILE_CONTEXT%%

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
- **CHAT IS CONCISE**: Your final chat reply must be SHORT — 2-4 plain sentences, no headings,
  no tables, no long documents. Substantial content (drafts, documents, lists, tables,
  structured data) belongs in UI components / tool outputs, not in the chat text; long text
  replies are moved to the canvas automatically.
- **VISUALIZATIONS**: If the user asks for a graph, YOU MUST call the graphing tool. Do not just describe the data.
%%ASTRAL_CANVAS_CONTEXT%%
COMPONENT UPDATE RULES:
- The user's canvas is PERSISTENT: every component listed above under COMPONENTS CURRENTLY ON CANVAS stays visible until removed, and updates replace it in place.
- When the user asks to MODIFY, UPDATE, REMOVE items from, or CHANGE existing displayed data, re-call the SAME tool that originally created it with the corrected/updated parameters. Do NOT create duplicates.
- When you author UI components directly and intend to UPDATE one listed above, set its "id" field to that component's component_id so it updates in place; omit "id" for genuinely new components.
- When the user asks for something completely NEW and unrelated, call the appropriate tool normally — the new output is added alongside the existing components.
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
    # DeepSeek DSML format — note the FULLWIDTH vertical bar (U+FF5C), not regular |.
    # Matches both the wrapper <｜DSML｜tool_calls>...</｜DSML｜tool_calls> and
    # standalone <｜DSML｜invoke ...></｜DSML｜invoke> blocks.
    re.compile(r"<｜DSML｜tool_calls>.*?</｜DSML｜tool_calls>", re.DOTALL),
    re.compile(r"<｜DSML｜invoke[^>]*>.*?</｜DSML｜invoke>", re.DOTALL),
    # Stray dangling open tags with no close
    re.compile(r"<\|?tool_call\|?>", re.IGNORECASE),
    re.compile(r"<\|tool_calls_section_(?:begin|end)\|>", re.IGNORECASE),
    re.compile(r"\[/?TOOL_CALLS\]", re.IGNORECASE),
    re.compile(r"</?｜DSML｜[^>]*>"),
]


# Patterns used to extract the tool NAME from a leak match — independent of
# which wrapper pattern fired. Used by Orchestrator._diagnose_leaked_tool_calls
# to translate raw markup into a friendly user-facing alert.
_LEAK_TOOL_NAME_EXTRACTORS = [
    # DeepSeek DSML invoke tag: <｜DSML｜invoke name="tool_name">
    re.compile(r'<｜DSML｜invoke\s+name="([^"]+)"'),
    # Llama / OpenAI-style JSON tool calls embedded in leak markup
    re.compile(r'"name"\s*:\s*"([^"]+)"'),
    # Qwen <tool_call><name>tool_name</name>...
    re.compile(r"<name>\s*([A-Za-z_][A-Za-z0-9_]*)\s*</name>"),
    # Mistral [TOOL_CALLS] [{"name": "tool_name", ...}] — covered by the JSON pattern above
    # Bare function-name=... forms occasionally seen in mistral
    re.compile(r"function\s*[:=]\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)"),
]


def _tool_names_from_leak(content: str) -> List[str]:
    """Extract distinct tool names from leaked tool-call markup.

    Tries every pattern in :data:`_LEAK_TOOL_NAME_EXTRACTORS` against the
    full ``content`` blob. Returns names in first-seen order with duplicates
    removed. Returns an empty list when no recognizable tool name is found —
    in that case the caller falls back to silently stripping the markup.
    """
    if not content:
        return []
    seen: List[str] = []
    seen_set: set = set()
    for pat in _LEAK_TOOL_NAME_EXTRACTORS:
        for match in pat.finditer(content):
            name = match.group(1)
            if name and name not in seen_set:
                seen_set.add(name)
                seen.append(name)
    return seen


# Diagnostic statuses returned by Orchestrator._diagnose_disabled_tool.
# Defined at module scope so tests can import them by name.
class ToolDiagnosticStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED_IN_PICKER = "disabled_in_picker"
    AGENT_DISABLED_BY_USER = "agent_disabled_by_user"
    PERMISSION_DENIED = "permission_denied"
    SECURITY_BLOCKED = "security_blocked"
    UNKNOWN_TOOL = "unknown_tool"


class ToolDiagnostic(NamedTuple):
    status: ToolDiagnosticStatus
    agent_id: Optional[str]
    agent_display_name: Optional[str]
    reason: Optional[str]


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


# Feature 029 — catalog change handling for historical components
# (specs/029-agents-adaptive-ui-ci/baseline.md). Six agents are retired
# outright; three merged into ml-services-1. Sources remap so refresh /
# pagination on pre-merge components keeps working; retired sources get an
# explicit retirement message instead of a dispatch crash. Module-level (not
# class attributes) so unbound-method test fakes need no extra wiring.
RETIRED_AGENT_IDS = frozenset({
    "email_tracker", "email-tracker-1", "grant_budgets", "grant-budgets-1",
    "grants", "grants-1", "linkedin", "linkedin-1",
    "nefarious", "nefarious-1", "nocodb", "nocodb-1",
})
_MERGED_AGENT_REMAP = {
    "classify": "ml-services-1", "classify-1": "ml-services-1",
    "forecaster": "ml-services-1", "forecaster-1": "ml-services-1",
    "llm_factory": "ml-services-1", "llm-factory-1": "ml-services-1",
}
_MERGED_TOOL_PREFIX = {
    "classify": "classify_", "classify-1": "classify_",
    "forecaster": "forecaster_", "forecaster-1": "forecaster_",
}
_MERGED_COLLIDING_VERBS = frozenset({
    "submit_dataset", "start_training_job", "get_job_status",
    "get_results", "delete_dataset",
})

# 030: per-tool dispatch ceilings for long-running verbs (everything else
# keeps the 30 s default). research_brief legitimately performs one search
# plus several 15 s-bounded page fetches — the default ceiling guaranteed
# "Tool call timed out" (live incident).
TOOL_TIMEOUT_OVERRIDES = {
    "research_brief": 150.0,
    "fetch_page": 45.0,
    "summarize_url": 60.0,
    "compare_documents": 60.0,
}


def remap_merged_source(agent_id: str, tool_name: str):
    """Map a pre-merge (agent, tool) provenance onto the ml-services-1 agent.

    The five verbs classify and forecaster shared pre-merge carry a service
    prefix in the consolidated registry; everything else keeps its name.
    Unrelated agents pass through untouched.
    """
    new_agent = _MERGED_AGENT_REMAP.get(agent_id)
    if not new_agent:
        return agent_id, tool_name
    prefix = _MERGED_TOOL_PREFIX.get(agent_id, "")
    if prefix and tool_name in _MERGED_COLLIDING_VERBS:
        tool_name = prefix + tool_name
    return new_agent, tool_name


class Orchestrator:
    def __init__(self):
        # 020-async-queries: background task manager for async chat processing
        from orchestrator.async_tasks import BackgroundTaskManager
        self.async_task_manager = BackgroundTaskManager()
        self.agents: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.ui_clients: List[websockets.WebSocketServerProtocol] = []
        self.ui_sessions: Dict[websockets.WebSocketServerProtocol, Dict] = {}
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_capabilities: Dict[str, List[Dict]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.pending_ui_sockets: Dict[str, Any] = {}  # request_id -> UI websocket (for progress forwarding)
        # 015-external-ai-agents: per-(user, agent) concurrency cap for long-running tools (FR-026).
        self.concurrency_cap = ConcurrencyCap(max_per_user_agent=3)
        # Maps cap_job_id -> (user_id, agent_id) so terminal ToolProgress can release the right slot.
        self._pending_cap_entries: Dict[str, tuple] = {}
        # Maps cap_job_id -> {user_id, agent_id, chat_id, tool_name} for long-running
        # jobs, so a job's progress + terminal result can be routed to (and
        # persisted in) the originating CHAT — not a single ephemeral socket —
        # which keeps auto-progress working across refresh / device changes.
        self._job_context: Dict[str, Dict[str, Any]] = {}
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

        # Feature 028 — per-socket read-only timeline mode (mutating
        # component actions are refused server-side while set) and per-chat
        # serialization locks for deterministic component-action ordering.
        self._ws_timeline_mode: Dict[int, bool] = {}
        self._workspace_locks: Dict[str, asyncio.Lock] = {}

        # Sockets currently showing the server-driven welcome canvas (example
        # queries pushed after register_ui). The first chat message blanks the
        # canvas so flat ui_upsert appends never land under the examples.
        self._ws_welcome: Dict[int, bool] = {}

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

        # Feature 040 / 033 Wave-0 (C-U12): default reasoning-effort knob
        # threaded through _call_llm. Unset → nothing is sent (zero behavior
        # change on endpoints that predate reasoning models). Callers may
        # override per-call; this is only the global default.
        self.llm_reasoning_effort = self._valid_reasoning_effort(
            os.getenv("LLM_REASONING_EFFORT")
        )
        # 033 Wave-0 (C-N14/C-U12): per-(base_url, model) capability cache of
        # optional request params the endpoint rejected, so we probe once and
        # then stop sending them. {(base_url, model): {"response_format", …}}.
        self._llm_unsupported_params: Dict[tuple, set] = {}

        # 033 Wave-0 (C-S4): when datamarking is engaged, also surgically remove
        # well-known instruction-override spans from untrusted tool output
        # (FR: "optional span-level removal"). Off by default — the default
        # defense is delimiting only, which never mutates content.
        self._datamark_sanitize_spans = os.getenv(
            "DATAMARK_SANITIZE_SPANS", "false"
        ).lower() in ("true", "1", "yes")

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

        # Feature 028 — per-chat persistent workspace (identity, upserts,
        # snapshots/timeline). Owns the saved_components store.
        from orchestrator.workspace import WorkspaceManager
        self.workspace = WorkspaceManager(self.history)

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
        # Feature 025 — per-user personalization (profile, personality, memory)
        from personalization.service import PersonalizationService
        self.personalization_service = PersonalizationService(self.history.db)
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

        # 028 FR-016 — agent connections are authenticated. In production
        # (ASTRAL_ENV != development) a missing/invalid key refuses the
        # registration outright (fail closed); dev mode stays keyless.
        from orchestrator.auth import validate_agent_api_key
        if not validate_agent_api_key(getattr(msg, "api_key", None) or ""):
            logger.warning(
                "Refusing agent registration for '%s': missing or invalid agent "
                "API key (028 FR-016 fail-closed)", card.agent_id)
            if websocket is not None:
                try:
                    await websocket.close(code=1008, reason="agent authentication required")
                except Exception:
                    logger.debug("close after refused agent registration failed", exc_info=True)
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
                # Feature 030: ownerless registrations are operator-bundled
                # agents (user-created agents get explicit creator ownership
                # from agent_lifecycle before they register), so default them
                # PUBLIC — otherwise they are invisible in every Agents tab
                # and users cannot discover or enable them. Drafts stay
                # private.
                self.history.db.set_agent_ownership(
                    card.agent_id, default_owner,
                    is_public=not self._is_draft_agent(card.agent_id))
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

            # Internal registration of an operator-configured A2A discovery —
            # carries the orchestrator's own configured key (FR-016).
            register_msg = RegisterAgent(agent_card=custom_card,
                                         api_key=os.getenv("AGENT_API_KEY") or None)
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

            elif isinstance(msg, ToolProgress):
                # Long-running job progress. Handled UNCONDITIONALLY — this branch
                # was previously gated behind the off-by-default progress_streaming
                # flag, which silently dropped both the auto-progress the agent
                # promised AND the concurrency-cap release.
                await self._handle_tool_progress(msg)

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

                    # Feature 016 (FR-015): Record the persistent-login-aware
                    # entry-point action. The client tells us via msg.resumed
                    # whether it reached this WS connect via a silent resume
                    # from a stored credential (True) or via a fresh
                    # interactive Keycloak login (False — also the legacy
                    # default for older clients). Three distinct action_type
                    # values let the audit log distinguish these flows.
                    try:
                        from audit.hooks import record_auth_event
                        resumed_flag = bool(getattr(msg, "resumed", False))
                        action = "session_resumed" if resumed_flag else "login_interactive"
                        await record_auth_event(
                            claims={**user_data, "_pl_resumed": resumed_flag},
                            action=action,
                            description=(
                                "Silent session resumed from stored credential"
                                if resumed_flag
                                else "Interactive login completed; new session established"
                            ),
                        )
                    except Exception as _e:
                        logger.debug(f"persistent-login audit record failed: {_e}")

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

                    # Initial canvas: server-driven welcome examples when this
                    # socket has no chat to resume — ordinary astralprims
                    # components over the normal ui_render path (Constitution
                    # II: ROTE adapts them per device; nothing client-specific).
                    try:
                        if not self._ws_active_chat.get(id(websocket)):
                            from orchestrator.welcome import welcome_components
                            # Feature 030: tell the welcome canvas whether any
                            # tools are dispatchable so it can lead with the
                            # enable-agents consent card instead of promising
                            # examples that would silently degrade to text.
                            _welcome_user = self._get_user_id(websocket)
                            try:
                                _tools_avail = self.compute_tools_available_for_user(_welcome_user)
                            except Exception:
                                _tools_avail = True
                            await self.send_ui_render(
                                websocket, welcome_components(tools_available=_tools_avail))
                            self._ws_welcome[id(websocket)] = True
                    except Exception as _e:  # non-fatal — an empty canvas is fine
                        logger.debug(f"welcome canvas render failed (non-fatal): {_e}")
                else:
                    logger.warning("UI registration failed: Invalid or missing token")
                    # Feature 016 (FR-015): When the client said it was
                    # silently resuming (resumed=True) but the server
                    # rejected the token, record auth.session_resume_failed
                    # so the audit log captures the failure. Best-effort
                    # attribution via base64-decode of the JWT payload; on
                    # failure record as anonymous.
                    try:
                        resumed_flag = bool(getattr(msg, "resumed", False))
                        if resumed_flag:
                            attribution_claims = None
                            if token:
                                try:
                                    import base64
                                    parts = token.split(".")
                                    if len(parts) == 3:
                                        payload_b64 = parts[1]
                                        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                                        payload_json = base64.b64decode(payload_b64).decode("utf-8")
                                        attribution_claims = json.loads(payload_json)
                                except Exception:
                                    attribution_claims = None
                            from audit.hooks import record_auth_event
                            from audit.recorder import get_recorder, make_correlation_id, now_utc
                            from audit.schemas import AuditEventCreate
                            if attribution_claims and attribution_claims.get("sub"):
                                await record_auth_event(
                                    claims=attribution_claims,
                                    action="session_resume_failed",
                                    description="Silent session resume rejected (invalid/expired token)",
                                    outcome="failure",
                                    outcome_detail="ws_register token rejected",
                                )
                            else:
                                rec = get_recorder()
                                if rec is not None:
                                    await rec.record(AuditEventCreate(
                                        actor_user_id="anonymous",
                                        auth_principal="anonymous",
                                        event_class="auth",
                                        action_type="auth.session_resume_failed",
                                        description="Silent session resume rejected; token unattributable",
                                        correlation_id=make_correlation_id(),
                                        outcome="failure",
                                        outcome_detail="ws_register token rejected (no claims recoverable)",
                                        inputs_meta={"resumed": True},
                                        started_at=now_utc(),
                                    ))
                    except Exception as _e:
                        logger.debug(f"session_resume_failed audit record failed: {_e}")
                    # Ungate waiting tasks so they hit the auth check naturally
                    evt = self._registered_events.get(id(websocket))
                    if evt:
                        evt.set()
                    # Feature 028 (FR-009, research D4): replace the dead-end
                    # error Alert with a recoverable auth_required signal. The
                    # client re-fetches /auth/session (which silently
                    # refreshes server-side) and retries register_ui, or
                    # redirects to /auth/login when the session is truly gone.
                    from shared.protocol import AuthRequired
                    reason = "invalid"
                    if token:
                        try:
                            import base64 as _b64
                            _p = token.split(".")[1]
                            _p += "=" * (-len(_p) % 4)
                            _exp = json.loads(_b64.urlsafe_b64decode(_p)).get("exp")
                            if _exp is not None and float(_exp) < time.time():
                                reason = "expired"
                        except Exception:
                            pass
                    await self._safe_send(websocket, AuthRequired(reason=reason).to_json())
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
                        Alert(message="Unauthorized. Please refresh.", variant="error").to_dict()
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
                    # Leaving the welcome canvas: blank it so flat ui_upsert
                    # appends start from an empty canvas on every target.
                    if self._ws_welcome.pop(id(websocket), None):
                        try:
                            await self.send_ui_render(websocket, [])
                        except Exception:
                            pass
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

                    # Feature 028: chat_message also marks this socket's active
                    # chat (pre-028 only load_chat did) so workspace upserts in
                    # brand-new chats reach the originating tab's siblings too.
                    self._ws_active_chat[id(websocket)] = chat_id

                    display_message = msg.payload.get("display_message")
                    async_mode = msg.payload.get("async_mode", False)

                    # Feature 031: structured attachment references staged on
                    # this turn. Each entry: {attachment_id, filename, category}.
                    # Validated for ownership inside handle_chat_message; absent
                    # / non-list ≡ no attachments (backward compatible).
                    attachments_raw = msg.payload.get("attachments")
                    attachments = attachments_raw if isinstance(attachments_raw, list) else None

                    # 020-async-queries: if async_mode is True, dispatch as
                    # a background task instead of blocking the WS.
                    if async_mode:
                        await self._dispatch_async_chat(
                            websocket, user_message, chat_id, display_message,
                            user_id=user_id, draft_agent_id=draft_agent_id,
                            selected_tools=selected_tools, attachments=attachments,
                        )
                    else:
                        self.cancelled_sessions[id(websocket)] = False
                        # Use serialized wrapper so concurrent chat messages
                        # for the same session are processed one at a time.
                        await self._serialized_chat(
                            websocket, user_message, chat_id, display_message,
                            user_id=user_id, draft_agent_id=draft_agent_id,
                            selected_tools=selected_tools, attachments=attachments,
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

                elif msg.action == "watch_task":
                    # 020-async-queries: subscribe to task completion notifications
                    task_id = msg.payload.get("task_id")
                    if task_id:
                        bg_task = await self.async_task_manager.get(task_id)
                        if bg_task:
                            bg_task.watchers.append(websocket)
                            # If already completed, notify immediately
                            if bg_task.status.value in ("completed", "failed", "cancelled"):
                                await self._safe_send(websocket, json.dumps({
                                    "type": "task_completed",
                                    "payload": {
                                        "task_id": bg_task.task_id,
                                        "chat_id": bg_task.chat_id,
                                        "status": bg_task.status.value,
                                    },
                                }))
                        else:
                            await self._safe_send(websocket, json.dumps({
                                "type": "error",
                                "payload": {"message": f"Task {task_id} not found"},
                            }))
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "error",
                            "payload": {"message": "task_id is required for watch_task"},
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
                            Alert(message="Please provide an agent URL", variant="error").to_dict()
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
                                Alert(message=f"Could not discover A2A agent at {agent_url}", variant="error").to_dict()
                            ])
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "done",
                                "message": "Discovery failed"
                            }))

                elif msg.action == "get_history":
                    # Feature 037: show the server-driven skeleton while the
                    # recent-chats query runs, then push the rendered list.
                    await self._push_history_surface(websocket, loading=True)
                    chats = self.history.get_recent_chats(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "history_list",
                        "chats": chats
                    }))
                    await self._push_history_surface(websocket, chats=chats)

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
                        # Loading a chat replaces the canvas — the welcome
                        # blank-on-first-message must not fire afterwards.
                        self._ws_welcome.pop(ws_id, None)
                        # Feature 028 (FR-031/FR-032): switching chats ends any
                        # historical timeline view — the new chat opens live,
                        # and the client is told so its banner/mode clears.
                        if self._ws_timeline_mode.pop(ws_id, None):
                            await self._safe_send(websocket, json.dumps({
                                "type": "workspace_timeline_mode",
                                "active": False,
                            }))

                        # Feature 028 (FR-028) + 045: component-bearing transcript
                        # messages get a server-rendered html form, but the chat
                        # rail is TEXT ONLY — only text primitives render; rich
                        # components (tables/charts/metrics) are dropped here and
                        # shown on the canvas, which re-hydrates from the
                        # workspace below. A message with no text-only content
                        # gets no html (the client renders no bubble for it).
                        try:
                            for m in chat.get("messages", []):
                                if not isinstance(m.get("content"), str) and isinstance(m.get("content"), list):
                                    _t_html = self._transcript_html(m["content"])
                                    if _t_html:
                                        m["html"] = _t_html
                        except Exception:
                            logger.exception("webrender unavailable for transcript rendering")

                        # Feature 031: re-hydrate per-turn attachment references
                        # so the client re-renders attachment chips on loaded
                        # user messages (additive `attachments` field).
                        try:
                            from orchestrator.attachments.message_attachment_repo import MessageAttachmentRepository
                            from orchestrator.attachments.repository import AttachmentRepository
                            _link_repo = MessageAttachmentRepository(self.history.db)
                            _att_repo = AttachmentRepository(self.history.db)
                            for m in chat.get("messages", []):
                                if m.get("role") != "user" or not m.get("id"):
                                    continue
                                links = _link_repo.list_for_message(m["id"], user_id)
                                atts = []
                                for ln in links:
                                    a = _att_repo.get_by_id(ln["attachment_id"], user_id)
                                    if a is not None:
                                        atts.append({"attachment_id": a.attachment_id,
                                                     "filename": a.filename, "category": a.category})
                                if atts:
                                    m["attachments"] = atts
                        except Exception:
                            logger.debug("attachment re-hydration failed (non-fatal)", exc_info=True)

                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_loaded",
                            "chat": chat
                        }))

                        # Feature 028 (FR-027): re-hydrate the persistent
                        # workspace — the canvas state the user left — as a
                        # full ui_render after chat_loaded (stream-resume
                        # precedent below). No capabilities re-run.
                        try:
                            # Feature 029: materialized arrangements re-hydrate too.
                            ws_components = self._canvas_components(chat_id, user_id)
                            if ws_components:
                                await self.send_ui_render(websocket, ws_components)
                        except Exception:
                            logger.exception("workspace re-hydration failed for chat %s", chat_id)

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
                            Alert(message="Chat not found", variant="error").to_dict()
                        ])

                elif msg.action == "new_chat":
                    chat_id = self.history.create_chat(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_created",
                        "payload": {"chat_id": chat_id, "from_message": False}
                    }))

                # Saved components actions
                elif msg.action in ("save_component", "delete_saved_component",
                                    "combine_components", "condense_components") \
                        and self._ws_timeline_mode.get(id(websocket)):
                    # Feature 028 (FR-031): historical views are strictly
                    # read-only — the shipped client makes these unreachable in
                    # timeline mode, but a raw WS client must be refused too.
                    await self._audit_workspace_denial(
                        user_id, msg.payload.get("chat_id") or "",
                        msg.payload.get("component_id") or "", "timeline_readonly")
                    await self.send_ui_render(websocket, [
                        Alert(message="You are viewing a past workspace state — return to live to interact.",
                              variant="warning").to_dict()
                    ], target="chat")

                elif msg.action == "save_component":
                    chat_id = msg.payload.get("chat_id")
                    component_data = msg.payload.get("component_data")
                    component_type = msg.payload.get("component_type")
                    title = msg.payload.get("title")
                    
                    if not chat_id or not component_data:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing required fields for saving component", variant="error").to_dict()
                        ])
                        return
                    
                    try:
                        # Feature 028 (D18): explicit saves are a deprecated
                        # alias — everything rich is auto-persisted. Route
                        # through the workspace so the row gets a stable
                        # identity instead of a bare legacy row.
                        if isinstance(component_data, dict):
                            ops = self.workspace.upsert(chat_id, user_id, [component_data])
                            component_id = ops[0]["component_id"] if ops else self.history.save_component(
                                chat_id, component_data, component_type, title, user_id=user_id
                            )
                            if ops:
                                await self.send_ui_upsert(websocket, chat_id, user_id, ops)
                        else:
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
                            Alert(message="Missing component ID", variant="error").to_dict()
                        ])
                        return

                    # Feature 028 (D18): resolve the row before deleting so the
                    # workspace identity can be removed from every client and
                    # the removal snapshotted/audited.
                    row = self.history.get_component_by_id(component_id, user_id=user_id)
                    ws_component_id = None
                    chat_id_for_row = row.get("chat_id") if row else None
                    if row and isinstance(row.get("component_data"), dict):
                        ws_component_id = row["component_data"].get("component_id")

                    success = self.history.delete_component(component_id, user_id=user_id)
                    if success:
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_deleted",
                            "component_id": component_id
                        }))
                        if ws_component_id and chat_id_for_row:
                            await self.send_ui_upsert(websocket, chat_id_for_row, user_id, [
                                {"op": "remove", "component_id": ws_component_id}
                            ])
                            try:
                                self.workspace.snapshot(chat_id_for_row, user_id, cause="remove")
                                from audit.hooks import record_workspace_event
                                asyncio.create_task(record_workspace_event(
                                    user_id=user_id, action="component_removed",
                                    chat_id=chat_id_for_row, component_id=ws_component_id,
                                ))
                            except Exception:
                                logger.debug("workspace remove bookkeeping failed", exc_info=True)

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
                            # Feature 028 (D18): make the legacy replacement
                            # visible — stamp identities, snapshot, re-render.
                            await self._reconcile_legacy_replacement(
                                websocket, chat_id, user_id, cause="combine"
                            )
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

                elif msg.action == "enable_recommended_agents":
                    # Feature 030 — one-click consent enable. The click IS the
                    # explicit user grant (Constitution VII: the system sets
                    # attenuated scopes automatically; the user may override
                    # per agent afterwards). Server-side validation: only
                    # connected, non-draft, PUBLIC agents are eligible and
                    # ``tools:write`` is never granted. The action is audited
                    # like every other ui_event (ws.enable_recommended_agents).
                    requested = msg.payload.get("agent_ids")
                    if requested is not None and not (
                        isinstance(requested, list)
                        and all(isinstance(a, str) for a in requested)
                    ):
                        return
                    enabled_now = self._enable_recommended_agent_scopes(user_id, requested)
                    if self._ws_welcome.get(id(websocket)):
                        # Welcome canvas is showing — re-render it so the
                        # consent card disappears and the examples are live.
                        from orchestrator.welcome import welcome_components
                        await self.send_ui_render(websocket, welcome_components(
                            tools_available=self.compute_tools_available_for_user(user_id)))
                    else:
                        await self.send_ui_render(websocket, [Alert(
                            message=(
                                f"Enabled {len(enabled_now)} agents for this account "
                                "(read-only — never write) — ask your question again to use them."
                                if enabled_now else
                                "No public agents were available to enable."
                            ),
                            variant="success" if enabled_now else "warning",
                        ).to_dict()], target="chat")
                    for client in self.ui_clients:
                        if self._get_user_id(client) == user_id:
                            asyncio.create_task(self.send_dashboard(client))
                            asyncio.create_task(self.send_agent_list(client))

                elif msg.action == "schedule_decision":
                    # Feature 030 — the consent click for a chat-proposed
                    # scheduled job (audited as ws.schedule_decision plus the
                    # schedule.* events the handler records).
                    from orchestrator import scheduling_chat
                    await scheduling_chat.handle_decision(
                        self, websocket, user_id, msg.payload or {})

                elif msg.action == "update_device":
                    # ROTE: viewport / capability change from the frontend
                    device_info = msg.payload.get("device") or {}
                    new_profile, re_adapted, profile_changed = self.rote.update_device(websocket, device_info)
                    await self._safe_send(websocket, json.dumps({
                        "type": "rote_config",
                        "device_profile": new_profile.to_dict(),
                        "speech_server_available": bool(os.getenv("SPEACHES_URL", "").strip()),
                    }))
                    # Feature 028 (D17): a device change re-renders the FULL
                    # persisted workspace from server state. The pre-028
                    # single-slot _last_components replay would wipe all but
                    # the most recent fragment once partial upserts exist.
                    handled_via_workspace = False
                    if profile_changed:
                        active_chat = self._ws_active_chat.get(id(websocket))
                        if active_chat:
                            try:
                                # Feature 029: re-adapt the designed canvas, not
                                # just the flat component list.
                                ws_components = self._canvas_components(active_chat, user_id)
                                if ws_components:
                                    await self.send_ui_render(websocket, ws_components)
                                    handled_via_workspace = True
                            except Exception:
                                logger.exception("workspace re-adapt failed after device change")
                    # Legacy fallback for sockets with no persisted workspace.
                    if not handled_via_workspace and re_adapted is not None:
                        re_html = None
                        try:
                            from webrender import render_for_target
                            re_html = render_for_target("web", re_adapted, self.rote.get_profile(websocket))
                        except Exception:
                            logger.exception("webrender: failed to re-render UI after device change")
                        msg_out = UIUpdate(components=re_adapted, html=re_html)
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
                            # Feature 028 (D18): make the legacy replacement
                            # visible — stamp identities, snapshot, re-render.
                            await self._reconcile_legacy_replacement(
                                websocket, chat_id, user_id, cause="condense"
                            )
                    except Exception as e:
                        logger.error(f"Condense failed: {e}", exc_info=True)
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to condense components: {str(e)}"
                        }))

                elif msg.action == "component_action":
                    # Feature 028 — standardized deterministic component
                    # action (contracts/component-action.md).
                    await self._handle_component_action(websocket, user_id, msg.payload or {})

                elif msg.action == "table_paginate":
                    # Feature 028 (FR-038): pagination clicks that carry the
                    # table's component identity route through the
                    # standardized pipeline — permission-gated and updating
                    # ONLY the table, instead of replacing the whole canvas.
                    if (msg.payload or {}).get("component_id"):
                        await self._handle_component_action(websocket, user_id, {
                            "chat_id": (msg.payload or {}).get("chat_id"),
                            "component_id": msg.payload["component_id"],
                            "kind": "refresh",
                            "params_patch": (msg.payload or {}).get("params", {}),
                        })
                        return
                    # Legacy alias (pre-028 clients): re-invoke with raw params.
                    tool_name = msg.payload.get("tool_name")
                    agent_id = msg.payload.get("agent_id")
                    params = msg.payload.get("params", {})

                    if not tool_name or not agent_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing tool_name or agent_id for pagination", variant="error").to_dict()
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
                                Alert(message=result.error.get("message", "Pagination failed"), variant="error").to_dict()
                            ])
                    except Exception as e:
                        logger.error(f"table_paginate failed: {e}", exc_info=True)
                        await self.send_ui_render(websocket, [
                            Alert(message=f"Pagination failed: {e}", variant="error").to_dict()
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

                else:
                    # Feature 027: chrome/settings + agentic-creation actions
                    # live in their own dispatcher. It returns False only for
                    # actions outside its namespace — those were previously a
                    # silent fall-through; log them so typos are diagnosable.
                    from orchestrator.chrome_events import handle_chrome_event
                    handled = await handle_chrome_event(
                        self, websocket, str(msg.action or ""), msg.payload or {}, user_id
                    )
                    if not handled:
                        logger.warning("Unhandled ui_event action: %r", msg.action)

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
                    return {"error": "Failed to parse LLM response as JSON"}
            
            if "components" not in result or not isinstance(result["components"], list):
                return {"error": "LLM response missing 'components' array"}
            
            # Feature 029 (FR-020): the renderer registry is the single
            # source of truth for valid types — hand-copied whitelists
            # drifted (param_picker/audio/file IO were silently rewritten
            # to containers). "chart" stays as an accepted alias; the tree
            # validator maps it to plotly_chart.
            from webrender import allowed_primitive_types
            VALID_TYPES = set(allowed_primitive_types()) | {"chart"}
            
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
            logger.info("Mapping generic component type 'chart' -> 'plotly_chart'")
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

    @classmethod
    def _is_text_only_components(cls, components: list) -> bool:
        """Return True if all components in the tree contain only text-based content.

        Used to decide whether parsed UI JSON should go to the canvas (rich content)
        or the chat panel only (text-only content).
        """
        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_type = comp.get("type", "").strip().lower()
            if comp_type not in cls._TEXT_ONLY_TYPES:
                return False
            for key in ("children", "content"):
                children = comp.get(key, [])
                if isinstance(children, list):
                    child_dicts = [c for c in children if isinstance(c, dict) and "type" in c]
                    if child_dicts and not cls._is_text_only_components(child_dicts):
                        return False
        return True

    @classmethod
    def _transcript_html(cls, content) -> str:
        """Feature 045 — server-rendered HTML for a component-bearing transcript
        message, restricted to TEXT ONLY.

        The chat rail is words only: rich components (tables, charts, metrics,
        dashboards, …) live on the canvas and re-hydrate from the persistent
        workspace (``_canvas_components``), NOT from the transcript. So a loaded
        transcript message renders only its text-only primitives (Text/Alert/
        List and text-only containers); any rich component is dropped. Returns
        ``''`` when the message carries nothing text-like — the client then
        renders no bubble for it (the content is on the canvas).
        """
        if not isinstance(content, list):
            return ""
        text_only = [c for c in content
                     if isinstance(c, dict) and cls._is_text_only_components([c])]
        if not text_only:
            return ""
        try:
            from webrender import render as _render_web
            return _render_web(text_only)
        except Exception:
            logger.debug("transcript text-only render failed", exc_info=True)
            return ""

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

    async def _serialized_chat(self, websocket, message, chat_id, display_message, *, user_id=None, draft_agent_id=None, selected_tools=None, attachments=None):
        """Run handle_chat_message under a per-websocket lock so messages
        are serialized but the WS receive loop is never blocked."""
        ws_id = id(websocket)
        lock = self._chat_locks.setdefault(ws_id, asyncio.Lock())
        async with lock:
            try:
                await self.handle_chat_message(
                    websocket, message, chat_id, display_message,
                    user_id=user_id, draft_agent_id=draft_agent_id,
                    selected_tools=selected_tools, attachments=attachments,
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
                        ).to_dict()
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

    async def _dispatch_async_chat(
        self, websocket, message: str, chat_id: str, display_message: str = None,
        *, user_id=None, draft_agent_id=None, selected_tools=None, attachments=None,
    ):
        """020-async-queries: Dispatch a chat message as a background task.

        Creates a BackgroundTask and returns immediately with a task_started
        message. The task runs handle_chat_message asynchronously using a
        VirtualWebSocket to capture outputs.
        """
        logger.info("Dispatching async chat for chat_id=%s user_id=%s", chat_id, user_id)

        async def _run_in_background(vws, msg, cid, display, uid, draft, tools, atts):
            """Execute handle_chat_message with the virtual WS."""
            await self.handle_chat_message(
                vws, msg, cid, display,
                user_id=uid, draft_agent_id=draft, selected_tools=tools,
                attachments=atts,
            )

        bg_task = await self.async_task_manager.submit(
            chat_id=chat_id,
            user_id=user_id or self._get_user_id(websocket),
            coro_factory=_run_in_background,
            msg=message,
            cid=chat_id,
            display=display_message,
            uid=user_id or self._get_user_id(websocket),
            draft=draft_agent_id,
            tools=selected_tools,
            atts=attachments,
        )

        # Register the submitting websocket as a watcher
        bg_task.watchers.append(websocket)

        await self._safe_send(websocket, json.dumps({
            "type": "task_started",
            "payload": {
                "task_id": bg_task.task_id,
                "chat_id": chat_id,
                "status": "queued",
            },
        }))

        # Send loading state so UI knows the query was accepted
        await self._safe_send(websocket, json.dumps({
            "type": "chat_status",
            "status": "processing_async",
            "message": f"Query running in background (task {bg_task.task_id})",
        }))

        return None

    async def run_scheduled_turn(
        self,
        *,
        user_id: str,
        chat_id: Optional[str],
        instruction: str,
        agent_id: Optional[str],
        access_token: str,
        allowed_scopes: List[str],
        correlation_id: str,
    ) -> str:
        """Execute a scheduled job's instruction as a background chat turn (025 T040/T046).

        Reached only when ``FF_SCHEDULER_EXECUTION`` is enabled (gated at loop
        start), which itself requires the recorded offline-grant security review
        (030 FR-004/FR-005). The instruction runs through the normal chat path
        with output persisted to ``chat_id`` history, so the user sees it on
        reconnect (in-app only). Returns a short summary for the completion
        notification.

        Authority: the runner has already minted ``access_token`` from the
        offline grant and computed ``allowed_scopes`` = consented ∩ current.
        Execution runs under the user's current scopes — the security ceiling
        enforced by ``handle_chat_message``. Deep-threading the minted delegated
        token and narrowing tool execution end-to-end to ``allowed_scopes`` is
        the explicit scope of the T057 security review before the flag is enabled
        in production (see specs/030-finish-soul-integration/security-review.md).
        """
        from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket

        target_chat = chat_id or f"scheduled-{user_id}"
        bg = BackgroundTask(
            task_id=(correlation_id or "sched")[:8],
            chat_id=target_chat,
            user_id=user_id,
        )
        vws = VirtualWebSocket(bg)
        try:
            await self.handle_chat_message(vws, instruction, target_chat, user_id=user_id)
        finally:
            try:
                await vws.close()
            except Exception:  # pragma: no cover - close is best-effort
                pass

        # Summarize the captured assistant text for the notification body.
        summary = ""
        for out in bg.outputs:
            if not isinstance(out, dict):
                continue
            txt = out.get("text") or out.get("message")
            if not txt and isinstance(out.get("payload"), dict):
                txt = out["payload"].get("text") or out["payload"].get("message")
            if isinstance(txt, str) and txt.strip():
                summary = txt.strip()
        logger.info(
            "scheduler.run_completed",
            extra={
                "correlation_id": correlation_id,
                "user_id": user_id,
                "chat_id": target_chat,
                "agent_id": agent_id,
                "allowed_scopes": list(allowed_scopes or []),
                "outputs": len(bg.outputs),
            },
        )
        return summary or "Your scheduled task finished."

    async def notify_user(self, user_id: str, payload: Dict[str, Any]) -> None:
        """Deliver an in-app notification to all of a user's connected sockets (025 T049).

        Best-effort live fan-out over ``ui_clients``. The durable artifact of a
        scheduled run is its output, which ``run_scheduled_turn`` persists to chat
        history (delivered on reconnect via ``load_chat``); this is the transient
        toast. In-app only — there is no external channel.
        """
        try:
            data = json.dumps(payload)
        except Exception:  # pragma: no cover - defensive
            logger.debug("notify_user: unserializable payload", exc_info=True)
            return
        sent = 0
        for ws in list(self.ui_clients):
            try:
                if self._get_user_id(ws) != user_id:
                    continue
                if await self._safe_send(ws, data):
                    sent += 1
            except Exception:  # pragma: no cover - per-socket best-effort
                logger.debug("notify_user: send failed for one socket", exc_info=True)
        logger.info(
            "notify_user.delivered",
            extra={"user_id": user_id, "sockets": sent, "kind": payload.get("type")},
        )

    async def _attach_turn_attachments(self, websocket, message, chat_id, user_id, turn_message_id, attachments):
        """Feature 031: validate, link, and surface this turn's attachments.

        Each staged attachment is ownership-validated; valid ones are linked to
        the persisted user message (``message_attachment``) and listed in a
        structured "Attachments on this turn" block appended to the LLM-facing
        message (with the reader tool that can parse each, or "pending parser").
        Foreign/invalid/deleted references are dropped and audited — never
        parsed. Capped at 10 per turn. Returns the (possibly augmented) message.
        """
        try:
            from orchestrator.attachments.repository import AttachmentRepository
            from orchestrator.attachments.message_attachment_repo import MessageAttachmentRepository
            from orchestrator.attachments.parser_repo import AttachmentParserRepository
            from orchestrator import parser_registry
        except Exception:
            logger.warning("attachment wiring imports failed (non-fatal)", exc_info=True)
            return message

        db = self.history.db
        att_repo = AttachmentRepository(db)
        link_repo = MessageAttachmentRepository(db)
        parser_repo = AttachmentParserRepository(db)

        async def _audit_drop(aid):
            try:
                from datetime import datetime, timezone

                from audit.recorder import get_recorder
                from audit.schemas import AuditEventCreate
                rec = get_recorder()
                if rec is None:
                    return
                # correlation_id and started_at are REQUIRED by AuditEventCreate;
                # omitting them raised a ValidationError that the except below
                # silently swallowed, so cross-user denials were never recorded.
                await rec.record(AuditEventCreate(
                    actor_user_id=user_id or "legacy",
                    auth_principal=user_id or "legacy",
                    event_class="file",
                    action_type="attachment_reference_denied",
                    description=f"Dropped unauthorized/invalid attachment reference {aid}",
                    conversation_id=chat_id,
                    correlation_id=str(_uuid.uuid4()),
                    outcome="failure",
                    started_at=datetime.now(timezone.utc),
                ))
            except Exception:
                logger.warning("attachment drop audit failed", exc_info=True)

        MAX_PER_TURN = 10
        accepted = []
        dropped = 0
        seen = set()
        for entry in (attachments or [])[:50]:
            if len(accepted) >= MAX_PER_TURN:
                break
            aid = entry.get("attachment_id") if isinstance(entry, dict) else None
            if not aid or aid in seen:
                continue
            seen.add(aid)
            att = None
            try:
                att = att_repo.get_by_id(aid, user_id)
            except Exception:
                logger.debug("attachment lookup failed", exc_info=True)
            if att is None:
                dropped += 1
                await _audit_drop(aid)
                continue
            try:
                link_repo.insert(chat_id=chat_id, attachment_id=aid,
                                 user_id=user_id, message_id=turn_message_id)
            except Exception:
                logger.debug("message_attachment insert failed", exc_info=True)
            try:
                cov = parser_registry.coverage(att.extension, att.category, parser_repo=parser_repo)
                readable = cov["tool"] if cov.get("covered") else "pending parser"
            except Exception:
                readable = "unknown"
            accepted.append((att, readable))

        if accepted:
            lines = ["[Attachments on this turn]"]
            for att, readable in accepted:
                lines.append(
                    f'- id={att.attachment_id} name="{att.filename}" '
                    f"category={att.category} (readable: {readable})"
                )
            message = message + "\n\n" + "\n".join(lines)
        if dropped:
            try:
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status", "status": "info",
                    "message": f"{dropped} attachment(s) couldn't be used and were skipped.",
                }))
            except Exception:
                pass
        return message

    async def handle_chat_message(self, websocket, message: str, chat_id: str, display_message: str = None, user_id: str = None, draft_agent_id: str = None, selected_tools=None, attachments=None):
        """Process a chat message: LLM determines which tools to call (Multi-Turn Re-Act Loop).

        Feature 013 / FR-018, FR-020, FR-023: ``selected_tools`` is the
        user's in-chat tool-picker subset. When not None, the per-turn
        filter loop excludes any tool not in the subset — narrowing only,
        never widening (scope/per-tool permissions are still enforced).

        Feature 031: ``attachments`` is the list of attachment references the
        user staged on this turn ({attachment_id, filename, category}). Each is
        ownership-validated, linked to the persisted message, and surfaced to
        the LLM as a structured "Attachments on this turn" block so it calls the
        right reader tool with the real attachment_id.
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
        # Feature 031: an attachments-only turn (no typed text) still proceeds —
        # synthesize a minimal instruction so the LLM engages with the files.
        if (not message) and attachments:
            message = "Please review the attached file(s)."
        if not message:
            logger.warning("Empty message received")
            return

        # 030 FR-009 (025 T021): intercept deterministic onboarding ParamPicker
        # submits before the LLM/history path and persist them directly. These
        # are fixed templates ("Save my personalization profile — ...") posted by
        # the onboarding panels; nothing interpreted them before, so selections
        # were silently dropped. Handled submits never enter the LLM path.
        if not draft_agent_id:
            try:
                from orchestrator import onboarding_submit
                if onboarding_submit.is_onboarding_submit(message):
                    if await onboarding_submit.handle_submit(
                            self, websocket, user_id, message, chat_id):
                        return
            except Exception:  # pragma: no cover - never block a chat turn
                logger.warning("onboarding submit handling failed (non-fatal)", exc_info=True)

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
                ).to_dict()
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

        # Feature 030 — fire-and-forget PHI awareness notice (notify-only,
        # fail-open; persistence/audit posture unchanged).
        try:
            asyncio.create_task(self._notify_phi_if_detected(
                websocket, chat_id, user_id, msg_to_save))
        except Exception:
            logger.debug("phi notice scheduling failed (non-fatal)", exc_info=True)

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

        # Feature 031: validate/link/surface this turn's structured attachments.
        # Augments the LLM-facing `message` with an "Attachments on this turn"
        # block; the SAVED history message (msg_to_save) stays the user's text.
        if attachments:
            try:
                message = await self._attach_turn_attachments(
                    websocket, message, chat_id, user_id, turn_message_id, attachments)
            except Exception:
                logger.warning("attachment turn-processing failed (non-fatal)", exc_info=True)

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
        tool_to_agent = {}  # Map LLM-facing function name → agent_id
        # 015-external-ai-agents: when two registered agents expose the
        # same tool name (e.g. classify-1 and forecaster-1 both have
        # `submit_dataset`), we qualify the LLM-facing name with an
        # `{agent_id}__` prefix so the model can pick unambiguously.
        # `tool_to_unqualified` maps the qualified LLM-facing name back
        # to the bare skill id that the owning agent expects to receive
        # over the MCP dispatch boundary. For non-colliding tools the
        # qualified and unqualified names are identical.
        tool_to_unqualified: Dict[str, str] = {}

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

        # Phase A: walk every (agent, skill) pair, run the full gate
        # stack, and accumulate the survivors. We can't emit yet —
        # qualification depends on knowing the full set first (Phase B).
        eligible: List[Tuple[str, Any]] = []
        for agent_id, card in self.agent_cards.items():
            if agent_id not in self.agents:
                continue

            # Draft test: only include tools from the draft agent being tested
            if draft_agent_id and agent_id != draft_agent_id:
                continue

            # 030 follow-up: NON-LIVE drafts never enter normal chats. A
            # draft under self-test registers with the orchestrator and the
            # test flow enables its scopes — without this skip its generated
            # tools leaked into every chat, colliding with (and shadowing)
            # first-party tools (live incident: a generated Serper-keyed
            # web_search shadowed the keyless built-in one).
            if not draft_agent_id and self._is_draft_agent(agent_id):
                logger.debug(
                    f"Agent '{agent_id}' excluded user={user_id} reason=draft_not_live"
                )
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

                eligible.append((agent_id, skill))

        # Phase B: detect skill-id collisions across the surviving pairs.
        # A skill id owned by >1 distinct agent_id needs qualification so
        # the model can pick a specific provider.
        skill_id_owners: Dict[str, set] = {}
        for agent_id, skill in eligible:
            skill_id_owners.setdefault(skill.id, set()).add(agent_id)
        colliding_skill_ids: set = {
            sid for sid, owners in skill_id_owners.items() if len(owners) > 1
        }
        if colliding_skill_ids:
            logger.info(
                "Tool name collisions detected — qualifying with agent_id prefix: %s",
                sorted(colliding_skill_ids),
            )

        # Phase C: emit one tool definition per eligible pair, qualifying
        # the LLM-facing name when there's a collision.
        for agent_id, skill in eligible:
            if skill.id in colliding_skill_ids:
                # OpenAI function-name grammar is [a-zA-Z0-9_-]{1,64}; our
                # agent_ids use hyphens, our skill ids use underscores,
                # and "__" appears in neither — so it's a safe separator.
                llm_name = f"{agent_id}__{skill.id}"
                desc = f"[Provider: {agent_id}] {skill.description or ''}"
            else:
                llm_name = skill.id
                desc = skill.description

            schema = self._sanitize_tool_schema(skill.input_schema or {"type": "object", "properties": {}})
            tool_def = {
                "type": "function",
                "function": {
                    "name": llm_name,
                    "description": desc,
                    "parameters": schema
                }
            }
            tools_desc.append(tool_def)
            tool_to_agent[llm_name] = agent_id
            tool_to_unqualified[llm_name] = skill.id

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

        # Feature 027 — inject the orchestrator meta-tools (create_capability /
        # extend_agent) so the LLM can act on capability gaps (D1). Excluded:
        # draft-test sessions, text-only turns (feature 008 semantics — the
        # user disabled everything deliberately), and flag-off deployments.
        from orchestrator import agentic_creation
        meta_tools_injected = False
        if agentic_creation.should_inject(draft_agent_id) and not is_text_only:
            for _meta_def in agentic_creation.meta_tool_definitions():
                _meta_name = _meta_def["function"]["name"]
                tools_desc.append(_meta_def)
                tool_to_agent[_meta_name] = agentic_creation.META_AGENT_ID
                tool_to_unqualified[_meta_name] = _meta_name
            meta_tools_injected = True

        # Feature 030 — scheduling from chat: the schedule_recurring_task
        # meta-tool makes the feature-025 scheduler reachable from the
        # conversation (a consent card gates creation). Same exclusions as
        # the 027 meta-tools.
        from orchestrator import scheduling_chat
        scheduler_tool_injected = False
        if scheduling_chat.should_inject(draft_agent_id) and not is_text_only:
            for _sched_def in scheduling_chat.meta_tool_definitions():
                _sched_name = _sched_def["function"]["name"]
                tools_desc.append(_sched_def)
                tool_to_agent[_sched_name] = scheduling_chat.META_AGENT_ID
                tool_to_unqualified[_sched_name] = _sched_name
            scheduler_tool_injected = True

        # 030-finish-soul-integration — cross-session memory from chat: the
        # remember/memory_search/memory_get meta-tools make the feature-025
        # memory store usable on request (passive prompt recall is unchanged).
        # Same exclusions as the 027/030 meta-tools.
        from orchestrator import memory_chat
        memory_tool_injected = False
        if memory_chat.should_inject(draft_agent_id) and not is_text_only:
            for _mem_def in memory_chat.meta_tool_definitions():
                _mem_name = _mem_def["function"]["name"]
                tools_desc.append(_mem_def)
                tool_to_agent[_mem_name] = memory_chat.META_AGENT_ID
                tool_to_unqualified[_mem_name] = _mem_name
            memory_tool_injected = True

        if not tools_desc and draft_agent_id:
            await self.send_ui_render(websocket, [
                Alert(
                    message=(
                        "Draft agent has no usable tools yet. Configure tools "
                        "and permissions before testing it."
                    ),
                    variant="warning",
                ).to_dict()
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

            # Feature 028 (FR-029): the canvas context comes from the SAME
            # workspace state the user sees, keyed by the stable component_id
            # the upsert path matches on — so "update the table" turns
            # actually update the table the user is looking at.
            canvas_saved = self.workspace.live_rows(chat_id, user_id=user_id) if chat_id else []
            canvas_context = ""
            if canvas_saved:
                canvas_context = "\nCOMPONENTS CURRENTLY ON CANVAS:\n"
                for sc in canvas_saved:
                    cd = sc.get("component_data", {})
                    if not isinstance(cd, dict):
                        cd = {}
                    source_tool = cd.get("_source_tool", "unknown")
                    source_agent = cd.get("_source_agent", "unknown")
                    canvas_context += (
                        f"- component_id: {sc.get('component_id') or sc['id']} | Title: {sc['title']} "
                        f"| Type: {sc['component_type']} | Tool: {source_tool} | Agent: {source_agent}\n"
                    )

            # 033 Wave-0 (C-N16 — context engineering): with the flag on, the
            # volatile file/canvas sections are appended LAST so the stable
            # instruction prefix stays KV-cache-friendly; off → byte-identical
            # in-place substitution of the legacy f-string.
            system_prompt = context_engineering.compose_system_prompt(
                CHAT_SYSTEM_TEMPLATE,
                file_context=file_context,
                canvas_context=canvas_context,
                cache_stable=flags.is_enabled("context_engineering"),
            )

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

            # 030 FR-010 (025 T028): populate enabled-skill guidance from the
            # tools actually available to the user this turn. Previously
            # ``personalization_skill_lines`` was never assigned, so the call
            # site below always read None and enabling a skill changed nothing.
            # Meta-tools (orchestrator/scheduler/memory pseudo-agents) are
            # excluded — they are not user "skills".
            personalization_skill_lines: List[str] = []
            _meta_agent_ids = {"__orchestrator__", "__scheduler__", "__memory__"}
            for _td in tools_desc:
                try:
                    _fn = _td.get("function") or {}
                    _name = _fn.get("name")
                    if not _name or tool_to_agent.get(_name) in _meta_agent_ids:
                        continue
                    _desc = (_fn.get("description") or "").strip().split(". ")[0][:160]
                    personalization_skill_lines.append(
                        f"- {_name}: {_desc}" if _desc else f"- {_name}")
                except Exception:  # pragma: no cover - never block a chat turn
                    continue
            personalization_skill_lines = personalization_skill_lines[:40] or None

            # Feature 025 — append per-user personalization (memory recall, user
            # context, enabled-skill guidance, and personality/"soul"). This is
            # added AFTER the compliance/safety preamble and tool rules so the
            # personality block remains subordinate to them (FR-015). Skill
            # guidance lines are supplied from the eligible tool set computed
            # above. Failures here must never break a chat turn.
            try:
                skill_lines = locals().get("personalization_skill_lines") or None
                personalization_fragment = self.personalization_service.build_prompt_fragment(
                    user_id, skill_lines=skill_lines
                )
                if personalization_fragment:
                    system_prompt += f"\n\n{personalization_fragment}\n"
            except Exception as exc:  # pragma: no cover — never block a chat turn
                logger.warning(f"personalization injection failed (non-fatal): {exc}")

            # Feature 027 — capability-gap guidance accompanies the meta-tools.
            if meta_tools_injected:
                system_prompt += agentic_creation.SYSTEM_PROMPT_ADDENDUM

            # Feature 030 — recurring-work guidance accompanies the
            # scheduling meta-tool (stops the model denying the capability).
            if scheduler_tool_injected:
                system_prompt += scheduling_chat.SYSTEM_PROMPT_ADDENDUM

            # 030 — memory guidance accompanies the memory meta-tools.
            if memory_tool_injected:
                system_prompt += memory_chat.SYSTEM_PROMPT_ADDENDUM

            # 033 Wave-0 (C-S4 — spotlighting/datamarking): mint one unguessable
            # sentinel for this turn and tell the model that anything wrapped in
            # its markers is untrusted DATA, never instructions. Untrusted
            # (non-digest) tool outputs are wrapped at append time below. No-op
            # when the flag is off.
            datamark_on = flags.is_enabled("datamarking")
            turn_sentinel = datamarking.make_turn_sentinel() if datamark_on else None
            if datamark_on:
                system_prompt += "\n\n" + datamarking.spotlight_system_addendum(turn_sentinel)

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
                        Alert(message="Processing was cancelled.", variant="info").to_dict()
                    ])
                    self.history.add_message(chat_id, "assistant", [
                        Alert(message="Processing was cancelled.", variant="info").to_dict()
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

                # 033 Wave-0 (C-N16): in-loop context editing — tombstone stale
                # tool outputs so a long tool-calling loop doesn't pin volatile
                # (often untrusted) text in the window. Fail-open; off by default.
                if flags.is_enabled("context_engineering"):
                    try:
                        messages, _n_edited = context_engineering.edit_context(messages)
                        if _n_edited:
                            logger.info(
                                "Context editing: tombstoned %d stale tool output(s)",
                                _n_edited,
                            )
                    except Exception:  # pragma: no cover - never block a turn
                        logger.debug("context editing failed (non-fatal)", exc_info=True)

                # Call LLM. Feature 008: text-only turns tag the audit
                # event with feature="chat_dispatch_text_only" so
                # operators can distinguish fallback dispatches from
                # tool-augmented ones (FR-009).
                call_feature = "chat_dispatch_text_only" if is_text_only else "tool_dispatch"
                # Feature 030: wrap the (non-streaming, possibly minute-long)
                # LLM call in a visible chat_step phase — the walkthrough
                # measured 30-220 s tool-less turns whose ONLY feedback was a
                # static status line. KIND_PHASE rows persist with the same
                # PHI redaction as tool steps; failures here never block.
                _phase_recorder = self._chat_recorders.get(id(websocket))
                _phase_step_id = None
                if _phase_recorder is not None:
                    try:
                        from orchestrator.chat_steps import KIND_PHASE
                        _phase_step_id = await _phase_recorder.start(
                            KIND_PHASE,
                            "Drafting answer" if is_text_only else
                            ("Planning next step" if turn_count == 1 else "Analyzing results"),
                        )
                    except Exception:
                        logger.debug("phase step start failed (non-fatal)", exc_info=True)
                try:
                    llm_msg, usage = await self._call_llm(
                        websocket, messages, tools_desc, feature=call_feature
                    )
                except Exception:
                    if _phase_recorder is not None and _phase_step_id:
                        try:
                            await _phase_recorder.error(_phase_step_id, "LLM call failed")
                        except Exception:
                            pass
                    raise
                if _phase_recorder is not None and _phase_step_id:
                    try:
                        await _phase_recorder.complete(_phase_step_id)
                    except Exception:
                        logger.debug("phase step complete failed (non-fatal)", exc_info=True)
                self._accumulate_usage(chat_id, usage)
                if not llm_msg:
                    logger.error("LLM returned None, stopping loop.")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message="Failed to get a response from the AI model. Please try again.", variant="error").to_dict()
                    ])
                    return

                # Check for reasoning content (DeepSeek, o1, etc.)
                reasoning = getattr(llm_msg, 'reasoning_content', None)
                if reasoning:
                    logger.info(f"LLM returned reasoning content ({len(reasoning)} chars)")
                    reasoning_components = [
                        Collapsible(title="Reasoning", content=[
                            Text(content=reasoning, variant="markdown")
                        ]).to_dict()
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
                        res = await self.execute_single_tool(websocket, tc, tool_to_agent, chat_id, user_id=user_id, tool_to_unqualified=tool_to_unqualified)
                        if res:
                            tool_results.append(res)
                    else:
                        res_list = await self.execute_parallel_tools(websocket, llm_msg.tool_calls, tool_to_agent, chat_id, user_id=user_id, tool_to_unqualified=tool_to_unqualified)
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
                        # Feature 029: the adaptive designer arranges multi-
                        # component rounds (fail-open to the 028 flat append).
                        ws_ops = await self._deliver_round_components(
                            websocket, tool_ui_components, chat_id, user_id=user_id,
                            user_request=message,
                        )
                        if chat_id:
                            self.history.add_message(chat_id, "assistant", tool_ui_components, user_id=user_id)
                            if ws_ops:
                                # FR-030: capture the workspace state this turn produced.
                                try:
                                    self.workspace.snapshot(
                                        chat_id, user_id, cause="turn",
                                        turn_message_id=self.history.get_latest_message_id(chat_id, user_id=user_id),
                                    )
                                except Exception:
                                    logger.debug("workspace snapshot failed (tool turn)", exc_info=True)

                    # Append tool outputs to LLM conversation history. C-N15:
                    # the LLM-visible text is the two-tier digest (a tool's
                    # `_model_digest` wins; else the existing `_data`/full-result
                    # serialization) — see _tool_result_to_llm_content.
                    for i, tc in enumerate(llm_msg.tool_calls):
                        res = tool_results[i] if i < len(tool_results) else None
                        tool_content = self._tool_result_to_llm_content(res)
                        # 033 Wave-0 (C-S4): spotlight untrusted tool output.
                        # A tool's own `_model_digest` (C-N15) is tool-authored
                        # and trusted; only raw, non-digest output is wrapped as
                        # untrusted data the model must not obey.
                        if datamark_on and not self._result_has_model_digest(res):
                            tool_content = datamarking.spotlight(
                                tool_content, turn_sentinel,
                                sanitize=self._datamark_sanitize_spans,
                            )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": tool_content,
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
                                Alert(message="All available tools are restricted by your permission settings. Please update your agent permissions.", variant="warning").to_dict()
                            ])
                            break

                    # Update task state and track tool calls
                    if task:
                        for tc in llm_msg.tool_calls:
                            task.tool_calls_made.append(tc.function.name)
                        task.transition(TaskState.RUNNING, current_tool=None)

                    # Loop continues to next turn to let LLM analyze results.
                    # (030: name the writing phase — the walkthrough measured
                    # up to 124 s behind the old static "Analyzing results...")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "thinking",
                        "message": "Analyzing results and writing the response..."
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
                    # Inspect the raw markup BEFORE stripping so we can name
                    # the tool the model wanted (DSML / OpenAI-leak / Qwen /
                    # Mistral / etc.) and surface a friendly disabled-tool
                    # alert. See Orchestrator._diagnose_leaked_tool_calls.
                    leak_alerts = self._diagnose_leaked_tool_calls(raw_content, user_id, chat_id)
                    content = _sanitize_text_response(raw_content)
                    if content != raw_content.strip():
                        logger.warning(
                            "Stripped leaked tool-call tokens from text response "
                            "(chat_id=%s user_id=%s is_text_only=%s raw_len=%d clean_len=%d alerts=%d)",
                            chat_id, user_id, is_text_only, len(raw_content), len(content), len(leak_alerts),
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
                                        # Recursively validate component structure so the
                                        # client never sees an unrenderable type. Feature 029
                                        # (FR-020): validate against the renderer registry,
                                        # not a hand-copied subset.
                                        from webrender import allowed_primitive_types
                                        self._validate_component_tree(
                                            item, set(allowed_primitive_types()) | {"chart"}
                                        )
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

                    final_ops = []
                    if parsed_components:
                        if self._is_text_only_components(parsed_components):
                            # Text-only components -- route to chat panel only.
                            # Persisted history matches what the user sees so a
                            # chat reload re-renders the same alert.
                            response_components = list(leak_alerts) + list(parsed_components)
                            if is_text_only:
                                response_components += self._text_only_cta_components(user_id)
                            await self.send_ui_render(websocket, response_components, target="chat")
                        else:
                            # Rich UI components -- canvas gets the parsed components,
                            # chat gets the leak alerts + a CONCISE narrative (030:
                            # the chat rail is words only; a long/structured
                            # narrative becomes a durable canvas doc card). The
                            # persisted message includes BOTH so reload shows
                            # the canvas + alerts.
                            _tools_ran = bool(task.tool_calls_made) if task else False
                            if chat_id and self._narrative_is_long(content):
                                parsed_components = list(parsed_components) + [
                                    self._narrative_doc_card(chat_id, content)]
                                chat_core = [
                                    Text(content=self._concise_lead(content)).to_dict(),
                                    Text(content="The full write-up is on the canvas.",
                                         variant="caption").to_dict()]
                            else:
                                chat_core = self._chat_narrative(content)
                            final_ops = await self._send_or_replace_components(
                                websocket, parsed_components, chat_id, user_id=user_id
                            ) or []
                            chat_summary = (list(leak_alerts) + chat_core
                                            + [self._provenance_caption(_tools_ran)])
                            await self.send_ui_render(websocket, chat_summary, target="chat")
                            # Feature 045: the chat transcript stores the TEXT the
                            # user saw (chat_summary), NOT the rich components —
                            # those persist in the workspace and re-hydrate to the
                            # canvas on reload. Keeps the chat rail words-only and
                            # makes a reloaded transcript match the live one.
                            response_components = list(chat_summary)
                    else:
                        _tools_ran = bool(task.tool_calls_made) if task else False
                        # 030: long/structured narrative (drafts, documents,
                        # anything with headings/tables) is promoted to a
                        # durable canvas card; the chat rail gets a concise
                        # plain-words lead. Short answers stay chat-only.
                        narrative_doc = None
                        if chat_id and self._narrative_is_long(content):
                            narrative_doc = self._narrative_doc_card(chat_id, content)
                            final_ops = await self._send_or_replace_components(
                                websocket, [narrative_doc], chat_id, user_id=user_id) or []
                            chat_core = [
                                Text(content=self._concise_lead(content)).to_dict(),
                                Text(content="The full write-up is on the canvas.",
                                     variant="caption").to_dict()]
                        else:
                            chat_core = self._chat_narrative(content)
                        response_components = (list(leak_alerts) + chat_core
                                               + [self._provenance_caption(_tools_ran)])
                        # Feature 030: text-only turns for a never-configured
                        # account get a deterministic enable affordance — not
                        # left to the model's prose (which pointed users at a
                        # panel where the agents were not even visible).
                        if is_text_only:
                            response_components += self._text_only_cta_components(user_id)
                        # Concise text response goes to chat panel
                        await self.send_ui_render(websocket, response_components, target="chat")
                        if narrative_doc is not None:
                            # Persist the doc with the turn so reload shows it.
                            response_components = [narrative_doc] + response_components

                    # Save complete interaction to history
                    self.history.add_message(chat_id, "assistant", response_components, user_id=user_id)

                    # Feature 028 (FR-030): close the turn with a workspace
                    # snapshot when this turn changed the workspace.
                    if final_ops and chat_id:
                        try:
                            self.workspace.snapshot(
                                chat_id, user_id, cause="turn",
                                turn_message_id=self.history.get_latest_message_id(chat_id, user_id=user_id),
                            )
                        except Exception:
                            logger.debug("workspace snapshot failed (final turn)", exc_info=True)

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
                    # Fallback if LLM summary fails — descriptive, not boilerplate.
                    await self.send_ui_render(websocket, [
                        Card(title="Round results", content=[
                            Text(content="Multiple tool operations were completed. Review the results above for details.", variant="body")
                        ]).to_dict()
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
                        "message": "Invalid tool schema detected — auto-fixing agent code..."
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
                            Alert(message="Tool schema fixed. Agent restarted — please try your message again.", variant="info").to_dict()
                        ])
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Auto-fix could not resolve the schema issue. Try refining the agent.", variant="warning").to_dict()
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
                        Alert(message=f"Tool schema error and auto-fix failed: {error_text}", variant="error", title="Error").to_dict()
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
                    Alert(message=error_text, variant="error", title="Error").to_dict()
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
                        feature: str = "tool_dispatch", response_format=None,
                        reasoning_effort=None):
        """Helper to call LLM with retries and exponential backoff.

        Only retries on transient errors (502, 503, 504). Fails fast on
        non-transient errors like 424 (model not found) or 401 (auth).

        033 Wave-0 optional enhancement params, both probe-and-fallback so a
        plainer OpenAI-compatible endpoint is never broken by them:

        * ``response_format`` (C-N14 — enforced structured output): a
          ``response_format`` value (e.g. ``{"type": "json_object"}`` or a
          ``json_schema`` block) passed straight through to the endpoint.
        * ``reasoning_effort`` (C-U12 — reasoning-budget knob): ``"minimal"`` /
          ``"low"`` / ``"medium"`` / ``"high"``; falls back to the
          ``LLM_REASONING_EFFORT`` global default when the caller passes None.

        If the endpoint rejects either param (400 / unsupported / unknown
        keyword), it is recorded as unsupported for this (base_url, model) and
        the call is retried without it — the request still succeeds, just
        without the enhancement. Subsequent calls skip the rejected param
        entirely.

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
        # 033 Wave-0: assemble the optional enhancement params, minus any this
        # endpoint already told us it doesn't support (probe cache). The
        # in-loop except strips any that draw a fresh rejection.
        cap_key = (getattr(resolved, "base_url", None), call_model)
        unsupported = getattr(self, "_llm_unsupported_params", {}).get(cap_key, set())
        effort = reasoning_effort if reasoning_effort is not None else getattr(
            self, "llm_reasoning_effort", None)
        effort = self._valid_reasoning_effort(effort)
        extra_kwargs: Dict[str, Any] = {}
        if response_format is not None and "response_format" not in unsupported:
            extra_kwargs["response_format"] = response_format
        if effort is not None and "reasoning_effort" not in unsupported:
            extra_kwargs["reasoning_effort"] = effort
        # 033 Wave-3 (C-D6): device-capability-aware model router. Cheap-first —
        # pick the cheapest tier that fits this task, capped by the connecting
        # device; a low-confidence response escalates one tier (below). Flag-
        # gated (default OFF) + fail-open: with the flag off, or no MODEL_TIERS
        # configured, call_model is the already-resolved default, unchanged.
        _route_tier: Optional[int] = None
        escalated = False
        if model_router.router_enabled():
            try:
                prof = self.rote.get_profile(websocket) if websocket is not None else None
                dtype = prof.device_type.value if prof is not None else None
                dec = model_router.route(
                    feature, default_model=call_model, device_type=dtype,
                    device_caps=getattr(prof, "capabilities", None))
                call_model, _route_tier = dec.model, dec.tier
            except Exception:
                logger.debug("model_router: selection failed — using default model",
                             exc_info=True)
        attempt = 0
        while attempt < self.MAX_RETRIES:
            attempt += 1
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
                kwargs.update(extra_kwargs)

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
                # Some serving stacks leak Harmony channel tokens
                # ("<|channel|>thought…") or <think> blocks into content;
                # strip them before any consumer renders or persists it.
                if _msg is not None and isinstance(getattr(_msg, "content", None), str):
                    _msg.content = strip_reasoning_markup(_msg.content)
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
                # 033 Wave-3 (C-D6): cheap-first cascade — if the router placed
                # this call on a lower tier and the response reads low-confidence
                # (hedge/refusal/empty), escalate ONE tier and re-issue once. Only
                # for prose turns (tool-call turns aren't graded this way). Bounded
                # by ``escalated`` so it happens at most once.
                if (_route_tier is not None and not escalated and not tools_desc
                        and model_router.router_enabled()
                        and not model_router.confidence_ok(getattr(_msg, "content", None))):
                    _next = model_router.escalate(_route_tier)
                    _next_model = (model_router.resolve_model(_next, resolved.model)
                                   if _next is not None else None)
                    if _next_model and _next_model != call_model:
                        escalated, _route_tier, call_model = True, _next, _next_model
                        logger.info("model_router: low-confidence → escalating to "
                                    "tier %s (%s)", model_router.tier_name(_next),
                                    _next_model)
                        attempt -= 1  # the escalation re-call isn't a retry
                        continue
                return response.choices[0].message, usage
            except Exception as e:
                error_str = str(e)

                # 033 Wave-0: did the endpoint reject one of our optional
                # enhancement params? If so, remember it for this
                # (base_url, model), strip it, and retry immediately — the
                # request itself is fine, just without the enhancement.
                drop = self._llm_unsupported_extras(error_str, extra_kwargs)
                if drop:
                    cache = getattr(self, "_llm_unsupported_params", None)
                    if cache is not None:
                        cache.setdefault(cap_key, set()).update(drop)
                    for p in drop:
                        extra_kwargs.pop(p, None)
                    logger.info(
                        "LLM endpoint rejected %s; retrying without it", sorted(drop)
                    )
                    # A capability-probe rejection is not a real failure —
                    # don't spend a retry attempt on it.
                    attempt -= 1
                    continue

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

    _REASONING_EFFORTS = ("minimal", "low", "medium", "high")

    @classmethod
    def _valid_reasoning_effort(cls, value):
        """Normalize a reasoning-effort value (C-U12). Returns the lowercased
        value if it is one of the recognized levels, else None (so an unset or
        garbage env/arg is simply not sent)."""
        if value is None:
            return None
        v = str(value).strip().lower()
        return v if v in cls._REASONING_EFFORTS else None

    @staticmethod
    def _llm_unsupported_extras(error_str: str, extra_kwargs: Dict[str, Any]) -> set:
        """033 Wave-0 capability probe: given a failed completion's error text
        and the optional enhancement params we sent, return the subset the
        endpoint appears to reject (so the caller can drop + remember them).

        Conservative: only fires on signals that look like an unsupported /
        malformed *parameter* (not a transient 5xx or an auth error). When the
        message names a specific param, only that one is dropped; when it is a
        generic "unsupported parameter" 400 that names none of ours, all active
        enhancement params are dropped (they are optional, so dropping them to
        keep the call working is always safe).
        """
        if not extra_kwargs:
            return set()
        low = (error_str or "").lower()
        # Never treat transient/auth failures as a param-capability problem.
        if any(code in low for code in ("502", "503", "504", "bad gateway",
                                        "service unavailable", "connection",
                                        "timeout", "401", "403")):
            return set()
        named = {p for p in extra_kwargs if p in low}
        if named:
            return named
        generic = any(sig in low for sig in (
            "unsupported", "unrecognized", "unexpected keyword", "unknown parameter",
            "unknown field", "not supported", "invalid parameter", "extra inputs",
            "no longer supported", "is not permitted", "unknown argument",
        ))
        if generic and ("400" in low or "param" in low or "argument" in low
                        or "field" in low or "input" in low):
            return set(extra_kwargs)
        return set()

    async def _call_llm_json(self, websocket, messages, *, schema=None,
                             schema_name: str = "result", temperature=None,
                             feature: str = "structured", reasoning_effort=None):
        """C-N14 — request enforced structured (JSON) output and parse it.

        Passes a ``response_format`` (a strict ``json_schema`` block when
        ``schema`` is given, else plain ``json_object``) through
        :meth:`_call_llm`, which probe-and-falls-back if the endpoint can't do
        it. Returns the parsed object, or ``None`` when the call failed or the
        content was not valid JSON — callers keep their existing best-effort
        JSON-repair path as the fallback, so this is always safe to adopt.
        """
        if schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        else:
            response_format = {"type": "json_object"}
        msg, _usage = await self._call_llm(
            websocket, messages, tools_desc=None, temperature=temperature,
            feature=feature, response_format=response_format,
            reasoning_effort=reasoning_effort,
        )
        content = getattr(msg, "content", None) if msg is not None else None
        if not content:
            return None
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            # Tolerate a fenced ```json block or surrounding prose.
            extracted = self._extract_json_block(content)
            if extracted is not None:
                try:
                    return json.loads(extracted)
                except (ValueError, TypeError):
                    return None
            return None

    @staticmethod
    def _extract_json_block(text: str):
        """Best-effort: pull the first balanced JSON object/array out of a
        string that may be wrapped in a ```json fence or prose. Returns the
        substring or None."""
        if not isinstance(text, str):
            return None
        s = text.strip()
        if s.startswith("```"):
            # strip a leading fence line and a trailing fence
            nl = s.find("\n")
            if nl != -1:
                s = s[nl + 1:]
            if s.rstrip().endswith("```"):
                s = s.rstrip()[:-3]
            s = s.strip()
        starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
        if not starts:
            return None
        start = min(starts)
        open_ch = s[start]
        close_ch = "}" if open_ch == "{" else "]"
        depth = 0
        for i in range(start, len(s)):
            if s[i] == open_ch:
                depth += 1
            elif s[i] == close_ch:
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        return None

    @staticmethod
    def _tool_result_to_llm_content(res) -> str:
        """033 Wave-0 (C-N15 — two-tier tool output): the text a tool result
        contributes to the LLM conversation.

        A tool may split its result into a short model-facing tier and a larger
        renderer-only tier. Precedence:

        1. ``_model_digest`` — the explicit model-facing digest. When present it
           is the ONLY thing the LLM sees; the render-only payload
           (``_ui_components`` / ``_data`` / raw fetched text) never enters the
           model. This both cuts tokens and closes a prompt-injection channel
           (untrusted fetched/parsed content stops reaching the reasoning loop).
        2. ``_data`` — the existing convention; serialized as today.
        3. otherwise the whole result is serialized — unchanged behavior.

        Defaulting to (2)/(3) keeps every current tool byte-identical; the
        digest tier is purely opt-in for a tool that sets ``_model_digest``.
        """
        if res is None:
            return "No output"
        if getattr(res, "error", None):
            return f"Error: {res.error.get('message')}"
        result = getattr(res, "result", None)
        if not result:
            return "No output"
        if isinstance(result, dict) and result.get("_model_digest") is not None:
            digest = result["_model_digest"]
            return digest if isinstance(digest, str) else json.dumps(digest)
        if isinstance(result, dict) and "_data" in result:
            return json.dumps(result["_data"])
        return json.dumps(result)

    @staticmethod
    def _result_has_model_digest(res) -> bool:
        """True when a tool result carries a C-N15 ``_model_digest`` — i.e. the
        LLM-visible text is tool-authored (trusted) and should NOT be wrapped as
        untrusted by C-S4 datamarking."""
        result = getattr(res, "result", None)
        return isinstance(result, dict) and result.get("_model_digest") is not None

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

            summary_text = strip_reasoning_markup(response.choices[0].message.content or "")
            summary_text = summary_text.strip()

            if summary_text:
                # Feature 029 (FR-027): contextual title over the constant
                # "Summary" — derived from the summary's own first heading.
                return [
                    Card(title=self._derive_chat_title(summary_text, default="Round results"),
                         content=[
                             Text(content=summary_text, variant="body")
                         ]).to_dict()
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

    def _find_tool_owner(self, tool_name: str) -> Optional[str]:
        """Return the agent_id that owns ``tool_name`` (any registered agent), or None.

        Searches every entry in ``self.agent_cards`` regardless of filter state —
        the goal is to identify the owner so we can name it in the disabled-tool
        alert, not to gate dispatch.
        """
        if not tool_name:
            return None
        for agent_id, card in self.agent_cards.items():
            for skill in getattr(card, "skills", []) or []:
                if getattr(skill, "id", None) == tool_name:
                    return agent_id
        return None

    def _diagnose_disabled_tool(
        self,
        tool_name: str,
        user_id: Optional[str],
        chat_id: Optional[str],
    ) -> ToolDiagnostic:
        """Determine why ``tool_name`` may be unavailable for ``user_id`` in ``chat_id``.

        Mirrors the filter stack in handle_chat_message's tool-list build
        (orchestrator.py around lines 2080–2140). Priority order — first match wins:
        UNKNOWN_TOOL > AGENT_DISABLED_BY_USER > SECURITY_BLOCKED > PERMISSION_DENIED >
        DISABLED_IN_PICKER > ENABLED.
        """
        agent_id = self._find_tool_owner(tool_name)
        if not agent_id:
            return ToolDiagnostic(
                status=ToolDiagnosticStatus.UNKNOWN_TOOL,
                agent_id=None,
                agent_display_name=None,
                reason=None,
            )
        card = self.agent_cards.get(agent_id)
        agent_display = (
            getattr(card, "name", None) or agent_id if card is not None else agent_id
        )

        # 1) User has disabled the whole agent.
        if user_id:
            try:
                disabled = set(self.history.db.get_user_disabled_agents(user_id))
            except Exception:  # pragma: no cover — defensive
                disabled = set()
            if agent_id in disabled:
                return ToolDiagnostic(
                    status=ToolDiagnosticStatus.AGENT_DISABLED_BY_USER,
                    agent_id=agent_id,
                    agent_display_name=agent_display,
                    reason=None,
                )

        # 2) System-blocked (proactive security review).
        flags = getattr(self, "security_flags", {}).get(agent_id, {}) or {}
        flag = flags.get(tool_name) or {}
        if flag.get("blocked"):
            return ToolDiagnostic(
                status=ToolDiagnosticStatus.SECURITY_BLOCKED,
                agent_id=agent_id,
                agent_display_name=agent_display,
                reason=flag.get("reason"),
            )

        # 3) Permission / scope denial.
        if user_id:
            try:
                allowed = self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name)
            except Exception:  # pragma: no cover — defensive
                allowed = True
            if not allowed:
                return ToolDiagnostic(
                    status=ToolDiagnosticStatus.PERMISSION_DENIED,
                    agent_id=agent_id,
                    agent_display_name=agent_display,
                    reason=None,
                )

        # 4) Per-chat tool picker.
        if user_id and chat_id:
            try:
                bound_agent_id = self.history.db.get_chat_agent(chat_id)
            except Exception:  # pragma: no cover — defensive
                bound_agent_id = None
            if bound_agent_id is not None:
                try:
                    saved = self.history.db.get_user_tool_selection(user_id, bound_agent_id)
                except Exception:  # pragma: no cover — defensive
                    saved = None
                if saved is not None and len(saved) > 0 and tool_name not in saved:
                    return ToolDiagnostic(
                        status=ToolDiagnosticStatus.DISABLED_IN_PICKER,
                        agent_id=agent_id,
                        agent_display_name=agent_display,
                        reason=None,
                    )

        return ToolDiagnostic(
            status=ToolDiagnosticStatus.ENABLED,
            agent_id=agent_id,
            agent_display_name=agent_display,
            reason=None,
        )

    @staticmethod
    def _alert_for_disabled_tool(diag: ToolDiagnostic, tool_name: str) -> Alert:
        """Render a user-facing Alert explaining why ``tool_name`` was unavailable.

        Variants follow existing conventions: 'warning' for things the user
        can self-correct (picker, agent toggle, permission), 'error' for
        admin-blocked or unknown-tool states, 'info' for the surprising
        ENABLED-but-format-mismatch case (only reachable from the leak path).
        """
        agent_label = diag.agent_display_name or diag.agent_id or "an installed agent"
        if diag.status is ToolDiagnosticStatus.DISABLED_IN_PICKER:
            return Alert(
                message=(
                    f"The assistant tried to use the **{tool_name}** tool "
                    f"(from the **{agent_label}** agent), but that tool is "
                    f"turned off in your tool picker for this chat. "
                    f"Re-enable it in the picker to use it."
                ),
                variant="warning",
                title="Tool disabled",
            )
        if diag.status is ToolDiagnosticStatus.AGENT_DISABLED_BY_USER:
            return Alert(
                message=(
                    f"The assistant tried to use the **{tool_name}** tool, "
                    f"but the **{agent_label}** agent is disabled. "
                    f"Open Agents settings and turn it on to use this tool."
                ),
                variant="warning",
                title="Agent disabled",
            )
        if diag.status is ToolDiagnosticStatus.PERMISSION_DENIED:
            return Alert(
                message=(
                    f"The assistant tried to use the **{tool_name}** tool "
                    f"(from the **{agent_label}** agent), but it is restricted "
                    f"by permissions. Open the agent's permissions panel and "
                    f"grant the right scope."
                ),
                variant="warning",
                title="Tool restricted",
            )
        if diag.status is ToolDiagnosticStatus.SECURITY_BLOCKED:
            reason = diag.reason or "system policy"
            return Alert(
                message=(
                    f"The assistant tried to use the **{tool_name}** tool, "
                    f"but it is system-blocked: {reason}. An administrator "
                    f"must unblock it before it can be used."
                ),
                variant="error",
                title="Tool blocked",
            )
        if diag.status is ToolDiagnosticStatus.UNKNOWN_TOOL:
            return Alert(
                message=(
                    f"The assistant tried to use a tool named **{tool_name}**, "
                    f"but no installed agent provides it. The model may have "
                    f"hallucinated the name — try rephrasing your request."
                ),
                variant="error",
                title="Unknown tool",
            )
        # ENABLED — only reachable from the leak path (not from the dispatch
        # gate, which short-circuits before this is rendered).
        return Alert(
            message=(
                f"The assistant emitted tool-call markup that this orchestrator "
                f"doesn't recognize. The **{tool_name}** tool exists and is "
                f"enabled — try switching to a model that uses native tool "
                f"calling, or configure your LLM endpoint to emit OpenAI-format "
                f"tool calls."
            ),
            variant="info",
            title="Unrecognized tool-call format",
        )

    def _diagnose_leaked_tool_calls(
        self,
        content: str,
        user_id: Optional[str],
        chat_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Inspect ``content`` for leaked tool-call markup and return one Alert
        (as a serialized component dict) per distinct tool name found.

        Only returns alerts for tool names actually parsed out of the markup —
        if the leak regex matches but no recognizable tool name can be
        extracted, returns an empty list (the existing strip behavior remains
        the only mitigation for that case).
        """
        if not content:
            return []
        # Quick pre-filter: only walk extractors when at least one leak pattern fired.
        if not any(p.search(content) for p in _LEAKED_TOOL_CALL_PATTERNS):
            return []
        names = _tool_names_from_leak(content)
        if not names:
            return []
        alerts: List[Dict[str, Any]] = []
        for tool_name in names:
            diag = self._diagnose_disabled_tool(tool_name, user_id, chat_id)
            alert = self._alert_for_disabled_tool(diag, tool_name)
            alerts.append(alert.to_dict())
        return alerts

    def _is_long_running_tool(self, agent_id: Optional[str], tool_name: str) -> bool:
        """Return True if the agent's card declares this tool as long-running (FR-026)."""
        if not agent_id:
            return False
        card = self.agent_cards.get(agent_id)
        if not card:
            return False
        md = getattr(card, "metadata", {}) or {}
        return tool_name in (md.get("long_running_tools") or [])

    def _policy_roles(self, websocket) -> List[str]:
        """Best-effort session roles for the C-S3 policy engine. Handles a flat
        ``roles`` claim or the Keycloak ``realm_access.roles`` shape; returns
        ``[]`` when unavailable (role-predicated rules simply won't match)."""
        claims = self.ui_sessions.get(websocket) if websocket is not None else None
        if not isinstance(claims, dict):
            return []
        roles = claims.get("roles")
        if not roles:
            ra = claims.get("realm_access")
            roles = ra.get("roles") if isinstance(ra, dict) else None
        return list(roles) if isinstance(roles, (list, tuple)) else []

    def _taint_tracker(self, chat_id: Optional[str]):
        """Per-chat C-S2 taint tracker (the data-flow scope), lazily created."""
        store = getattr(self, "_taint_trackers", None)
        if store is None:
            store = {}
            self._taint_trackers = store
        key = chat_id or "_global"
        tracker = store.get(key)
        if tracker is None:
            from orchestrator.taint import TaintTracker
            tracker = TaintTracker()
            store[key] = tracker
        return tracker

    async def execute_single_tool(self, websocket, tool_call, tool_to_agent: Dict, chat_id: str = None, user_id: str = None, tool_to_unqualified: Optional[Dict[str, str]] = None) -> Optional[MCPResponse]:
        """Execute a single tool call and render its UI components. Returns the Result object."""
        # The LLM may have emitted a qualified name (e.g. "forecaster-1__submit_dataset")
        # when two agents own a tool of the same id. Resolve the bare skill id so the
        # owning agent receives the name it actually registered.
        llm_tool_name = tool_call.function.name
        if tool_to_unqualified and llm_tool_name in tool_to_unqualified:
            tool_name = tool_to_unqualified[llm_tool_name]
        else:
            tool_name = llm_tool_name
        try:
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        except json.JSONDecodeError:
            args = {}

        # Feature 027 — orchestrator meta-tools dispatch before the agent
        # gates (the pseudo-agent has no scopes/credentials; ownership and
        # approval gates live inside the handler — contracts/agentic-creation.md).
        agent_id = tool_to_agent.get(llm_tool_name)
        if agent_id is None and tool_to_agent:
            # 030: weak models routinely mangle hyphen/underscore in
            # collision-qualified names ("web_research-1__web_search" for
            # "web-research-1__web_search"), which used to dead-end as
            # "No agent available" — and then bait the model into creating
            # a duplicate capability. Recover deterministically when the
            # normalized form matches exactly ONE offered tool.
            wanted = llm_tool_name.replace("-", "_").lower()
            matches = [k for k in tool_to_agent
                       if k.replace("-", "_").lower() == wanted]
            if len(matches) == 1:
                logger.info(
                    "Tool name normalized: %r -> %r", llm_tool_name, matches[0])
                llm_tool_name = matches[0]
                tool_name = (tool_to_unqualified or {}).get(llm_tool_name, tool_name)
                agent_id = tool_to_agent.get(llm_tool_name)
        if agent_id == "__orchestrator__":
            from orchestrator import agentic_creation
            return await agentic_creation.handle_meta_tool(
                self, tool_name, args, user_id=user_id, chat_id=chat_id, websocket=websocket
            )
        if agent_id == "__scheduler__":
            # Feature 030 — scheduling meta-tool: validation + consent card
            # only; creation happens in the schedule_decision ui_event.
            from orchestrator import scheduling_chat
            return await scheduling_chat.handle_meta_tool(
                self, tool_name, args, user_id=user_id, chat_id=chat_id, websocket=websocket
            )
        if agent_id == "__memory__":
            # 030 — memory meta-tools: execute immediately (PHI-gated), no card.
            from orchestrator import memory_chat
            return await memory_chat.handle_meta_tool(
                self, tool_name, args, user_id=user_id, chat_id=chat_id, websocket=websocket
            )

        # System-level security block (proactive security review)
        agent_flags = self.security_flags.get(agent_id, {}) if agent_id else {}
        if agent_id and tool_name in agent_flags and agent_flags[tool_name].get("blocked"):
            reason = agent_flags[tool_name].get("reason", "Security threat detected")
            err_msg = f"Tool '{tool_name}' is system-blocked: {reason}"
            logger.warning(f"Security block: agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="error")
            await self.send_ui_render(websocket, [alert.to_dict()], target="chat")
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_dict()]
            )

        # Permission enforcement gate (RFC 8693 delegation)
        if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
            err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
            logger.warning(f"Permission denied: user={user_id} agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="warning")
            await self.send_ui_render(websocket, [alert.to_dict()])
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_dict()]
            )

        # 033 Wave-4 (C-S3): deterministic pre-action policy engine — an ordered,
        # fail-closed rule chain (data, admin-extensible via POLICY_RULES) on top
        # of the permission gate. Default OFF + no seed rules ⇒ purely additive.
        # deny/confirm block the call; rewrite redacts args before execution.
        if user_id:
            from orchestrator import policy
            if policy.policy_enabled():
                try:
                    decision = policy.evaluate_policy(
                        policy.load_rules(),
                        {"tool": tool_name, "agent": agent_id, "user_id": user_id,
                         "roles": self._policy_roles(websocket), "args": args})
                except Exception:
                    logger.debug("policy: evaluation failed — allowing", exc_info=True)
                    decision = policy.PolicyDecision()
                # 033 C-S8: a require_token rule demands a valid single-use
                # transaction token bound to (agent, user, tool, hash(args)).
                # Fail-closed — missing/tampered/expired/replayed ⇒ deny.
                if decision.effect == policy.REQUIRE_TOKEN:
                    from orchestrator import transaction_token as _txn
                    token = args.get("_txn_token") if isinstance(args, dict) else None
                    ok_tok, why = _txn.verify_and_consume(
                        _txn.default_store(), token, agent_id or "", user_id,
                        tool_name, args)
                    if not ok_tok:
                        msg = decision.reason or (
                            f"'{tool_name}' needs a valid one-time authorization "
                            f"token ({why}).")
                        logger.warning("policy.require_token user=%s tool=%s rule=%s reason=%s",
                                       user_id, tool_name, decision.rule_id, why)
                        alert = Alert(message=msg, variant="warning")
                        await self.send_ui_render(websocket, [alert.to_dict()])
                        return MCPResponse(error={"message": msg, "retryable": False},
                                           ui_components=[alert.to_dict()])
                elif decision.effect in (policy.DENY, policy.CONFIRM):
                    msg = decision.reason or (
                        f"'{tool_name}' needs confirmation before it can run."
                        if decision.effect == policy.CONFIRM
                        else f"'{tool_name}' was blocked by an access policy.")
                    logger.warning("policy.%s user=%s tool=%s rule=%s",
                                   decision.effect, user_id, tool_name, decision.rule_id)
                    alert = Alert(message=msg, variant="warning")
                    await self.send_ui_render(websocket, [alert.to_dict()])
                    return MCPResponse(error={"message": msg, "retryable": False},
                                       ui_components=[alert.to_dict()])
                if decision.args is not None:
                    args = decision.args  # rewritten (e.g. a secret arg redacted)
                # Never forward a consumed authorization token to the agent.
                if isinstance(args, dict) and "_txn_token" in args:
                    args = {k: v for k, v in args.items() if k != "_txn_token"}

        # 033 Wave-4 (C-S2): value-level taint/data-flow gate. If this call is a
        # write/egress SINK and its arguments carry untrusted-tainted values
        # (effective trust = min over data ancestors, recorded from prior
        # untrusted-source outputs — survives multi-hop laundering), refuse it.
        # Flag-gated (default OFF) + fail-open: unknown values are trusted, so a
        # call with only constants/user intent always passes.
        if user_id:
            from orchestrator import taint as _taint
            if _taint.taint_enabled() and _taint.is_sink(agent_id, tool_name):
                tracker = self._taint_tracker(chat_id)
                trust = tracker.effective_trust_of_args(args)
                if _taint.check_flow(trust) == "deny":
                    msg = (f"'{tool_name}' was blocked: it would send untrusted "
                           f"data (from a web/third-party source) into a "
                           f"write/egress action.")
                    logger.warning("taint.deny user=%s tool=%s agent=%s trust=%s",
                                   user_id, tool_name, agent_id, _taint.trust_name(trust))
                    alert = Alert(message=msg, variant="warning")
                    await self.send_ui_render(websocket, [alert.to_dict()])
                    return MCPResponse(error={"message": msg, "retryable": False},
                                       ui_components=[alert.to_dict()])

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

        # 5th gate (015): when no `agent_id` was resolved via `tool_to_agent` —
        # which happens because the tool was filtered out at chat-time tool-list
        # construction — see whether the tool actually EXISTS on a registered
        # agent and surface a friendly disabled-tool alert. This catches the
        # case where the model emitted a call for a tool the user disabled in
        # the picker (or whose owning agent they disabled wholesale).
        if not agent_id and tool_name:
            owner = self._find_tool_owner(tool_name)
            if owner is not None:
                diag = self._diagnose_disabled_tool(tool_name, user_id, chat_id)
                alert = self._alert_for_disabled_tool(diag, tool_name)
                logger.info(
                    "Dispatch blocked by disabled-tool gate: tool=%s owner=%s status=%s user=%s chat=%s",
                    tool_name, owner, diag.status.value, user_id, chat_id,
                )
                await self.send_ui_render(websocket, [alert.to_dict()], target="chat")
                return MCPResponse(
                    error={"message": alert.message, "retryable": False},
                    ui_components=[alert.to_dict()],
                )

        if not agent_id or (agent_id not in self.agents and agent_id not in self.a2a_clients):
            err_msg = f"No agent available for tool '{tool_name}'"
            await self.send_ui_render(websocket, [
                Alert(message=err_msg, variant="error").to_dict()
            ], target="chat")
            return MCPResponse(error={"message": err_msg})

        # RFC 8693 delegation: generate a scoped token excluding system-blocked tools
        # The delegation token constrains what the agent can do even if it's compromised
        if user_id and agent_id:
            delegation_token = await self._get_delegation_token(websocket, agent_id, user_id)
            if delegation_token:
                args["_delegation_token"] = delegation_token
            elif self._delegation_required():
                # Feature 030 / Constitution VII: agents MUST act under RFC
                # 8693 delegated tokens. The walkthrough found the deployed
                # realm missing the tools:* client scopes — every exchange
                # failed invalid_scope and dispatch silently proceeded
                # UNSCOPED. Production posture now fails closed with an
                # actionable operator message; development keeps the
                # fail-open behavior (warned once per agent) so local stacks
                # without a fully configured realm still work.
                err_msg = (
                    "Tool execution is disabled: delegated authorization "
                    "(RFC 8693 token exchange) is unavailable for agent "
                    f"'{agent_id}'. An operator must register the tools:* "
                    "client scopes on the identity provider (see "
                    "docs/keycloak-realm-settings.md), or set "
                    "DELEGATION_REQUIRED=false to accept unscoped dispatch."
                )
                logger.error(
                    "Delegation required but unavailable: agent=%s user=%s — refusing dispatch",
                    agent_id, user_id,
                )
                await self.send_ui_render(websocket, [
                    Alert(message=err_msg, variant="error").to_dict()
                ], target="chat")
                return MCPResponse(error={"message": err_msg, "retryable": False})

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

        # 015-external-ai-agents: concurrency cap for long-running tools (FR-026).
        # Acquired here so a 4th concurrent attempt is rejected without ever
        # touching the upstream service. Released either on dispatch error
        # (below) or by the terminal-phase ToolProgress handler.
        cap_job_id: Optional[str] = None
        if user_id and agent_id and self._is_long_running_tool(agent_id, tool_name):
            cap_job_id = f"cap_{tool_name}_{_uuid.uuid4().hex[:8]}"
            acquired = await self.concurrency_cap.acquire(user_id, agent_id, cap_job_id)
            if not acquired:
                inflight = self.concurrency_cap.inflight_jobs(user_id, agent_id)
                max_n = self.concurrency_cap.max_per_user_agent
                err_msg = (
                    f"You already have {max_n} jobs running on '{agent_id}'. "
                    f"Wait for one to finish or cancel one before starting another. "
                    f"(Running: {', '.join(inflight)})"
                )
                logger.info(
                    "ConcurrencyCap rejected dispatch: user=%s agent=%s tool=%s",
                    user_id, agent_id, tool_name,
                )
                alert = Alert(message=err_msg, variant="warning")
                await self.send_ui_render(websocket, [alert.to_dict()], target="chat")
                return MCPResponse(
                    error={"message": err_msg, "retryable": False},
                    ui_components=[alert.to_dict()],
                )
            args["_cap_job_id"] = cap_job_id
            self._pending_cap_entries[cap_job_id] = (user_id, agent_id)
            # Remember the chat this long-running job belongs to so its progress
            # and final result are delivered to (and persisted in) that chat for
            # any client that returns to it later (014/015 + 028).
            self._job_context[cap_job_id] = {
                "user_id": user_id,
                "agent_id": agent_id,
                "chat_id": chat_id,
                "tool_name": tool_name,
            }

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

        # 033 Wave-4 (C-S2): record the call's output taint so it propagates
        # through the chain. The output's trust = min(source trust, input trust):
        # an untrusted web/third-party source taints its output, and any tool
        # that consumed untrusted input passes the taint on (laundering survives
        # an intermediate hop). Flag-gated; best-effort (never affects the call).
        if user_id and result is not None and result.error is None:
            try:
                from orchestrator import taint as _taint
                if _taint.taint_enabled():
                    tracker = self._taint_tracker(chat_id)
                    src = _taint.classify_source(agent_id, tool_name)
                    inp = tracker.effective_trust_of_args(args)
                    tracker.record_output(result.ui_components, src, inp)
            except Exception:
                logger.debug("taint: output record failed", exc_info=True)

        # 015-external-ai-agents: release cap if the dispatch errored or returned
        # nothing — there will be no terminal ToolProgress to do it. Successful
        # long-running starts keep the slot held; the JobPoller's terminal
        # ToolProgress will release it via the handler in handle_agent_messages.
        if cap_job_id and (result is None or (result is not None and result.error)):
            try:
                await self.concurrency_cap.release(user_id, agent_id, cap_job_id)
            finally:
                self._pending_cap_entries.pop(cap_job_id, None)

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
        # collects the round's components and either runs the adaptive UI
        # designer over them or flat-appends them to the workspace (029).
        if result and result.error:
            # Errors are still shown immediately so the user knows something went wrong
            err_msg = result.error.get('message', 'Unknown error')
            await self.send_ui_render(websocket, [
                Alert(message=f"Tool '{tool_name}' failed: {err_msg}", variant="error").to_dict()
            ], target="chat")

            # Auto-fix: if this is a draft agent, attempt to fix the tool
            # error automatically. 030: the draft check now gates the STATUS
            # too — previously every errored live tool flashed a misleading
            # "Auto-fixing..." even though auto_fix only acts on drafts.
            if (agent_id and hasattr(self, 'lifecycle_manager')
                    and self.lifecycle_manager._get_draft_by_agent_id(agent_id)):
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
                            Alert(message=f"Auto-fix applied for '{tool_name}'. Agent restarted — try again.", variant="info").to_dict()
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

    async def execute_parallel_tools(self, websocket, tool_calls, tool_to_agent: Dict, chat_id: str = None, user_id: str = None, tool_to_unqualified: Optional[Dict[str, str]] = None) -> List[Optional[MCPResponse]]:
        """Execute multiple tool calls with concurrency safety.

        When tool_concurrency_safety is enabled, read-only tools (tools:read,
        tools:search scopes) run in parallel while write/system tools run serially
        after the parallel batch completes.  This prevents race conditions when
        two write tools target the same agent.
        """
        # Phase 1: Prepare all tool calls (args, permissions, credentials)
        prepared = []  # list of (index, tc, tool_name, agent_id, args | None, error_coro | None)

        for idx, tc in enumerate(tool_calls):
            # Same qualified→unqualified resolution as the single-tool path:
            # an LLM-emitted name like "forecaster-1__submit_dataset" is mapped
            # back to the bare skill id "submit_dataset" before dispatch so the
            # owning agent receives the name it registered.
            llm_tool_name = tc.function.name
            if tool_to_unqualified and llm_tool_name in tool_to_unqualified:
                tool_name = tool_to_unqualified[llm_tool_name]
            else:
                tool_name = llm_tool_name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            if chat_id:
                args = self._map_file_paths(chat_id, args, user_id=user_id)
                args["session_id"] = chat_id
                if user_id:
                    args["user_id"] = user_id

            agent_id = tool_to_agent.get(llm_tool_name)

            # Feature 027 — meta-tools dispatch directly (see execute_single_tool).
            if agent_id == "__orchestrator__":
                from orchestrator import agentic_creation
                prepared.append((idx, tc, tool_name, agent_id, None,
                                 agentic_creation.handle_meta_tool(
                                     self, tool_name, args, user_id=user_id,
                                     chat_id=chat_id, websocket=websocket)))
                continue

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
                                       ui_components=[Alert(message=msg, variant="error").to_dict()])
                prepared.append((idx, tc, tool_name, agent_id, None, _sec_err()))
                continue

            # Permission check
            if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
                err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
                logger.warning(f"Permission denied (parallel): user={user_id} agent={agent_id} tool={tool_name}")
                async def _perm_err(msg=err_msg):
                    return MCPResponse(error={"message": msg, "retryable": False},
                                       ui_components=[Alert(message=msg, variant="error").to_dict()])
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
                error_components.append(Alert(message=f"Tool error: {str(result)}", variant="error").to_dict())
            else:
                final_results.append(result)
                if result and result.error:
                    error_components.append(Alert(message=f"Tool '{tool_names[i]}' failed: {result.error.get('message')}", variant="error").to_dict())

        # Only render errors immediately — successful results are batched by caller
        if error_components:
            await self.send_ui_render(websocket, error_components)

        # Auto-fix: attempt to fix draft agent tool errors
        if hasattr(self, 'lifecycle_manager'):
            for i, result in enumerate(final_results):
                if result and result.error:
                    t_name = tool_names[i] if i < len(tool_names) else None
                    a_id = tool_to_agent.get(t_name) if t_name else None
                    # 030: status only when auto-fix can actually act (drafts).
                    if a_id and self.lifecycle_manager._get_draft_by_agent_id(a_id):
                        try:
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "fixing",
                                "message": f"Auto-fixing tool '{t_name}'..."
                            }))
                            await self.lifecycle_manager.auto_fix_tool_error(
                                a_id, t_name, result.error.get('message', ''), websocket
                            )
                            await self.send_ui_render(websocket, [
                                Alert(message=f"Auto-fix applied for '{t_name}'. Agent restarted — try again.", variant="info").to_dict()
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
            result = await self.execute_tool_and_wait(
                agent_id, tool_name, args,
                timeout=TOOL_TIMEOUT_OVERRIDES.get(tool_name, 30.0),
                ui_websocket=websocket)
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

    def _delegation_required(self) -> bool:
        """Whether tool dispatch must refuse to proceed without a delegated token.

        Constitution VII mandates RFC 8693 delegated tokens for agents.
        Default: required in production posture (``ASTRAL_ENV`` unset or not
        ``development`` — the project's fail-closed convention), optional in
        development. ``DELEGATION_REQUIRED`` overrides either way.
        """
        override = os.getenv("DELEGATION_REQUIRED", "").strip().lower()
        if override in ("1", "true", "yes"):
            return True
        if override in ("0", "false", "no"):
            return False
        return os.getenv("ASTRAL_ENV", "").strip().lower() != "development"

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
                # Feature 030: log loudly ONCE per agent instead of warning on
                # every call — a misconfigured realm previously produced an
                # identical warning per tool dispatch (pure noise) while the
                # dispatch itself proceeded unscoped.
                if not hasattr(self, "_delegation_failed_agents"):
                    self._delegation_failed_agents = set()
                if agent_id not in self._delegation_failed_agents:
                    self._delegation_failed_agents.add(agent_id)
                    logger.error(
                        "RFC 8693 token exchange failing for agent=%s (logged once; "
                        "see docs/keycloak-realm-settings.md): %s", agent_id, result)
                else:
                    logger.debug(f"Delegation token exchange failed for agent={agent_id}: {result}")
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
                # Feature 037: refresh the server-driven, ROTE-adapted surface.
                tasks.append(self._push_history_surface(c, chats=history_list))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _push_history_surface(self, websocket, *, chats=None, loading: bool = False) -> None:
        """Feature 037: render the chat-history surface (skeleton while loading,
        else the recent-chats list) and push it ROTE-adapted to the client's
        history region via send_ui_render(target="history"). Fail-soft — a
        surface error never breaks history delivery."""
        try:
            from orchestrator.history_surface import (
                history_skeleton_components,
                history_surface_components,
            )
            comps = (history_skeleton_components() if loading
                     else history_surface_components(chats or []))
            await self.send_ui_render(websocket, comps, target="history")
        except Exception:
            logger.debug("history surface push failed", exc_info=True)

    @staticmethod
    def _derive_chat_title(content: str, default: str = "Response") -> str:
        """Feature 029 (FR-027): a contextual chat-card title.

        Prefers the response's own first markdown heading; falls back to the
        provided default. Never invents content — purely derivational.
        """
        for line in (content or "").splitlines():
            line = line.strip()
            if line.startswith("#"):
                heading = line.lstrip("#").strip().rstrip(":")
                if heading:
                    return heading[:80]
        return default

    def _chat_narrative(self, content: str) -> List[Dict]:
        """Feature 029 (FR-027): the final-turn chat-panel narrative.

        Replaces the constant ``Card(title="Analysis")``: short plain answers
        render as bare markdown (no card chrome); longer ones get a card with
        a title derived from the response itself.
        """
        text = (content or "").strip()
        if len(text) <= 280 and "\n\n" not in text and not text.startswith("#"):
            return [Text(content=text, variant="markdown").to_dict()]
        return [
            Card(title=self._derive_chat_title(text), content=[
                Text(content=text, variant="markdown")
            ]).to_dict()
        ]

    def _canvas_components(self, chat_id: str, user_id: str) -> List[Dict]:
        """Feature 029: the canvas as one component list — designed arrangements
        materialized in place, unclaimed components flat — in shared position
        order. With no arrangements this is exactly the pre-029 flat canvas."""
        layouts = self.workspace.live_layouts(chat_id, user_id)
        if not layouts:
            return self.workspace.live_components(chat_id, user_id)
        from orchestrator import ui_designer
        from orchestrator.workspace import iter_layout_refs
        by_id: Dict[str, Dict] = {}
        comp_entries = []
        for row in self.workspace.live_rows(chat_id, user_id):
            data = row.get("component_data")
            if not isinstance(data, dict):
                continue
            cid = row.get("component_id")
            if cid and not data.get("component_id"):
                data["component_id"] = cid
            if cid:
                by_id[cid] = data
            comp_entries.append((row.get("position") or 0, cid, data))
        claimed = set()
        for lay in layouts:
            claimed |= set(iter_layout_refs(lay["layout"]))
        stream: List = [
            (pos, 0, [data]) for pos, cid, data in comp_entries
            if not (cid and cid in claimed)
        ]
        stream += [
            (lay.get("position") or 0, 1, ui_designer.materialize(lay["layout"], by_id))
            for lay in layouts
        ]
        out: List[Dict] = []
        for _pos, _kind, payload in sorted(stream, key=lambda t: (t[0], t[1])):
            out.extend(payload)
        return out

    async def _push_canvas(self, chat_id: str, user_id: str, originating_ws=None):
        """Full-canvas ui_render (materialized arrangements) to every socket of
        the user on this chat — the same fan-out + per-socket ROTE adaptation
        the legacy reconciliation path uses."""
        components = self._canvas_components(chat_id, user_id)
        targets = [
            ws for ws in self.ui_clients
            if self._get_user_id(ws) == user_id
            and self._ws_active_chat.get(id(ws)) == chat_id
        ]
        if originating_ws is not None and originating_ws not in targets:
            targets.append(originating_ws)
        for ws in targets:
            await self.send_ui_render(ws, components)

    async def _deliver_round_components(self, websocket, components: List[Dict], chat_id: str,
                                        user_id: str, *, user_request: str = "") -> List[Dict]:
        """Feature 029: deliver one round's rich components to the canvas.

        Rounds with ≥2 components (flag-gated) get the adaptive designer pass:
        components persist first (identities assigned by the unchanged 028
        upsert), one LLM call arranges them (reference leaves + garnish), the
        arrangement persists, and the full designed canvas fans out. EVERY
        failure mode falls back to the legacy flat append — same persistence,
        same ``ui_upsert`` delivery, no user-visible error (FR-022).
        """
        from orchestrator import ui_designer
        from orchestrator.workspace import layout_key_for
        timeline = self._ws_timeline_mode.get(id(websocket), False)
        if not chat_id or not ui_designer.should_design(components, timeline_mode=timeline):
            return await self._send_or_replace_components(websocket, components, chat_id, user_id)
        try:
            ops = self.workspace.upsert(chat_id, user_id, components)
        except Exception:
            logger.exception("workspace upsert failed — falling back to transient render")
            await self.send_ui_render(websocket, components)
            return []
        layout = None
        try:
            turn_marker = str(self.history.get_latest_message_id(chat_id, user_id=user_id) or "")
            layout_key = layout_key_for(chat_id, turn_marker)

            _designer_pass = {"n": 0}

            async def _designer_llm(messages):
                # Same credential resolution as the round itself (feature 006,
                # websocket-scoped) and the same llm_call auditing (FR-028).
                # Feature 030: each pass announces itself — the walkthrough
                # measured an 83 s frame-silent gap while the designer worked
                # behind a stale status line.
                _designer_pass["n"] += 1
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "thinking",
                        "message": f"Designing your layout (pass {_designer_pass['n']} of "
                                   f"{ui_designer.designer_max_rounds()})...",
                    }))
                except Exception:
                    logger.debug("designer progress status send failed", exc_info=True)
                msg, _usage = await self._call_llm(
                    websocket, messages, tools_desc=None,
                    temperature=0.2, feature="ui_designer",
                )
                return (msg.content or "") if msg else None

            from webrender import allowed_primitive_types
            # Feature 039 (C-U2): the current persisted arrangement for this
            # layout_key (if any) lets the designer avoid re-arranging it for a
            # marginal gain.
            _current_layout = None
            try:
                for _lay in self.workspace.live_layouts(chat_id, user_id):
                    if _lay.get("layout_key") == layout_key:
                        _current_layout = _lay.get("layout")
                        break
            except Exception:
                _current_layout = None
            layout = await ui_designer.design_round(
                user_request=user_request,
                round_components=components,
                canvas_rows=self.workspace.live_rows(chat_id, user_id),
                chat_id=chat_id,
                layout_key=layout_key,
                allowed_types=set(allowed_primitive_types()),
                llm_call=_designer_llm,
                current_layout=_current_layout,
            )
        except Exception:
            logger.exception("ui_designer crashed — falling back to flat append")
            layout = None
        delivered_designed = False
        if layout:
            try:
                self.workspace.upsert_layout(chat_id, user_id, layout_key, layout)
                await self._push_canvas(chat_id, user_id, originating_ws=websocket)
                delivered_designed = True
            except Exception:
                logger.exception("designed canvas delivery failed — falling back to ui_upsert")
        if not delivered_designed:
            await self.send_ui_upsert(websocket, chat_id, user_id, ops)
        # Audit the mutation (FR-023) — identical to the flat path.
        try:
            from audit.hooks import record_workspace_event
            for op in ops:
                asyncio.create_task(record_workspace_event(
                    user_id=user_id,
                    action="component_updated" if not op.get("created") else "component_added",
                    chat_id=chat_id, component_id=op.get("component_id"),
                ))
        except Exception:
            logger.debug("workspace audit failed", exc_info=True)
        return ops

    async def _send_or_replace_components(self, websocket, components: List[Dict], chat_id: str,
                                          user_id: str, *, force_component_id: Optional[str] = None) -> List[Dict]:
        """Feature 028: persist rich components into the chat's workspace under
        stable identities and push partial ``ui_upsert`` updates (research D12).

        Replaces the pre-028 ``(tool, agent)`` matcher whose
        ``components_replaced`` messages the thin client silently dropped —
        the disappearing-UI defect. Updates morph in place on every socket of
        this user viewing the chat (FR-040); new components append. Returns
        the persisted op list so callers can snapshot the turn (FR-030).
        """
        if not components:
            return []
        if not chat_id:
            await self.send_ui_render(websocket, components)
            return []
        try:
            ops = self.workspace.upsert(chat_id, user_id, components,
                                        force_component_id=force_component_id)
        except Exception:
            logger.exception("workspace upsert failed — falling back to transient render")
            await self.send_ui_render(websocket, components)
            return []
        await self.send_ui_upsert(websocket, chat_id, user_id, ops)
        # Audit the mutation (FR-023) without blocking the turn.
        try:
            from audit.hooks import record_workspace_event
            for op in ops:
                asyncio.create_task(record_workspace_event(
                    user_id=user_id,
                    action="component_updated" if not op.get("created") else "component_added",
                    chat_id=chat_id, component_id=op.get("component_id"),
                ))
        except Exception:
            logger.debug("workspace audit failed", exc_info=True)
        return ops

    def _component_action_allowed(self, user_id: str, agent_id: str, tool_name: str):
        """FR-036: deterministic component actions pass the SAME gates as the
        chat path — security-flag blocks and per-user tool permissions
        (the pre-028 ``table_paginate`` skipped both)."""
        agent_flags = self.security_flags.get(agent_id, {}) if hasattr(self, "security_flags") else {}
        flag = agent_flags.get(tool_name)
        if flag and flag.get("blocked"):
            return False, "This tool is blocked by a security review."
        try:
            if not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
                return False, "This tool is disabled in your permissions."
        except Exception:
            logger.exception("component_action: permission check failed — denying")
            return False, "Permission check failed."
        return True, ""

    async def _handle_component_action(self, websocket, user_id: str, payload: Dict[str, Any]):
        """Feature 028 — standardized deterministic component action
        (contracts/component-action.md): resolve the emitting component's
        provenance, re-check permissions, re-execute its source capability,
        and upsert the result into the target component in place."""
        chat_id = payload.get("chat_id") or self._ws_active_chat.get(id(websocket))
        component_id = payload.get("component_id")
        target_id = payload.get("target_component_id") or component_id
        params_patch = payload.get("params_patch") or {}
        # Contract (component-action.md): 'refresh' and 'invoke' are the
        # deterministic kinds — both re-execute the source capability with the
        # patched params. Anything else is refused explicitly (intent actions
        # never arrive on this verb; they use the param_picker chat idiom).
        kind = str(payload.get("kind") or "refresh").lower()
        if kind not in ("refresh", "invoke"):
            await self._audit_workspace_denial(user_id, chat_id or "", component_id or "",
                                               f"unsupported_kind:{kind}")
            await self.send_ui_render(websocket, [
                Alert(message=f"Unsupported component action kind '{kind}'.",
                      variant="error").to_dict()
            ], target="chat")
            return
        if not chat_id or not component_id:
            await self.send_ui_render(websocket, [
                Alert(message="This action is missing its component context.", variant="error").to_dict()
            ], target="chat")
            return
        # Timeline guard (FR-031): historical views are strictly read-only.
        if self._ws_timeline_mode.get(id(websocket)):
            await self._audit_workspace_denial(user_id, chat_id, component_id, "timeline_readonly")
            await self.send_ui_render(websocket, [
                Alert(message="You are viewing a past workspace state — return to live to interact.",
                      variant="warning").to_dict()
            ], target="chat")
            return
        row = self.workspace.get_by_component_id(chat_id, user_id, component_id)
        if row is None or not isinstance(row.get("component_data"), dict):
            await self.send_ui_render(websocket, [
                Alert(message="This component is no longer available.", variant="warning").to_dict()
            ], target="chat")
            return
        cd = row["component_data"]
        agent_id = cd.get("_source_agent", "")
        tool_name = cd.get("_source_tool", "")
        if not agent_id or not tool_name:
            await self.send_ui_render(websocket, [
                Alert(message="This component has no refreshable source.", variant="warning").to_dict()
            ], target="chat")
            return
        # Feature 029 (FR-004): retired sources get a clear retirement message
        # (audited), merged sources transparently reroute to ml-services-1.
        if agent_id in RETIRED_AGENT_IDS:
            await self._audit_workspace_denial(user_id, chat_id, component_id, "agent_retired")
            await self.send_ui_render(websocket, [
                Alert(
                    title="Capability retired",
                    message="This component came from an agent that has been retired; "
                            "it can still be viewed but no longer refreshed.",
                    variant="warning",
                ).to_dict()
            ], target="chat")
            return
        agent_id, tool_name = remap_merged_source(agent_id, tool_name)
        allowed, deny_reason = self._component_action_allowed(user_id, agent_id, tool_name)
        if not allowed:
            await self._audit_workspace_denial(user_id, chat_id, component_id, deny_reason)
            await self.send_ui_render(websocket, [
                Alert(message=f"Action not permitted: {deny_reason}", variant="error").to_dict()
            ], target="chat")
            return

        params = dict(cd.get("_source_params") or {})
        if isinstance(params_patch, dict):
            params.update(params_patch)
        # Per-user credentials ride along exactly as on the chat path.
        args = dict(params)
        try:
            creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
            if creds:
                args["_credentials"] = creds
                args["_credentials_encrypted"] = True
        except Exception:
            logger.debug("component_action: credential injection failed", exc_info=True)

        lock = self._workspace_locks.setdefault(chat_id, asyncio.Lock())
        try:
            async with lock:  # deterministic ordering per chat (contract §Concurrency)
                result = await self._execute_with_retry(websocket, agent_id, tool_name, args)
                if result and result.ui_components and not result.error:
                    for comp in result.ui_components:
                        if isinstance(comp, dict):
                            comp["_source_agent"] = agent_id
                            comp["_source_tool"] = tool_name
                            comp["_source_params"] = params
                    ops = await self._send_or_replace_components(
                        websocket, result.ui_components, chat_id, user_id=user_id,
                        force_component_id=target_id,
                    )
                    if ops:
                        try:
                            self.workspace.snapshot(chat_id, user_id, cause="component_action")
                        except Exception:
                            logger.debug("workspace snapshot failed (component_action)", exc_info=True)
                elif result and result.error:
                    await self.send_ui_render(websocket, [
                        Alert(message=result.error.get("message", "The action failed."),
                              variant="error").to_dict()
                    ], target="chat")
        except Exception as e:
            logger.error(f"component_action failed: {e}", exc_info=True)
            await self.send_ui_render(websocket, [
                Alert(message=f"The action failed: {e}", variant="error").to_dict()
            ], target="chat")
        finally:
            await self._safe_send(websocket, json.dumps({
                "type": "chat_status", "status": "done", "message": ""
            }))

    async def _reconcile_legacy_replacement(self, websocket, chat_id: str, user_id: str,
                                            *, cause: str):
        """Feature 028 (D18): after a legacy combine/condense replace, stamp
        workspace identities onto the fresh rows, snapshot, and push the full
        live workspace so the mutation is visible (pre-028 the thin client
        silently dropped components_combined/condensed)."""
        if not chat_id:
            return
        try:
            now_ms = int(time.time() * 1000)
            for row in self.workspace.live_rows(chat_id, user_id):
                if row.get("component_id"):
                    continue
                data = row.get("component_data")
                if not isinstance(data, dict):
                    continue
                cid = self.workspace.resolve_identity(data)
                self.history.db.execute(
                    "UPDATE saved_components SET component_id = ?, component_data = ?, updated_at = ? "
                    "WHERE id = ? AND user_id = ?",
                    (cid, json.dumps(data), now_ms, row["id"], user_id),
                )
            self.workspace.snapshot(chat_id, user_id, cause=cause)
            ws_components = self._canvas_components(chat_id, user_id)
            # FR-040: the replacement is a workspace change — every socket of
            # this user on this chat gets the re-render, not just the
            # originator (REST-initiated calls pass websocket=None).
            targets = [
                ws for ws in self.ui_clients
                if self._get_user_id(ws) == user_id
                and self._ws_active_chat.get(id(ws)) == chat_id
            ]
            if websocket is not None and websocket not in targets:
                targets.append(websocket)
            for ws in targets:
                await self.send_ui_render(ws, ws_components)
        except Exception:
            logger.exception("legacy replacement reconciliation failed (%s)", cause)

    async def _audit_workspace_denial(self, user_id: str, chat_id: str,
                                      component_id: str, reason: str):
        try:
            from audit.hooks import record_workspace_event
            await record_workspace_event(
                user_id=user_id, action="action_denied", chat_id=chat_id,
                component_id=component_id, outcome="failure",
                description=f"Component action denied: {reason}",
                detail={"reason": reason},
            )
        except Exception:
            logger.debug("workspace denial audit failed", exc_info=True)

    async def send_ui_upsert(self, websocket, chat_id: str, user_id: str, ops: List[Dict]):
        """Fan a ``ui_upsert`` out to every socket of ``user_id`` whose active
        chat is ``chat_id``, adapting each op per receiving device (D16).

        The structured dict AND its web HTML fragment ride together per op
        (026 FR-018 dual shape); the originating socket goes through the same
        path so there is exactly one delivery code path.
        """
        if not ops:
            return
        from rote.adapter import ComponentAdapter
        from rote.capabilities import DeviceType
        from shared.protocol import UIUpsert
        from webrender import render_component_fragment

        targets = [
            ws for ws in self.ui_clients
            if self._get_user_id(ws) == user_id and self._ws_active_chat.get(id(ws)) == chat_id
        ]
        if websocket is not None and websocket not in targets:
            targets.append(websocket)

        for ws in targets:
            profile = self.rote.get_profile(ws)
            wire_ops = []
            for op in ops:
                if op.get("op") == "remove":
                    wire_ops.append({"op": "remove", "component_id": op.get("component_id")})
                    continue
                comp = op.get("component")
                cid = op.get("component_id")
                if profile.device_type == DeviceType.BROWSER:
                    adapted = comp
                else:
                    adapted_list = ComponentAdapter.adapt([comp], profile)
                    if len(adapted_list) == 1:
                        adapted = adapted_list[0]
                    else:
                        adapted = {"type": "container", "content": adapted_list}
                    if isinstance(adapted, dict):
                        adapted["component_id"] = cid
                html = None
                try:
                    html = render_component_fragment(
                        adapted if isinstance(adapted, dict) else comp, profile)
                except Exception:
                    logger.exception("webrender: ui_upsert fragment render failed")
                wire_ops.append({"op": "upsert", "component_id": cid,
                                 "component": adapted, "html": html})
            await self._safe_send(ws, UIUpsert(chat_id=chat_id, ops=wire_ops).to_json())

    async def _handle_tool_progress(self, msg) -> None:
        """Route a long-running job's ToolProgress to the job's CHAT.

        Live updates fan out to every socket the user currently has open on that
        chat (so progress survives a refresh or a move to another device), plus
        the legacy originating socket. On a terminal update the result is
        PERSISTED into the chat workspace so a client returning later
        re-hydrates the completed UI (014/015 + 028). The concurrency-cap slot is
        released on terminal regardless of who is connected.
        """
        md = msg.metadata or {}
        cap_job_id = md.get("cap_job_id", "")
        req_id = md.get("request_id", "")
        phase = md.get("phase", "")
        terminal = bool(md.get("terminal")) or phase in ("completed", "failed", "status_unknown")
        ctx = self._job_context.get(cap_job_id) if cap_job_id else None

        payload: Dict[str, Any] = {
            "type": "tool_progress",
            "tool_name": msg.tool_name,
            "agent_id": msg.agent_id,
            "message": msg.message,
            "percentage": msg.percentage,
        }
        if phase:
            payload["phase"] = phase
        if terminal:
            payload["terminal"] = True
        if md.get("result") is not None:
            payload["result"] = md["result"]

        # Fan out to the job-user's CURRENT sockets on the job's chat, plus the
        # legacy request-scoped socket if one is still registered.
        targets: List[Any] = []
        if ctx:
            targets = self._sockets_on_chat(ctx.get("user_id"), ctx.get("chat_id"))
        legacy = self.pending_ui_sockets.get(req_id)
        if legacy is not None and legacy not in targets:
            targets.append(legacy)
        for ws in targets:
            try:
                await self._safe_send(ws, json.dumps(payload))
            except Exception:
                logger.debug("tool_progress forward failed", exc_info=True)

        # Terminal: persist the outcome into the chat (so a returning client
        # re-generates the completed UI), then release the concurrency-cap slot.
        if terminal and ctx:
            try:
                await self._finalize_long_running_job(ctx, msg)
            except Exception:
                logger.exception("finalizing long-running job failed (cap=%s)", cap_job_id)
            self._job_context.pop(cap_job_id, None)
        if cap_job_id and phase in ("completed", "failed", "status_unknown"):
            entry = self._pending_cap_entries.pop(cap_job_id, None)
            if entry:
                u_id, a_id = entry
                try:
                    await self.concurrency_cap.release(u_id, a_id, cap_job_id)
                except Exception:
                    logger.debug("cap release failed", exc_info=True)

    def _sockets_on_chat(self, user_id: str, chat_id: str) -> List[Any]:
        """Every socket ``user_id`` currently has open on ``chat_id`` (for
        fanning a job update out to a refreshed / multi-device session)."""
        return [
            ws for ws in self.ui_clients
            if self._get_user_id(ws) == user_id and self._ws_active_chat.get(id(ws)) == chat_id
        ]

    async def _narrate_job_result(self, ctx: Dict[str, Any], result: Dict[str, Any]):
        """Ask the model to narrate a completed job's results (a concise,
        plain-language comparison naming the best performer). Server-initiated
        (operator-default LLM, websocket=None). Returns chat-rail components, or
        None when no LLM is available / the call fails — callers fall back to a
        deterministic note."""
        try:
            tool = ctx.get("tool_name", "the job")
            messages = [
                {"role": "system", "content": (
                    "You summarize a COMPLETED machine-learning training job for the "
                    "user in the chat. Write a concise, plain-language summary (2-4 "
                    "sentences) comparing the models/metrics and naming the best "
                    "performer, using the actual numbers from the results. No preamble, "
                    "no markdown headings, no code fences."
                )},
                {"role": "user", "content": (
                    f"Tool: {tool}\nResults JSON:\n{json.dumps(result, default=str)[:4000]}"
                )},
            ]
            message, _usage = await self._call_llm(
                None, messages, feature="job_summary", temperature=0.3
            )
            text = getattr(message, "content", None) if message is not None else None
            if text and text.strip():
                return self._chat_narrative(text.strip())
        except Exception:
            logger.debug("job result narration failed", exc_info=True)
        return None

    async def _finalize_long_running_job(self, ctx: Dict[str, Any], msg) -> None:
        """Persist + deliver a long-running job's terminal outcome to its chat:

        1. the result COMPONENT into the persistent per-chat workspace (028), so
           ``load_chat`` re-hydrates it for a client that refreshed or returned on
           another device, and ``send_ui_upsert`` delivers it live; and
        2. a NARRATION in the chat rail — for a completed job the model compares
           the metrics and names the winner (falling back to a deterministic note
           when no LLM is available) — persisted as an assistant transcript
           message and fanned out live to every socket currently on the chat.
        """
        uid = ctx.get("user_id")
        cid = ctx.get("chat_id")
        if not uid or not cid:
            return
        md = msg.metadata or {}
        phase = md.get("phase", "")
        component = self._build_job_result_component(ctx, msg)

        # 1) The result component → persistent workspace (canvas) + live upsert.
        component_id = None
        try:
            ops = self.workspace.upsert(cid, uid, [component])
            component_id = component.get("component_id")
            await self.send_ui_upsert(None, cid, uid, ops)
        except Exception:
            logger.exception("persisting job result component failed (chat=%s)", cid)

        # 2) The narration → chat rail. Model-written comparison for a completed
        #    job with results; a short deterministic note otherwise.
        chat_core = None
        if phase == "completed" and isinstance(md.get("result"), dict):
            chat_core = await self._narrate_job_result(ctx, md["result"])
        if not chat_core:
            title = component.get("title") or "Job complete"
            note = title if phase == "completed" else (msg.message or "Job ended.")
            chat_core = [Text(content=f"✓ {note}").to_dict()]

        try:
            self.history.add_message(cid, "assistant", chat_core, user_id=uid)
        except Exception:
            logger.debug("job narration persist failed", exc_info=True)
        for ws in self._sockets_on_chat(uid, cid):
            try:
                await self.send_ui_render(ws, chat_core, target="chat")
            except Exception:
                logger.debug("job narration live delivery failed", exc_info=True)

        try:
            from audit.hooks import record_workspace_event
            await record_workspace_event(
                user_id=uid, action="component_added", chat_id=cid,
                component_id=component_id, outcome="success",
                description=f"Long-running job result delivered: {ctx.get('tool_name')}",
            )
        except Exception:
            logger.debug("job finalize audit failed", exc_info=True)

    def _build_job_result_component(self, ctx: Dict[str, Any], msg) -> Dict[str, Any]:
        """Build a deterministic result component from a terminal ToolProgress.

        A completed job renders its metrics as a Table; a failed / unknown
        outcome renders a status Alert. The component is source-tagged so the
        workspace assigns it a stable identity (028) and it survives reload."""
        md = msg.metadata or {}
        phase = md.get("phase", "")
        tool = ctx.get("tool_name", "job")
        source = {
            "_source_agent": ctx.get("agent_id"),
            "_source_tool": ctx.get("tool_name"),
            "_source_params": {"_job_result": ctx.get("chat_id", "")},
        }
        if phase == "completed":
            rows: List[List[str]] = []

            def _flatten(d: Dict[str, Any], prefix: str = "") -> None:
                for k, v in d.items():
                    key = f"{prefix}{k}"
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        rows.append([key, "" if v is None else str(v)])
                    elif isinstance(v, dict) and len(rows) < 40:
                        _flatten(v, f"{key}.")

            result = md.get("result")
            if isinstance(result, dict):
                _flatten(result)
            comp: Dict[str, Any] = {
                "type": "table",
                "title": f"Training complete — {tool}",
                "headers": ["Metric", "Value"],
                "rows": rows[:40] or [["status", "complete"]],
            }
        else:
            note = msg.message or ("Job failed." if phase == "failed" else "Job status unknown.")
            comp = {
                "type": "alert",
                "message": f"{tool}: {note}",
                "variant": "error" if phase == "failed" else "warning",
            }
        comp.update(source)
        return comp

    async def send_ui_render(self, websocket, components: List, target: str = "canvas"):
        """Send a UIRender message to a UI client, adapted via ROTE."""
        # Auto-route error-only messages to the chat panel instead of the canvas
        if target == "canvas" and components and all(
            isinstance(c, dict) and c.get("type") == "alert" and c.get("variant") == "error"
            for c in components
        ):
            target = "chat"
        adapted = self.rote.adapt(websocket, components)
        html = None
        try:
            profile = self.rote.get_profile(websocket)
            if target == "canvas":
                # Feature 028: canvas renders carry per-component identity
                # wrappers so every top-level component is a ui_upsert morph
                # target (contracts/ws-workspace-protocol.md).
                from webrender import render_workspace
                html = render_workspace(adapted, profile)
            else:
                from webrender import render_for_target
                # All current device targets render to web HTML; the seam allows
                # future targets to register their own renderer (FR-011).
                html = render_for_target("web", adapted, profile)
        except Exception:
            logger.exception("webrender: failed to render UI (sending structured components only)")
        msg = UIRender(components=adapted, target=target, html=html)
        await self._safe_send(websocket, msg.to_json())

    async def _shell_token_for_request(self, request):
        """Feature 026: access token for the web shell's WS register_ui handshake.
        Server-side OIDC session (or 'dev-token' under mock auth)."""
        try:
            from orchestrator.web_auth import session_token
            return session_token(request)
        except Exception:
            logger.debug("web_auth: session_token unavailable", exc_info=True)
            return ""

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
        """Hide any agent whose agent_id maps to a non-live draft record.

        Feature 030: an explicitly PUBLIC agent is never treated as a draft.
        Lifecycle drafts are always private, so a public ownership row means
        the slug-reverse draft match was a stale-row false positive — e.g.
        the live bundled ``etf-tracker-1-1`` agent, whose directory name
        collides with an old draft slug and was silently hidden from the
        agent list and Public tab (verified walkthrough finding).
        """
        if hasattr(self, 'lifecycle_manager'):
            draft = self.lifecycle_manager._find_draft_by_agent_id(agent_id)
            if draft and draft["status"] != "live":
                try:
                    ownership = self.history.db.get_agent_ownership(agent_id) or {}
                except Exception:
                    ownership = {}
                if bool(ownership.get("is_public", False)):
                    return False
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

    def _enable_recommended_agent_scopes(self, user_id: str,
                                         requested_agent_ids=None) -> List[str]:
        """Consent-based bulk enable for the public catalog (feature 030).

        For every connected, non-draft, PUBLIC agent (optionally narrowed to
        ``requested_agent_ids``), grants the scopes its registered tools
        actually use — minus ``tools:write``, which is never granted here
        (Constitution VII: attenuated, system-computed scopes; explicit user
        click as the grant). Unknown, private, or draft ids are silently
        ignored. Returns the agent ids that were enabled.
        """
        ownership_map = {o["agent_id"]: o for o in self.history.db.get_all_agent_ownership()}
        enabled: List[str] = []
        for agent_id in list(self.agent_cards.keys()):
            if requested_agent_ids is not None and agent_id not in requested_agent_ids:
                continue
            if self._is_draft_agent(agent_id):
                continue
            if not bool(ownership_map.get(agent_id, {}).get("is_public", False)):
                continue
            scopes = self.tool_permissions.scopes_required_by_tools(agent_id)
            if not scopes:
                continue
            self.tool_permissions.set_agent_scopes(
                user_id, agent_id, {s: True for s in scopes})
            enabled.append(agent_id)
        if enabled:
            logger.info(
                f"Consent enable (030): user={user_id} agents={enabled} (write excluded)")
        return enabled

    # 030: chat rail vs canvas split — the chat bubble stays concise words;
    # long/structured narrative content is promoted to a durable canvas card.
    _NARRATIVE_PROMOTE_CHARS = 700

    @classmethod
    def _narrative_is_long(cls, content: str) -> bool:
        """True when a final narrative is too long/structured for the chat rail."""
        c = content or ""
        return (len(c) > cls._NARRATIVE_PROMOTE_CHARS
                or bool(re.search(r"(?m)^#{1,6}\s", c))
                or bool(re.search(r"(?m)^\|.+\|\s*$", c)))

    @staticmethod
    def _concise_lead(content: str, limit: int = 320) -> str:
        """First plain sentences of a narrative — headings/tables stripped."""
        lines = [ln for ln in (content or "").splitlines()
                 if ln.strip() and not ln.lstrip().startswith(("#", "|", ">"))]
        text = " ".join(" ".join(lines).split())
        if not text:
            text = " ".join((content or "").split())
        if len(text) <= limit:
            return text
        cut = text[:limit]
        for sep in (". ", "! ", "? "):
            idx = cut.rfind(sep)
            if idx > 80:
                return cut[:idx + 1]
        return cut.rsplit(" ", 1)[0] + "…"

    @staticmethod
    def _narrative_doc_card(chat_id: str, content: str) -> Dict[str, Any]:
        """Durable canvas card for a long-form narrative (drafts, documents).

        Identity is derived from the chat and the document's own first
        heading, so iterating on the same document ("revise the aims")
        SUPERSEDES it in place while a different document appends — the
        walkthrough found grant deliverables vanishing into chat scroll with
        no workspace identity at all.
        """
        import hashlib
        m = re.search(r"(?m)^#{1,6}\s+(.+)$", content or "")
        title = (m.group(1).strip()[:120] if m else "Document")
        digest = hashlib.sha1(f"{chat_id}|{title}".encode("utf-8")).hexdigest()[:12]
        return Card(id=f"doc_{digest}", title=title, content=[
            Text(content=content, variant="markdown"),
        ]).to_dict()

    @staticmethod
    def _provenance_caption(tools_ran: bool) -> Dict[str, Any]:
        """Deterministic provenance chip for chat replies (feature 030).

        The walkthrough found clinical/grant prose presented authoritatively
        with no provenance at all. This caption is server-composed (never
        left to the model) and distinguishes model-memory answers from
        tool-grounded ones. Renderer-level honesty, model-independent.
        """
        if tools_ran:
            text = "Based on this turn's tool results — sources and steps are shown above."
        else:
            text = ("Model knowledge only — no live tools or sources were used in this "
                    "reply. Verify independently before relying on it.")
        return Text(content=text, variant="caption").to_dict()

    async def _notify_phi_if_detected(self, websocket, chat_id: str,
                                      user_id: str, message: str) -> None:
        """Notify-only PHI awareness for chat input (feature 030).

        Fires a transient chat Alert when a user message LOOKS like it
        contains PHI. Detection is fail-open (a missing/erroring analyzer
        never fires the notice) and the persistence posture is unchanged:
        the message stays in the transcript, cross-session memory keeps its
        fail-closed Presidio gate, and audit stays content-free. Shown at
        most once per chat per socket. Never raises into the chat turn.
        """
        try:
            if not message or not chat_id:
                return
            if not hasattr(self, "_phi_notified"):
                self._phi_notified = set()
            key = (id(websocket), chat_id)
            if key in self._phi_notified:
                return
            from personalization.phi_gate import get_phi_gate
            gate = get_phi_gate()
            hit = await asyncio.to_thread(gate.detect_for_notice, message)
            if not hit:
                return
            self._phi_notified.add(key)
            logger.info(f"phi_notice.shown chat_id={chat_id}")  # content-free
            await self.send_ui_render(websocket, [Alert(
                title="Possible PHI in your message",
                message=("This looks like it may contain protected health information. "
                         "It stays in this chat's transcript only — it is never added to "
                         "cross-session memory, and audit logs record message lengths, "
                         "not content. Prefer synthetic or de-identified data where "
                         "possible."),
                variant="warning",
            ).to_dict()], target="chat")
        except Exception:
            logger.debug("phi notice failed (non-fatal)", exc_info=True)

    def _text_only_cta_components(self, user_id: str) -> List[Dict[str, Any]]:
        """Deterministic enable affordance for text-only replies (feature 030).

        Appended server-side to the chat reply when a turn dispatched with
        zero tools AND the user has never enabled any agent scope — the
        never-configured state the walkthrough showed every fresh account
        lands in. Users who deliberately disabled their agents (rows exist,
        some enabled elsewhere) are not nagged. Composed of astralprims
        primitives per Constitution II/VIII; the buttons route through the
        audited ``enable_recommended_agents`` / ``chrome_open`` actions.
        """
        try:
            if self.tool_permissions.has_any_enabled_scope(user_id):
                return []
        except Exception:
            return []
        return [
            Alert(
                message=("Answered without agents — live search, data and "
                         "interactive components are currently off for this "
                         "account."),
                variant="info",
            ).to_dict(),
            Button(label="Enable recommended agents",
                   action="enable_recommended_agents",
                   payload={"source": "text_only"}).to_dict(),
            Button(label="Choose agents individually", action="chrome_open",
                   payload={"surface": "agents"}, variant="secondary").to_dict(),
        ]

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
            self._ws_timeline_mode.pop(id(websocket), None)
            self._ws_welcome.pop(id(websocket), None)
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
            self._ws_timeline_mode.pop(id(websocket), None)
            self._ws_welcome.pop(id(websocket), None)
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

        # Feature 028 (FR-015): production posture is fail-closed. Mock auth
        # outside explicitly declared development mode is a fatal
        # misconfiguration — refuse to serve rather than run open.
        from orchestrator.session_store import assert_production_posture
        assert_production_posture()

        # Feature 028 (FR-013): drain queued offline sign-out revocations.
        async def _revocation_queue_loop():
            from orchestrator.web_auth import process_revocation_queue_once
            interval = int(os.getenv("AUTH_REVOCATION_RETRY_SECONDS", "60"))
            while True:
                try:
                    resolved = await process_revocation_queue_once()
                    if resolved:
                        logger.info("auth: resolved %d queued credential revocation(s)", resolved)
                except Exception:
                    logger.debug("auth: revocation queue pass failed", exc_info=True)
                await asyncio.sleep(interval)

        asyncio.create_task(_revocation_queue_loop())

        # 030: purge permission rows leaked by drafts discarded before the
        # delete-time purge existed (run in a thread — pure DB/dir checks).
        try:
            purged = await asyncio.to_thread(
                self.lifecycle_manager.reconcile_orphaned_draft_permissions)
            if purged:
                logger.info("Startup sweep purged leaked draft permissions "
                            f"for {purged} agent id(s)")
        except Exception:
            logger.debug("draft permission sweep failed (non-fatal)", exc_info=True)

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

        # Feature 025 wiring (027 click-through finding): the scheduler loop
        # was never instantiated anywhere, so cron jobs and "Run now" silently
        # never dispatched.
        #
        # 030-finish-soul-integration (FR-005, Constitution VII): the EXECUTION
        # loop runs unattended jobs under the offline-grant store, so it is now
        # FAIL-CLOSED — it starts only when FF_SCHEDULER_EXECUTION is enabled,
        # which MUST NOT be turned on until the lead-dev security review of
        # offline_grant.py is recorded (030 FR-004 / 025 T057). When the gate is
        # off, no job-execution code path is reachable; chat-side scheduling
        # (proposals/consent cards) is unaffected and the surface reports
        # unattended execution as unavailable.
        if flags.is_enabled("scheduler_execution"):
            try:
                from orchestrator.offline_grant import OfflineGrantStore
                from scheduler.loop import SchedulerLoop
                from scheduler.runner import JobRunner
                from scheduler.store import ScheduledJobStore
                _job_store = ScheduledJobStore(self.history.db)
                _job_runner = JobRunner(self, _job_store, OfflineGrantStore(self.history.db))
                self._scheduler_loop = SchedulerLoop(_job_store, _job_runner, self.async_task_manager)
                self._scheduler_loop.start()
                logger.info("scheduler.execution_loop_started (FF_SCHEDULER_EXECUTION=on)")
            except Exception:
                logger.exception("scheduler loop failed to start (jobs will not dispatch)")
        else:
            self._scheduler_loop = None
            logger.info(
                "scheduler.execution_loop_disabled (FF_SCHEDULER_EXECUTION=off) — "
                "unattended job execution is gated off pending the offline-grant "
                "security review (030 FR-004/FR-005; 025 T057)"
            )

        # Feature 027 (click-through finding): user-created agents that went
        # live do not survive a restart — nothing relaunched them, leaving
        # "My agents" empty and the original requests unservable. Relaunch
        # every live generated agent without touching ownership or the user's
        # saved scopes (align_scopes=False).
        async def _relaunch_generated_agents():
            await asyncio.sleep(5)  # let the static-fleet monitor settle first
            try:
                rows = self.history.db.fetch_all(
                    "SELECT id, agent_name FROM draft_agents WHERE status = 'live'")
            except Exception:
                logger.exception("relaunch: could not list live generated agents")
                return
            for row in rows:
                try:
                    await self.lifecycle_manager.start_draft_agent(
                        row["id"], align_scopes=False)
                    logger.info("relaunch: %s (%s) restarted", row["agent_name"], row["id"])
                except Exception as exc:
                    logger.warning("relaunch: %s (%s) failed: %s",
                                   row["agent_name"], row["id"], exc)

        asyncio.create_task(_relaunch_generated_agents())

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
            redoc_url="/api/redoc",
            openapi_url="/api/openapi.json",
        )

        # Constitution VI: interactive API docs MUST answer at the literal
        # /docs URL. The canonical pages stay /api-namespaced; these aliases
        # redirect (no second Swagger mount, no schema duplication).
        from fastapi.responses import RedirectResponse as _DocsRedirect

        @app.get("/docs", include_in_schema=False)
        async def _docs_alias():
            return _DocsRedirect("/api/docs")

        @app.get("/redoc", include_in_schema=False)
        async def _redoc_alias():
            return _DocsRedirect("/api/redoc")

        @app.get("/openapi.json", include_in_schema=False)
        async def _openapi_alias():
            return _DocsRedirect("/api/openapi.json")

        # CORS — the web UI is same-origin since feature 026 (the orchestrator
        # serves it), so cross-origin access is the exception, not the rule.
        # Default allowlist = this deployment's own public URLs; extend with
        # CORS_ORIGINS (comma-separated) for legitimate external consumers.
        # (The former :5173 React-dev defaults are gone with the SPA.)
        if os.getenv("CORS_ORIGINS"):
            cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
        else:
            cors_origins = sorted({
                o.rstrip("/") for o in (
                    os.getenv("PUBLIC_BASE_URL", ""),
                    os.getenv("BACKEND_PUBLIC_URL", ""),
                    f"http://localhost:{os.getenv('ORCHESTRATOR_PORT', '8001')}",
                ) if o
            })
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Store Orchestrator instance on app.state so REST API routes can access it
        app.state.orchestrator = self

        # ── Health probes (ungated; no user data) ───────────────────────────
        # /healthz: liveness — the process is serving. /readyz: readiness —
        # the database answers. Wired into the compose healthcheck and any
        # orchestration platform (k8s livenessProbe/readinessProbe).
        @app.get("/healthz", include_in_schema=False)
        async def healthz():
            return {"status": "ok"}

        @app.get("/readyz", include_in_schema=False)
        async def readyz():
            from fastapi.responses import JSONResponse as _JSON
            try:
                row = await asyncio.to_thread(self.history.db.fetch_one, "SELECT 1 AS ok")
                if not row:
                    raise RuntimeError("empty health-probe result")
            except Exception as exc:
                logger.warning("readyz: database probe failed: %s", exc)
                return _JSON({"status": "degraded", "db": "unreachable"}, status_code=503)
            return {"status": "ok", "db": "ok", "agents": len(self.agent_cards)}

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_ui_connection_fastapi(websocket)

        # ── Feature 026: serve the server-driven web UI from this app ──────
        # The shell page + static assets replace the former separate React SPA
        # (no separate :5173 frontend). astralprims defines primitives, the
        # orchestrator renders them (webrender), ROTE adapts per device.
        import os as _os
        from fastapi.responses import HTMLResponse as _HTMLResponse
        _webrender_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "webrender")
        _shell_path = _os.path.join(_webrender_dir, "templates", "shell.html")

        @app.get("/", response_class=_HTMLResponse)
        async def serve_shell(request: Request):
            # Feature 028 (FR-001): the shell is gated. Unauthenticated
            # visitors are redirected straight to Keycloak via /auth/login
            # with their destination preserved — no app markup is served.
            try:
                from orchestrator.web_auth import shell_gate
                from fastapi.responses import RedirectResponse as _Redirect
                gate = shell_gate(request)
                if gate:
                    return _Redirect(gate, status_code=302)
            except Exception:
                logger.exception("web_auth: shell gate check failed — failing closed")
                return _HTMLResponse("<h1>AstralBody</h1><p>Sign-in unavailable.</p>", status_code=503)
            try:
                with open(_shell_path, "r", encoding="utf-8") as fh:
                    shell = fh.read()
            except Exception:
                logger.exception("webrender: shell template missing")
                return _HTMLResponse("<h1>AstralBody</h1><p>UI shell unavailable.</p>", status_code=500)
            # Inject a session token for the WS handshake. In mock-auth/dev the
            # client falls back to 'dev-token'; with server-side OIDC the auth
            # routes establish a session and supply the access token here.
            token = ""
            try:
                token = await self._shell_token_for_request(request)
            except Exception:
                token = ""
            # Feature 027: render the static top bar + settings menu from the
            # server session's roles (admin group absent for non-admins —
            # FR-014 UX gating; handlers re-check server-side).
            topbar = ""
            try:
                from orchestrator.web_auth import session_roles
                from webrender.chrome import render_topbar
                topbar = render_topbar(roles=session_roles(request))
            except Exception:
                logger.exception("chrome: topbar render failed — serving bare shell")
            shell = shell.replace("%%ASTRAL_TOKEN%%", token or "")
            # Feature 028 (FR-011): server-derived resume flag — false only on
            # the load right after interactive sign-in; the client echoes it
            # into register_ui so auth.session_resumed keeps 016 semantics.
            resumed_flag = "true"
            try:
                from orchestrator.web_auth import session_resumed_flag
                resumed_flag = "true" if session_resumed_flag(request) else "false"
            except Exception:
                logger.debug("session_resumed_flag failed", exc_info=True)
            shell = shell.replace("%%ASTRAL_RESUMED%%", resumed_flag)
            # Feature 031: inject the file-input `accept` list from the server's
            # content_type allow-list so the picker offers exactly the accepted
            # extensions (single source of truth; server still validates uploads).
            accept_attr = ""
            try:
                from orchestrator.attachments.content_type import ACCEPTED_EXTENSIONS
                accept_attr = ",".join("." + e for e in sorted(ACCEPTED_EXTENSIONS))
            except Exception:
                logger.debug("attachment accept-list injection failed", exc_info=True)
            shell = shell.replace("%%ASTRAL_ACCEPT%%", accept_attr)
            return _HTMLResponse(shell.replace("%%ASTRAL_TOPBAR%%", topbar))

        app.mount("/static", StaticFiles(directory=_os.path.join(_webrender_dir, "static")), name="static")

        # Mount REST API routers
        from orchestrator.api import chat_router, component_router, agent_router, dashboard_router, draft_router, voice_router, task_router, async_task_router, user_router
        from orchestrator.auth import auth_router
        from orchestrator.web_auth import web_auth_router  # Feature 026 — server-side OIDC
        from orchestrator.attachments.router import attachments_router
        from audit.api import audit_router
        from audit.middleware import AuditHTTPMiddleware
        from feedback.api import feedback_user_router, feedback_admin_router
        from onboarding.api import onboarding_user_router, onboarding_admin_router
        from llm_config.api import llm_router  # Feature 006-user-llm-config
        # Feature 025 — agentic soul integration
        from personalization.api import (
            personalization_router,
            skills_router,
            memory_router,
        )
        from scheduler.api import schedule_router
        from dreaming.api import dreaming_router
        app.include_router(chat_router)
        app.include_router(component_router)
        app.include_router(agent_router)
        app.include_router(user_router)  # Feature 013 — tool-selection prefs
        app.include_router(draft_router)
        app.include_router(dashboard_router)
        app.include_router(auth_router)
        app.include_router(web_auth_router)  # Feature 026 — /auth/login,/callback,/session,/logout
        app.include_router(attachments_router)
        app.include_router(voice_router)
        app.include_router(task_router)
        app.include_router(async_task_router)
        app.include_router(audit_router)
        # Feature 004 — component feedback & tool-improvement loop
        app.include_router(feedback_user_router)
        app.include_router(feedback_admin_router)
        # Feature 005 — tool tips and getting started tutorial
        app.include_router(onboarding_user_router)
        app.include_router(onboarding_admin_router)
        # Feature 006 — user-configurable LLM subscription (Test Connection)
        app.include_router(llm_router)
        # Feature 025 — agentic soul integration
        app.include_router(personalization_router)
        app.include_router(skills_router)
        app.include_router(memory_router)
        app.include_router(schedule_router)
        app.include_router(dreaming_router)

        # Audit HTTP middleware — records every authenticated REST request
        # in the caller's own log (FR-021). Added after CORS so OPTIONS
        # preflights are short-circuited before reaching the recorder.
        app.add_middleware(AuditHTTPMiddleware)

        # Mount A2A JSON-RPC server (orchestrator as A2A agent)
        try:
            from orchestrator.a2a_orchestrator_executor import setup_orchestrator_a2a
            setup_orchestrator_a2a(app, self)
            logger.info("A2A JSON-RPC endpoint mounted at /a2a/")
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

        # Start combined server. proxy_headers honors X-Forwarded-Proto/-For
        # from a TLS-terminating reverse proxy (production deployments) so
        # request.base_url is https — which drives the session cookie's
        # `secure` flag and the OIDC redirect_uri. Only proxies listed in
        # FORWARDED_ALLOW_IPS are trusted (default: loopback only).
        config = uvicorn.Config(
            app, host="0.0.0.0", port=PORT,
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
            proxy_headers=True,
            forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        )
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
                except Exception:
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
            content = strip_reasoning_markup(response.choices[0].message.content)
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

            # Fetch JWKS (feature 028 D8: cached with kid-miss refetch — the
            # pre-028 per-call fetch made every WS register an IdP round-trip)
            jwks_url = f"{authority}/protocol/openid-connect/certs"
            from shared.jwks_cache import get_jwks
            jwks = await get_jwks(jwks_url, token=token)

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
