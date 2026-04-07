# AstralBody Backend — New Features

This document covers the recently added orchestrator subsystems. Each feature is gated behind a feature flag in `.env` and is disabled by default unless noted.

---

## Table of Contents

1. [Feature Flags](#feature-flags)
2. [Hook System](#hook-system)
3. [Task State Machine](#task-state-machine)
4. [Message Compaction](#message-compaction)
5. [Coordinator Mode](#coordinator-mode)
6. [Knowledge Synthesis ("Dreamer")](#knowledge-synthesis-dreamer)
7. [Local LLM via Ollama (Docker)](#local-llm-via-ollama-docker)

---

## Feature Flags

**File:** `backend/shared/feature_flags.py`

All new subsystems are gated by environment-variable-driven feature flags. Set them in your `.env` file.

| Flag | Default | Controls |
|------|---------|----------|
| `FF_DENIAL_LOOP_DETECTION` | `true` | Removes tools from prompt after repeated permission denials |
| `FF_TOOL_CONCURRENCY_SAFETY` | `true` | Prevents concurrent tool calls to the same agent |
| `FF_MESSAGE_COMPACTION` | `false` | Automatic context window management via summarization |
| `FF_PROGRESS_STREAMING` | `false` | Real-time progress updates during long tool calls |
| `FF_HOOK_SYSTEM` | `false` | Lifecycle event hooks (pre/post tool use, session events) |
| `FF_TASK_STATE_MACHINE` | `false` | Formal Re-Act loop state tracking with recovery |
| `FF_COORDINATOR_MODE` | `false` | Multi-step task decomposition and parallel execution |
| `FF_KNOWLEDGE_SYNTHESIS` | `false` | Background learning from tool interactions via local LLM |

Usage in code:

```python
from shared.feature_flags import flags

if flags.is_enabled("hook_system"):
    await self.hooks.emit(context)
```

---

## Hook System

**File:** `backend/orchestrator/hooks.py`  
**Flag:** `FF_HOOK_SYSTEM`

An extensible lifecycle event system that allows subsystems to observe and modify orchestrator behavior without changing core code. Inspired by Claude Code's PreToolUse / PostToolUse pattern.

### Events

| Event | When it fires |
|-------|---------------|
| `SESSION_START` | UI client connects via WebSocket |
| `SESSION_END` | UI client disconnects |
| `PRE_TOOL_USE` | Before executing a tool call (can block or modify args) |
| `POST_TOOL_USE` | After a successful tool call |
| `POST_TOOL_FAILURE` | After a failed tool call |
| `PERMISSION_DENIED` | When a tool call is denied by permissions |
| `AGENT_REGISTERED` | When a new agent connects and registers |
| `AGENT_DISCONNECTED` | When an agent disconnects |

### Hook Actions

- **`continue`** (default) — proceed normally
- **`block`** — prevent the action (only for `PRE_TOOL_USE`)
- **`modify`** — proceed with modified tool arguments

### Registering a Hook

```python
from orchestrator.hooks import HookManager, HookEvent, HookContext, HookResponse

async def my_audit_hook(ctx: HookContext) -> HookResponse:
    print(f"Tool {ctx.tool_name} called by {ctx.user_id}")
    return HookResponse()  # continue

manager = HookManager()
manager.register(HookEvent.POST_TOOL_USE, my_audit_hook)
```

---

## Task State Machine

**File:** `backend/orchestrator/task_state.py`  
**Flag:** `FF_TASK_STATE_MACHINE`

Provides formal state tracking for multi-step Re-Act operations. Enables inspection, turn-limit enforcement, and recovery from WebSocket disconnects.

### Task States

```
PENDING  -->  RUNNING  -->  AWAITING_TOOL  -->  COMPLETED
                  |                                |
                  +----------> FAILED              |
                  +----------> CANCELLED <---------+
```

### Key Features

- **Turn limits**: Each task has a configurable `max_turns` (default 10) to prevent infinite loops.
- **Auto-cancel**: Creating a new task for a chat automatically cancels any active task.
- **Cleanup**: Completed/failed/cancelled tasks are garbage-collected after 1 hour.

### Usage

```python
task = self.task_manager.create_task(chat_id, user_id, message="Search patients")
task.transition(TaskState.RUNNING)
task.transition(TaskState.AWAITING_TOOL, current_tool="search_patients")
task.transition(TaskState.COMPLETED)
```

---

## Message Compaction

**File:** `backend/orchestrator/compaction.py`  
**Flag:** `FF_MESSAGE_COMPACTION`

Automatic context window management. When conversation history approaches the LLM's token limit, older turns are summarized into compact summaries while preserving the system prompt, recent context, and the current user message.

### How It Works

1. Estimates token count across all messages (4 chars per token heuristic).
2. Checks against 80% of the model's known context window.
3. If over budget, groups older messages into turns (assistant + tool results kept together).
4. Preserves the last 4 turns and summarizes everything older via LLM.
5. Replaces compacted turns with `[COMPACTED] ...summary...`.

### Supported Models

Automatic context window detection for common models (GPT-4o, Llama 3.x, Qwen, Mistral, etc.). Falls back to 32,768 tokens for unknown models.

---

## Coordinator Mode

**File:** `backend/orchestrator/coordinator.py`  
**Flag:** `FF_COORDINATOR_MODE`

Decomposes complex multi-step user requests into parallel and sequential sub-tasks, executes them, and synthesizes results.

### How It Works

1. **Detection**: Heuristic checks for multi-step language ("and then", "first...next", commas with action verbs).
2. **Planning**: LLM generates a `CoordinatorPlan` with sub-tasks and dependency edges.
3. **Execution**: Sub-tasks are grouped into parallel waves (respecting `depends_on`), executed concurrently within each wave.
4. **Synthesis**: Results from all sub-tasks are combined into a final response via LLM.

### Example

User: "Search for patients over 60, then graph their ages and email me the results"

Coordinator creates:
- Wave 1: `search_patients(age_min=60)`
- Wave 2 (parallel): `graph_ages(data=wave1)` + `send_email(data=wave1)`

---

## Knowledge Synthesis ("Dreamer")

**File:** `backend/orchestrator/knowledge_synthesis.py`  
**Flags:** `FF_KNOWLEDGE_SYNTHESIS` + `FF_HOOK_SYSTEM`  
**Output:** `backend/knowledge/` directory

A background system that learns from tool interactions and produces structured markdown documents to improve future agent generation and task routing. Inspired by Claude Code's auto-dream memory consolidation.

### Architecture

```
[Re-Act Loop]
      |  POST_TOOL_USE / POST_TOOL_FAILURE hooks
      v
[InteractionCollector]  -->  interaction_log DB table
      |
      |  (background task, every 30 min, min 20 new interactions)
      v
[KnowledgeSynthesizer]  -->  calls local Ollama model
      |
      v
[backend/knowledge/]    -->  structured .md files
      |
      +---> Orchestrator system prompt  (routing hints)
      +---> Agent generator prompt      (proven patterns)
```

### Components

| Class | Purpose |
|-------|---------|
| `InteractionCollector` | Hook handler that logs tool call outcomes (agent, tool, success/fail, response time) to the `interaction_log` database table |
| `KnowledgeSynthesizer` | Background `asyncio.Task` that periodically queries unsynthesized interactions, groups by agent, calls the local LLM, and writes/updates markdown files |
| `KnowledgeIndex` | Reads and caches knowledge files with mtime-based invalidation. Provides `get_routing_hints()` and `get_generation_context()` for prompt injection |

### Knowledge File Structure

```
backend/knowledge/
  _index.md                      # Auto-maintained master index
  techniques/{agent_slug}.md     # Per-agent technique docs
  patterns/tool_patterns.md      # Cross-agent tool usage patterns
  capabilities/{agent_slug}.md   # Per-agent capability summaries
```

### Markdown Schema

All knowledge files use frontmatter:

```markdown
---
name: "weather_techniques"
type: "technique"
agent: "weather-1"
updated_at: "2026-04-07T14:30:00Z"
synthesis_count: 5
interaction_count: 142
confidence: 0.85
---

# Weather Agent Techniques

## Effective Patterns
- get_forecast succeeds 94% with "City, State" format vs 71% with zip code.

## Anti-Patterns
- Date ranges > 14 days: 100% failure rate.
```

### Feedback Loops

1. **Runtime routing**: `get_routing_hints()` appends agent performance summaries to the orchestrator system prompt so the LLM makes better tool-selection decisions.
2. **Agent generation**: `get_generation_context()` injects proven patterns into the LLM prompt when generating new agent code, so new agents benefit from past learnings.

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `KNOWLEDGE_LLM_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `KNOWLEDGE_LLM_API_KEY` | `ollama` | API key (Ollama doesn't need one) |
| `KNOWLEDGE_LLM_MODEL` | `qwen2.5:0.5b` | Model to use for synthesis |
| `KNOWLEDGE_SYNTHESIS_INTERVAL` | `1800` | Seconds between synthesis cycles |
| `KNOWLEDGE_MIN_INTERACTIONS` | `20` | Minimum new interactions before synthesizing |

### Database

Adds an `interaction_log` table to PostgreSQL:

| Column | Type | Description |
|--------|------|-------------|
| `agent_id` | TEXT | Which agent was called |
| `tool_name` | TEXT | Which tool was called |
| `success` | BOOLEAN | Whether the call succeeded |
| `error_message` | TEXT | Error details (if failed) |
| `response_time_ms` | INTEGER | Call duration |
| `chat_id` | TEXT | Associated chat session |
| `synthesized` | BOOLEAN | Whether this row has been processed |

### Graceful Degradation

If Ollama is unavailable, the collector continues logging interactions to the database. The synthesizer logs a warning and retries on the next cycle. No data is lost.

---

## Local LLM via Ollama (Docker)

**File:** `docker-compose.yml`

Three services support the knowledge synthesis system:

| Service | Image | Purpose |
|---------|-------|---------|
| `ollama` | `ollama/ollama:latest` | Ollama server (CPU-only). Models stored in persistent `ollama_models` volume. |
| `ollama-pull` | `ollama/ollama:latest` | One-shot init container that pulls the configured model on first startup, then exits. |
| `astralbody` | (built from Dockerfile) | Now depends on `ollama` with env vars pointing at `http://ollama:11434/v1`. |

### Default Model

**`qwen2.5:0.5b`** — a 0.5B parameter model (~400MB download). Fast on CPU (1-3 seconds per call). Good enough for structured data analysis and markdown generation.

### Alternative Models

Set `KNOWLEDGE_LLM_MODEL` in `.env` to switch:

| Model | Size | Speed (CPU) | Quality |
|-------|------|-------------|---------|
| `qwen2.5:0.5b` | ~400MB | Fastest | Good for structured extraction |
| `tinyllama` | ~600MB | Very fast | Decent for simple patterns |
| `qwen2.5:1.5b` | ~1GB | Fast | Better analysis quality |
| `qwen2.5:3b` | ~2GB | Moderate | Best quality for CPU |

### Quick Start

```bash
# 1. Enable the features in .env
FF_KNOWLEDGE_SYNTHESIS=true
FF_HOOK_SYSTEM=true

# 2. Start everything (Ollama + model pull + backend + postgres)
docker compose up -d

# 3. Verify Ollama is running
curl http://localhost:11434/api/tags

# 4. Use AstralBody normally — interactions are logged and
#    knowledge files appear in backend/knowledge/ after the
#    first synthesis cycle
```

### Running Without Docker

If running locally (not in Docker):

```bash
# Install and start Ollama
ollama serve

# Pull the model
ollama pull qwen2.5:0.5b

# Set env vars
export KNOWLEDGE_LLM_BASE_URL=http://localhost:11434/v1
export FF_KNOWLEDGE_SYNTHESIS=true
export FF_HOOK_SYSTEM=true
```
