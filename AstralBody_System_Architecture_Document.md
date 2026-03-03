# AstralBody: A Comprehensive System Architecture Document

## Multi-Agent Orchestration Platform with Server-Driven UI

**Document Purpose:** This document provides an exhaustive technical analysis of the AstralBody system, a multi-agent orchestration platform that combines Agent-to-Agent (A2A) communication, the Model Context Protocol (MCP), and LLM-powered tool routing with a server-driven dynamic UI. It is intended to support a qualifying examination by detailing the system's architecture, design decisions, implementation specifics, and positioning relative to comparable systems in the market.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview and Design Philosophy](#2-system-overview-and-design-philosophy)
3. [Architecture Deep Dive](#3-architecture-deep-dive)
   - 3.1 [Orchestrator Core](#31-orchestrator-core)
   - 3.2 [Agent Framework](#32-agent-framework)
   - 3.3 [Protocol Layer](#33-protocol-layer)
   - 3.4 [Server-Driven UI Primitives](#34-server-driven-ui-primitives)
   - 3.5 [Frontend Architecture](#35-frontend-architecture)
   - 3.6 [Authentication and Authorization](#36-authentication-and-authorization)
   - 3.7 [Data Persistence Layer](#37-data-persistence-layer)
   - 3.8 [LLM Integration and Tool Routing](#38-llm-integration-and-tool-routing)
   - 3.9 [Deployment Infrastructure](#39-deployment-infrastructure)
4. [Detailed Component Analysis](#4-detailed-component-analysis)
   - 4.1 [Specialist Agents](#41-specialist-agents)
   - 4.2 [Progress and Streaming System](#42-progress-and-streaming-system)
   - 4.3 [Expression Evaluator](#43-expression-evaluator)
   - 4.4 [Component Combining System](#44-component-combining-system)
5. [Communication Flows](#5-communication-flows)
6. [Comparison with Existing Systems](#6-comparison-with-existing-systems)
   - 6.1 [vs. LangChain / LangGraph](#61-vs-langchain--langgraph)
   - 6.2 [vs. AutoGen (Microsoft)](#62-vs-autogen-microsoft)
   - 6.3 [vs. CrewAI](#63-vs-crewai)
   - 6.4 [vs. OpenAI Assistants API / GPTs](#64-vs-openai-assistants-api--gpts)
   - 6.5 [vs. Semantic Kernel (Microsoft)](#65-vs-semantic-kernel-microsoft)
   - 6.6 [vs. Haystack (deepset)](#66-vs-haystack-deepset)
   - 6.7 [vs. Streamlit / Gradio](#67-vs-streamlit--gradio)
   - 6.8 [vs. Google A2A Protocol](#68-vs-google-a2a-protocol)
   - 6.9 [Comparative Summary Table](#69-comparative-summary-table)
7. [Novel Contributions and Key Differentiators](#7-novel-contributions-and-key-differentiators)
8. [Limitations and Future Work](#8-limitations-and-future-work)
9. [Conclusion](#9-conclusion)

---

## 1. Executive Summary

AstralBody is a multi-agent orchestration platform designed for domain-specific professional workflows—particularly in medical and scientific contexts. It distinguishes itself from existing agent frameworks through a unique combination of three capabilities:

1. **Server-Driven Dynamic UI**: Unlike most agent systems that return plain text or markdown, AstralBody agents return structured UI primitives (cards, tables, charts, metrics, grids, etc.) that are rendered as rich, interactive React components in the browser. The backend completely controls the presentation layer.

2. **Standards-Based Agent-to-Agent Communication**: The system implements Google's Agent-to-Agent (A2A) protocol for agent discovery (via `/.well-known/agent-card.json` endpoints) and Anthropic's Model Context Protocol (MCP) for tool invocation, making agents interoperable and self-describing.

3. **LLM-Powered Autonomous Tool Routing**: A central orchestrator uses a large language model (DeepSeek-V3.2 in the current configuration) in a multi-turn ReAct (Reasoning + Acting) loop to autonomously break down user requests, select appropriate tools across multiple specialist agents, execute them (potentially in parallel), analyze intermediate results, and compose final responses.

The system runs as a monolithic-but-modular application with a Python/FastAPI backend, React/TypeScript/Vite frontend, Keycloak-based OIDC authentication, SQLite persistence, and Docker-based deployment.

---

## 2. System Overview and Design Philosophy

### 2.1 Core Design Principles

**Agent Autonomy with Central Coordination**: Each specialist agent is a self-contained service with its own FastAPI server, tool registry, and agent card. The orchestrator does not hard-code knowledge of any agent's capabilities—instead, it discovers agents dynamically by polling a port range and fetching their self-describing agent cards.

**Server-Driven UI (SDUI)**: The fundamental architectural insight is that tool outputs should not be plain text that the LLM must re-format. Instead, every tool function returns structured UI primitive objects (e.g., `Card`, `Table`, `MetricCard`, `PlotlyChart`) that are serialized as JSON and rendered deterministically on the frontend. This means:
- The backend has full control over presentation
- UI changes require no frontend deployment
- Tool outputs are always well-formatted, never mangled by LLM interpretation
- Components can be saved, combined, and manipulated independently

**Protocol-First Design**: Rather than using proprietary inter-process communication, AstralBody adopts two emerging open standards:
- **A2A (Agent-to-Agent)** for agent discovery and registration
- **MCP (Model Context Protocol)** for tool invocation request/response semantics

**Multi-Tenant Session Isolation**: Every operation is scoped to a `user_id` derived from authenticated JWT tokens, ensuring complete data isolation between users at the database level.

### 2.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (React/Vite)                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────┐  │
│  │LoginScreen│  │ChatInterface │  │DynamicRend│  │UISavedDra│  │
│  │          │  │              │  │erer       │  │wer       │  │
│  └──────────┘  └──────────────┘  └───────────┘  └───────────┘  │
│                    │ WebSocket (/ws)      │ REST (/api/*)       │
└────────────────────┼─────────────────────┼─────────────────────┘
                     │                     │
┌────────────────────┼─────────────────────┼─────────────────────┐
│              ORCHESTRATOR (FastAPI, Port 8001)                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Orchestrator Core                                       │    │
│  │  - Agent Discovery & Registration                        │    │
│  │  - LLM-Powered ReAct Tool Routing                        │    │
│  │  - UI Message Handling                                   │    │
│  │  - Component Combining (LLM-powered)                     │    │
│  │  - Chat History & Session Management                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Auth Proxy   │  │   History    │  │  Token Validator      │  │
│  │ (BFF Pattern)│  │   Manager   │  │  (Keycloak JWKS)      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│           │                │                                    │
│     ┌─────┴─────┐    ┌────┴────┐                               │
│     │ Keycloak  │    │ SQLite  │                               │
│     │ IAM Server│    │ Database│                               │
│     └───────────┘    └─────────┘                               │
└────────────────────────────────────────────────────────────────┘
         │ WebSocket (ws://agent-host:port/agent)
         ▼
┌────────────────────────────────────────────────────────────────┐
│                    SPECIALIST AGENTS                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ General Agent │  │ Medical Agent│  │Weather Agent │         │
│  │ Port 8003     │  │ Port 8004    │  │Port 8005     │         │
│  │               │  │              │  │              │         │
│  │ Tools:        │  │ Tools:       │  │ Tools:       │         │
│  │ -dynamic_chart│  │ -search_pts  │  │ -geocode     │         │
│  │ -modify_data  │  │ -gen_synth   │  │ -cur_weather │         │
│  │ -sys_status   │  │ -analyze_pt  │  │ -ext_weather │         │
│  │ -cpu_info     │  │ -analyze_csv │  │ -hist_weather│         │
│  │ -memory_info  │  │ -generic_dat │  │ -alerts      │         │
│  │ -disk_info    │  │              │  │ -compare_loc │         │
│  │ -wiki_search  │  │              │  │ -hourly_fcst │         │
│  │ -arxiv_search │  │              │  │ -daily_fcst  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  Each agent exposes:                                           │
│  - GET  /.well-known/agent-card.json  (A2A Discovery)         │
│  - GET  /health                       (Health Check)          │
│  - WS   /agent                        (MCP Tool Execution)   │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Deep Dive

### 3.1 Orchestrator Core

The orchestrator (`orchestrator.py`, ~1,700 lines) is the central hub of the system. It is implemented as a single Python class (`Orchestrator`) that manages all system concerns:

**State Management:**
- `self.agents`: Dictionary mapping `agent_id` → WebSocket connection to that agent
- `self.ui_clients`: List of connected UI client WebSockets
- `self.ui_sessions`: Dictionary mapping UI WebSocket → authenticated user data (JWT payload)
- `self.agent_cards`: Dictionary mapping `agent_id` → `AgentCard` (self-description)
- `self.agent_capabilities`: Dictionary mapping `agent_id` → list of tool definitions
- `self.pending_requests`: Dictionary mapping `request_id` → `asyncio.Future` for correlating MCP request/response pairs

**Key Responsibilities:**

1. **Agent Discovery**: A background task (`_monitor_agents`) continuously polls ports 8003–8012 every 5 seconds, attempting to fetch agent cards via HTTP GET to `/.well-known/agent-card.json`. When a new agent is found, it establishes a persistent WebSocket connection to `/agent` and receives a `RegisterAgent` message containing the agent's full capability manifest.

2. **UI Client Management**: The orchestrator accepts WebSocket connections from browser clients on `/ws`. Upon connection, the client must send a `RegisterUI` message containing an authentication token. The orchestrator validates this token against Keycloak's JWKS endpoint and establishes an authenticated session.

3. **Multi-Turn ReAct Tool Routing**: When a user sends a chat message, the orchestrator enters a ReAct loop (up to 10 turns) where it:
   - Constructs a system prompt with available tools and file context
   - Calls the LLM with the full conversation history and tool definitions
   - If the LLM returns tool calls: executes them (sequentially or in parallel), renders results, and loops back for the LLM to analyze
   - If the LLM returns a final text response: parses it for potential UI components and renders the result

4. **Component Combining**: The orchestrator includes an LLM-powered component combining system that can merge or condense multiple saved UI components into cohesive unified views.

5. **Chat Title Summarization**: Automatically generates concise 3-5 word titles for new chats using the LLM.

### 3.2 Agent Framework

Each agent follows a standardized architecture pattern consisting of three files:

**Agent Main (`*_agent.py`)**: A FastAPI application that:
- Serves the A2A agent card at `/.well-known/agent-card.json`
- Provides a health check endpoint at `/health`
- Accepts WebSocket connections from the orchestrator at `/agent`
- On WebSocket connection, immediately sends a `RegisterAgent` message
- Listens for `MCPRequest` messages and dispatches them to the MCP server
- Runs tool functions in a thread pool via `asyncio.to_thread()` to avoid blocking the event loop

**MCP Server (`mcp_server.py`)**: A dispatcher that:
- Maintains a `TOOL_REGISTRY` dictionary mapping tool names to their functions, descriptions, and input schemas
- Handles `tools/list` requests by returning the full tool catalog
- Handles `tools/call` requests by invoking the registered function with the provided arguments
- Classifies errors as retryable or non-retryable based on exception type
- Extracts UI components from tool results and packages them into `MCPResponse` objects

**MCP Tools (`mcp_tools.py`)**: The actual tool implementations that:
- Accept typed arguments with sensible defaults
- Return dictionaries with `_ui_components` (list of serialized UI primitives) and `_data` (raw data for LLM consumption) keys
- Construct rich UI layouts using the shared primitives library

### 3.3 Protocol Layer

The protocol layer (`shared/protocol.py`) defines the message types used for all inter-component communication:

**Base Message**: All messages inherit from a `Message` dataclass with a `type` field. The `Message.from_json()` factory method deserializes JSON strings into the appropriate message subclass based on the `type` discriminator.

**MCP Protocol**:
- `MCPRequest`: Contains `request_id`, `method` (`tools/list` or `tools/call`), and `params` (tool name + arguments)
- `MCPResponse`: Contains `request_id`, `result` (data), `error` (with `message`, `code`, and `retryable` fields), and `ui_components` (serialized UI primitives)

**UI Protocol**:
- `UIEvent`: Client → Server events with `action` (e.g., `chat_message`, `get_dashboard`, `save_component`) and `payload`
- `UIRender`: Server → Client rendering instructions containing a list of UI component JSON objects
- `UIUpdate`/`UIAppend`: Incremental UI update mechanisms

**A2A Protocol**:
- `AgentCard`: Self-description containing `name`, `description`, `agent_id`, `version`, and `skills` list
- `AgentSkill`: Individual capability with `name`, `description`, `id`, `input_schema`, `output_schema`, and `tags`
- `RegisterAgent`: Sent when an agent connects, carrying the full `AgentCard`
- `RegisterUI`: Sent when a browser client connects, carrying the authentication `token`

### 3.4 Server-Driven UI Primitives

The primitives library (`shared/primitives.py`) defines 20+ UI component types as Python dataclasses:

| Primitive | Description | Key Fields |
|-----------|-------------|------------|
| `Container` | Generic wrapper with children | `children` |
| `Text` | Text display with variants | `content`, `variant` (body/h1/h2/h3/caption/markdown) |
| `Card` | Titled container with content | `title`, `content`, `variant` |
| `Table` | Data table | `headers`, `rows`, `variant` |
| `MetricCard` | KPI display | `title`, `value`, `subtitle`, `progress`, `variant` |
| `Alert` | Status messages | `message`, `title`, `variant` (info/success/warning/error) |
| `ProgressBar` | Progress indicator | `value`, `label`, `show_percentage` |
| `Grid` | Multi-column layout | `columns`, `children`, `gap` |
| `BarChart` | Bar chart | `title`, `labels`, `datasets` |
| `LineChart` | Line chart | `title`, `labels`, `datasets` |
| `PieChart` | Pie chart | `title`, `labels`, `data`, `colors` |
| `PlotlyChart` | Full Plotly.js chart | `title`, `data`, `layout`, `config` |
| `CodeBlock` | Syntax-highlighted code | `code`, `language`, `show_line_numbers` |
| `Tabs` | Tabbed interface | `tabs` (list of `TabItem`) |
| `Collapsible` | Expandable section | `title`, `content`, `default_open` |
| `FileUpload` | File upload control | `label`, `accept`, `action` |
| `FileDownload` | Download link | `label`, `url`, `filename` |
| `Button` | Interactive button | `label`, `action`, `payload`, `variant` |
| `Input` | Text input | `placeholder`, `name`, `value` |
| `Image` | Image display | `url`, `alt`, `width`, `height` |
| `Divider` | Horizontal rule | `variant` |

Each primitive serializes to a JSON dictionary via `to_json()`, and the `create_ui_response()` helper packages a list of components into the standard `{_ui_components, _data}` response format.

### 3.5 Frontend Architecture

The frontend is built with **React 18 + TypeScript + Vite** and uses **Tailwind CSS** for styling.

**Key Components:**

- **`App.tsx`**: Root component that gates access behind authentication, extracts user roles from JWT tokens, and renders the dashboard layout with the chat interface.

- **`DynamicRenderer.tsx`** (~960 lines): The core rendering engine that maps backend UI primitive JSON objects to React components. It includes:
  - A recursive `renderComponent()` function that dispatches on the `type` field
  - Individual render functions for each primitive type (e.g., `RenderCard`, `RenderTable`, `RenderMetric`)
  - An `extractSavableComponents()` function that recursively finds components suitable for saving to the drawer
  - An `AddAllToUIButton` component for batch-saving tool results
  - A `RenderErrorBoundary` class component for graceful error handling
  - Full Plotly.js integration for interactive charts
  - Markdown rendering via `react-markdown`

- **`ChatInterface.tsx`** (~646 lines): Real-time chat interface with:
  - Message input with file attachment support
  - File upload to the backend via REST API with progress tracking
  - Dynamic message rendering (user messages as text, assistant messages through `DynamicRenderer`)
  - Chat status indicators (thinking, executing, retrying, done)
  - Suggestion chips for common queries
  - Integration with the saved components drawer

- **`UISavedDrawer.tsx`**: A slide-out panel that displays saved UI components with:
  - Drag-and-drop combination of components
  - LLM-powered "condense all" functionality
  - Delete and manage individual saved components
  - Visual indicators in the chat history sidebar

- **`DashboardLayout.tsx`**: The main layout shell with sidebar navigation, agent status indicators, chat history list, and the admin panel (for agent creation when in admin role).

**Key Hooks:**

- **`useWebSocket.ts`**: Custom hook managing the WebSocket connection lifecycle, message parsing, state management for messages/agents/chat history/saved components, and automatic reconnection.

- **`useSmartAuth.ts`**: Authentication hook that dynamically switches between real Keycloak OIDC auth (`react-oidc-context`) and mock auth based on the `VITE_USE_MOCK_AUTH` environment variable.

### 3.6 Authentication and Authorization

AstralBody implements a **Backend-for-Frontend (BFF)** authentication pattern:

1. **Keycloak Integration**: The system uses Keycloak as its OIDC Identity Provider, configured under the `Astral` realm with an `astral-frontend` client.

2. **BFF Token Proxy** (`auth.py`): The frontend sends OIDC authorization code exchange requests to `/auth/token` on the backend, which injects the `client_secret` server-side before forwarding to Keycloak. This ensures the client secret never reaches the browser.

3. **WebSocket Authentication**: When a UI client connects via WebSocket, it sends a `RegisterUI` message with the access token. The orchestrator validates this token by fetching Keycloak's JWKS endpoint and verifying the JWT signature (RS256), issuer, and authorized party (`azp`) claim.

4. **REST API Authentication**: File upload/download endpoints use FastAPI's dependency injection with `HTTPBearer` security, extracting and validating tokens from the `Authorization` header or query parameters (for SSE endpoints).

5. **Role-Based Access Control**: The system extracts roles from both `realm_access.roles` and `resource_access.{client_id}.roles` in the JWT payload. Users must have either the `user` or `admin` role to access the system. Admin-only features (like agent creation) require the `admin` role.

6. **Mock Auth Mode**: For development, setting `VITE_USE_MOCK_AUTH=true` bypasses Keycloak entirely, using a mock auth context that simulates login with a dev user having both admin and user roles.

### 3.7 Data Persistence Layer

**Database** (`shared/database.py`): SQLite database with the following schema:

- **`chats`**: `id` (PK), `user_id`, `title`, `created_at`, `updated_at`, `has_saved_components`
- **`messages`**: `id` (auto-increment PK), `chat_id` (FK), `user_id`, `role`, `content` (JSON-serialized), `timestamp`
- **`saved_components`**: `id` (PK), `chat_id` (FK), `user_id`, `component_data` (JSON), `component_type`, `title`, `created_at`
- **`chat_files`**: `id` (auto-increment PK), `chat_id` (FK), `user_id`, `original_name`, `backend_path`, `uploaded_at`
- **`logs`**: `id` (auto-increment PK), `level`, `component`, `message`, `timestamp`

The `Database` class provides connection-per-request semantics for thread safety in SQLite's single-writer model. The schema includes automatic migration for adding `user_id` columns to support multi-tenancy retroactively.

**History Manager** (`orchestrator/history.py`): Business logic layer over the database providing:
- Chat CRUD operations with user scoping
- Message serialization (JSON content for UI components, plain text for user messages)
- Automatic JSON → SQLite migration for legacy data
- Saved component management with atomic replace operations for component combining
- File mapping management (tracking uploaded file original names → backend paths)

### 3.8 LLM Integration and Tool Routing

The LLM integration is one of the most sophisticated aspects of AstralBody:

**LLM Client Configuration:**
- Uses the OpenAI-compatible API client (`openai` Python package)
- Connects to a self-hosted vLLM server at `https://api-llm-factory.ai.uky.edu/v1`
- Currently configured for `DeepSeek-V3.2` model
- 180-second timeout for large model inference
- Configurable via environment variables (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`)

**Multi-Turn ReAct Loop:**

```
User Message → [System Prompt + History + Tools] → LLM
                                                    │
                    ┌───────────────────────────────┘
                    ▼
              Tool Calls?  ──Yes──→ Execute Tools (parallel/sequential)
                    │                        │
                    No                       ▼
                    │              Append results to conversation
                    ▼                        │
              Parse Final Response ←─────────┘
                    │                (loop back to LLM)
                    ▼
              Render UI Components
```

The loop runs for up to 10 turns, with the orchestrator:
1. Building tool definitions from all connected agents' capabilities
2. Including the last 10 messages of conversation history
3. Including file mapping context for uploaded files
4. Sending the full context to the LLM with `tool_choice: "auto"`
5. Processing tool calls by dispatching to the appropriate agent via WebSocket MCP
6. Appending tool results back to the conversation for the next LLM turn
7. On final response: parsing for JSON UI components, validating the component tree, and rendering

**Retry and Resilience:**
- LLM calls: Up to 5 retries with exponential backoff (1s, 2s, 4s, 8s)
- Distinguished between transient errors (502, 503, 504) and fatal errors (424, 401, 403)
- Tool execution: Up to 5 retries with backoff, with error classification (retryable vs. non-retryable)
- UI error recovery: If the LLM produces malformed JSON components, the orchestrator sends a correction prompt and retries

### 3.9 Deployment Infrastructure

**Docker Multi-Stage Build:**
- **Stage 1** (`node:20-alpine`): Builds the React frontend with Vite, outputting to `dist/`
- **Stage 2** (`python:3.11-slim`): Installs Python dependencies, copies backend source, copies compiled frontend, and sets up the entrypoint

**Docker Compose:**
- Single service (`astralbody`) exposing ports 8001 (orchestrator gateway) and 5173 (static frontend)
- Persistent volumes for `backend/data` (database) and `backend/tmp` (uploaded files)
- Environment from `.env` file
- Restart policy: `unless-stopped`

**Process Management** (`start.py`):
- Auto-discovers agent directories by scanning `backend/agents/` for folders containing `*_agent.py` files
- Starts the orchestrator first, then each agent on sequential ports starting at 8003
- Handles graceful shutdown with `taskkill` on Windows or `SIGTERM` on Unix

---

## 4. Detailed Component Analysis

### 4.1 Specialist Agents

**General Agent** (Port 8003, 8 tools):
- `generate_dynamic_chart`: Creates charts from arbitrary data, auto-detecting chart type
- `modify_data`: Applies row-based transformations to CSV/Excel files using safe expression evaluation
- `get_system_status`: Comprehensive system metrics (CPU, memory, disk)
- `get_cpu_info`, `get_memory_info`, `get_disk_info`: Detailed hardware monitoring
- `search_wikipedia`: Wikipedia article search with formatted results
- `search_arxiv`: Academic paper search with LLM-extracted search terms

**Medical Agent** (Port 8004, 5+ tools):
- `search_patients`: Filters mock patient records by age range and condition
- `generate_synthetic_patients`: Creates synthetic patient CSV datasets
- `analyze_patient_data`: Analyzes patient datasets with file upload prompts
- `analyze_generic_data`: Processes CSV data with missing data strategies
- `analyze_csv_file`: Reads and analyzes backend-stored CSV files

**Weather Agent** (Port 8005, 9 tools):
- `geocode_location`: City/state to coordinates via Open-Meteo geocoding API
- `get_current_weather`: Current conditions (temperature, humidity, wind, etc.)
- `get_extended_weather`: UV index, air quality, sunrise/sunset
- `get_historical_weather`: Date-range historical data with validation
- `get_weather_alerts`: Severe weather alerts (US only, via NWS API)
- `compare_locations`: Side-by-side weather comparison for up to 3 locations
- `get_hourly_forecast`: Detailed hourly predictions
- Plus daily and weekly forecast tools

### 4.2 Progress and Streaming System

The progress system (`shared/progress.py`) provides structured progress tracking:

- `ProgressPhase` enum: GENERATION, TESTING, INSTALLATION
- `ProgressStep` enum: 17 granular steps from PROMPT_CONSTRUCTION through TESTING_COMPLETE
- `ProgressEvent`: Structured event with phase, step, percentage (0-100), message, and optional data
- `ProgressEmitter`: Utility class with throttling (minimum 100ms between events), SSE formatting, and automatic percentage calculation based on phase/step mapping

### 4.3 Expression Evaluator

The expression evaluator (`shared/expression_evaluator.py`) provides safe Python expression evaluation for data transformation:

- **AST Validation**: Parses expressions into ASTs and validates against a whitelist of safe node types
- **Sandboxed Execution**: Restricted `eval()` with controlled `__builtins__` (only safe functions like `int`, `float`, `str`, `len`, `round`, `abs`, `min`, `max`, `sum`)
- **Math/NumPy Support**: Includes `math.sqrt`, `math.log`, `np.where`, etc.
- **Batch Evaluation**: Efficiently evaluates expressions across multiple rows with compiled code reuse
- **Security**: Blocks attribute access except for whitelisted methods (`get`, `lower`, `upper`, `strip`, `replace`, `str`, `contains`)

### 4.4 Component Combining System

The component combining system allows users to merge saved UI components:

1. **Combine** (2 components): The LLM analyzes whether two components contain related data (e.g., patient data + disease chart) and produces a unified component using grids, cards, and tables. If incompatible, it returns an error.

2. **Condense** (N components): The LLM groups related components together (e.g., all system metrics into one dashboard), keeping unrelated components separate, with the goal of reducing total component count while preserving all data.

The LLM receives a detailed schema description of all valid UI primitive types and must output valid JSON conforming to the component structure. The orchestrator validates the output, recursively fixing invalid component types and wrapping unknown types in cards.

---

## 5. Communication Flows

### 5.1 User Chat Message Flow

```
1. User types message in ChatInterface
2. Frontend sends UIEvent{action: "chat_message", payload: {message, chat_id}} via WebSocket
3. Orchestrator validates authentication (ui_sessions check)
4. Creates chat if needed, saves user message to history
5. Kicks off async title summarization for new chats
6. Builds tool definitions from all connected agents
7. Constructs system prompt with file context and conversation history
8. REACT LOOP:
   a. Sends messages + tools to LLM
   b. LLM returns tool_calls → orchestrator executes via MCP:
      - Sends MCPRequest to agent WebSocket
      - Agent dispatches to tool function
      - Agent returns MCPResponse with UI components
      - Orchestrator renders collapsible tool results
      - Appends tool output to conversation
      - Sends "thinking" status, loops to (a)
   c. LLM returns final text → orchestrator:
      - Attempts to parse as JSON UI components
      - Falls back to wrapping in Card with markdown Text
      - Sends UIRender to client
      - Saves to history
      - Sends "done" status
```

### 5.2 Agent Discovery Flow

```
1. _monitor_agents background task runs every 5 seconds
2. For each port 8003-8012:
   a. HTTP GET http://localhost:{port}/.well-known/agent-card.json
   b. If 200: parse AgentCard, check if already connected
   c. If new: establish WebSocket to ws://localhost:{port}/agent
   d. Receive RegisterAgent message with full capability manifest
   e. Store agent in self.agents, self.agent_cards, self.agent_capabilities
   f. Notify all UI clients of new agent
```

---

## 6. Comparison with Existing Systems

### 6.1 vs. LangChain / LangGraph

**LangChain** is the most widely adopted framework for building LLM applications. **LangGraph** extends it with stateful, multi-actor workflows using a graph-based execution model.

| Dimension | AstralBody | LangChain/LangGraph |
|-----------|------------|---------------------|
| **Architecture** | Centralized orchestrator with autonomous agents as services | Library-based chains/graphs within a single process |
| **Agent Communication** | WebSocket + A2A + MCP protocols | In-process function calls |
| **UI Generation** | Server-driven UI primitives rendered as React components | Text/markdown output; UI is separate concern |
| **Agent Discovery** | Dynamic at runtime via agent cards | Static, configured at development time |
| **Tool Invocation** | Network-based MCP protocol with retries | Direct function calls, in-process |
| **Multi-tenancy** | Built-in user isolation via JWT | Not built-in; must be implemented manually |
| **State Management** | SQLite persistence with full history | LangGraph has checkpointing; LangChain has memory modules |
| **Deployment** | Docker monolith with auto-discovery | Typically deployed as part of a larger application |

**Key Differences**: LangChain is a library meant to be embedded in applications, while AstralBody is a complete platform. LangChain excels at flexibility and ecosystem breadth (hundreds of integrations), while AstralBody excels at providing a complete, production-ready system with built-in UI, auth, and multi-tenancy. LangGraph's graph-based workflow model is more sophisticated for complex, branching workflows, whereas AstralBody's ReAct loop is simpler but sufficient for its use cases.

### 6.2 vs. AutoGen (Microsoft)

**AutoGen** is Microsoft's framework for building multi-agent conversational systems where multiple AI agents collaborate through conversation.

| Dimension | AstralBody | AutoGen |
|-----------|------------|---------|
| **Agent Model** | Specialist agents with MCP tools, coordinated by orchestrator | Conversational agents that talk to each other |
| **Coordination** | Central orchestrator makes all routing decisions | Agents negotiate directly; group chat manager optional |
| **UI** | Rich server-driven React UI | Text-based conversation logs |
| **Human-in-Loop** | Via chat interface with interactive components | Built-in human proxy agent |
| **Tool Model** | Tools return structured UI + data | Tools return text |
| **Deployment** | Agents as separate services | Agents as Python objects in one process |

**Key Differences**: AutoGen's key innovation is agent-to-agent conversation where agents can debate, critique, and refine each other's outputs. AstralBody takes a more structured approach where the orchestrator (not the agents) makes all coordination decisions. AutoGen is research-focused and excellent for exploring multi-agent collaboration patterns, while AstralBody is production-focused with authentication, persistence, and a polished UI.

### 6.3 vs. CrewAI

**CrewAI** focuses on role-based multi-agent collaboration with a "crew" metaphor.

| Dimension | AstralBody | CrewAI |
|-----------|------------|--------|
| **Agent Roles** | Specialist agents with specific tools | Role-based agents with goals and backstories |
| **Task Orchestration** | LLM-powered ReAct loop | Sequential or hierarchical task delegation |
| **Process Types** | Single ReAct loop with parallel tool execution | Sequential, hierarchical, and consensual processes |
| **UI** | Full web application with dynamic rendering | CLI output; web UI via integration |
| **Networking** | Agents as separate services (A2A) | In-process agents |
| **Persistence** | SQLite with user sessions | Limited built-in persistence |

**Key Differences**: CrewAI excels at defining complex role-based workflows with rich agent personas. AstralBody focuses more on tool execution and UI generation. CrewAI's hierarchical process model is more flexible for complex orchestration patterns, while AstralBody's single ReAct loop is simpler and more predictable.

### 6.4 vs. OpenAI Assistants API / GPTs

**OpenAI's Assistants API** provides a hosted agent runtime with tool calling, file handling, and thread-based conversation management.

| Dimension | AstralBody | OpenAI Assistants/GPTs |
|-----------|------------|------------------------|
| **Hosting** | Self-hosted, on-premise capable | Cloud-hosted (OpenAI servers) |
| **LLM** | Any OpenAI-compatible API (DeepSeek, Llama, etc.) | OpenAI models only (GPT-4, o1, etc.) |
| **Custom Tools** | Full custom tool development with rich UI responses | Code Interpreter, File Search, or function calling |
| **UI** | Custom React application with 20+ component types | ChatGPT interface or API |
| **Multi-Agent** | Multiple specialist agents with independent lifecycles | Single assistant per thread |
| **Data Privacy** | Full control, on-premise deployment | Data processed on OpenAI servers |
| **Cost** | Open-source, self-hosted LLM costs only | Per-token pricing |
| **Authentication** | Keycloak OIDC with role-based access | API key authentication |

**Key Differences**: The Assistants API is significantly easier to get started with and offers sophisticated built-in capabilities (Code Interpreter, vector store search). AstralBody offers complete control over data, model choice, UI, and deployment—critical for healthcare and regulated environments where data cannot leave organizational boundaries.

### 6.5 vs. Semantic Kernel (Microsoft)

**Semantic Kernel** is Microsoft's SDK for integrating AI services into applications with a focus on enterprise scenarios.

| Dimension | AstralBody | Semantic Kernel |
|-----------|------------|-----------------|
| **Language** | Python backend + TypeScript frontend | C#, Python, Java |
| **Architecture** | Complete platform with UI | SDK/library for embedding in applications |
| **Plugin Model** | MCP tools returning UI primitives | Plugins with semantic function descriptions |
| **Memory** | SQLite with chat history | Pluggable memory with vector stores |
| **Planner** | LLM ReAct loop | Handlebars, Stepwise, and Function Calling planners |
| **Enterprise Focus** | Authentication and multi-tenancy | Azure integration, enterprise connectors |

**Key Differences**: Semantic Kernel is deeply integrated with the Microsoft ecosystem (Azure OpenAI, M365, etc.) and focuses on enterprise application integration. AstralBody is more self-contained and focused on providing a complete, standalone research platform.

### 6.6 vs. Haystack (deepset)

**Haystack** is an end-to-end framework for building NLP/RAG pipelines.

| Dimension | AstralBody | Haystack |
|-----------|------------|----------|
| **Focus** | Multi-agent orchestration with dynamic UI | Document search and RAG pipelines |
| **Pipeline Model** | ReAct loop with tool calling | Directed graph of components |
| **UI** | Full React application | REST API; UI via Haystack Studio |
| **Agent Model** | Multiple specialist agents as services | Single agent with pipeline-based tools |
| **Document Handling** | File upload/download with mapping | Full document processing pipeline (ingestion, embedding, retrieval) |

**Key Differences**: Haystack excels at document-centric applications (search, QA, RAG) while AstralBody excels at tool-centric agent workflows with rich UI. They address different segments of the AI application space.

### 6.7 vs. Streamlit / Gradio

**Streamlit** and **Gradio** are rapid prototyping frameworks for building data applications and ML demos.

| Dimension | AstralBody | Streamlit/Gradio |
|-----------|------------|------------------|
| **UI Model** | Server-driven JSON primitives → React rendering | Python-defined widgets → auto-generated UI |
| **Agent Support** | Multi-agent orchestration built-in | None built-in; manual integration |
| **Real-time Communication** | WebSocket-based bidirectional | HTTP request/response (Streamlit has some WebSocket) |
| **Production Readiness** | Authentication, multi-tenancy, Docker | Basic auth; Streamlit Cloud/HuggingFace Spaces |
| **Component Library** | 20+ primitives optimized for agent output | Extensive widget library for general data apps |
| **Deployment** | Self-hosted with Docker | Cloud platforms or self-hosted |

**Key Differences**: Streamlit and Gradio are excellent for rapid prototyping and demos but lack the multi-agent orchestration, real-time WebSocket communication, and production security features that AstralBody provides. AstralBody's server-driven UI model is conceptually similar to Streamlit's approach but implemented at a lower level with more control.

### 6.8 vs. Google A2A Protocol

**Google's Agent-to-Agent (A2A) Protocol** is an open specification for agent interoperability that AstralBody partially implements.

| Dimension | AstralBody | Full A2A Spec |
|-----------|------------|---------------|
| **Agent Cards** | Implemented (/.well-known/agent-card.json) | Fully specified with more fields |
| **Discovery** | Port-range polling | DNS/registry-based discovery |
| **Task Management** | Orchestrator-managed ReAct loop | Structured task lifecycle (submitted, working, completed) |
| **Streaming** | WebSocket-based messages | SSE-based streaming with task updates |
| **Push Notifications** | Not implemented | Webhook-based push notifications |
| **Authentication** | Keycloak JWT | OAuth 2.0 / API keys |

**Key Differences**: AstralBody adopts the A2A discovery pattern (agent cards) but implements its own orchestration layer on top rather than using the full A2A task management protocol. The full A2A spec is more suitable for decentralized, internet-scale agent ecosystems, while AstralBody's approach is optimized for a controlled, organization-internal deployment.

### 6.9 Comparative Summary Table

| Feature | AstralBody | LangChain | AutoGen | CrewAI | OpenAI Assistants | Semantic Kernel |
|---------|------------|-----------|---------|--------|-------------------|-----------------|
| **Multi-Agent** | ✅ Services | ❌ Library | ✅ Conversational | ✅ Role-based | ❌ Single | ❌ Library |
| **Server-Driven UI** | ✅ 20+ types | ❌ | ❌ | ❌ | ❌ | ❌ |
| **A2A Discovery** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **MCP Protocol** | ✅ | ✅ (partial) | ❌ | ❌ | ❌ | ❌ |
| **Self-Hosted LLM** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Authentication** | ✅ Keycloak | ❌ | ❌ | ❌ | API Key | ✅ Azure AD |
| **Multi-Tenancy** | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Persistence** | ✅ SQLite | ✅ Pluggable | ❌ | ❌ | ✅ Threads | ✅ Pluggable |
| **ReAct Loop** | ✅ 10 turns | ✅ | ✅ | ✅ Sequential | ✅ | ✅ |
| **Parallel Tools** | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **File Handling** | ✅ Upload/Download | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Docker Deploy** | ✅ | ❌ (library) | ❌ | ❌ | N/A (hosted) | ❌ (library) |

---

## 7. Novel Contributions and Key Differentiators

1. **Server-Driven UI for Agent Systems**: AstralBody appears to be unique in combining multi-agent orchestration with a comprehensive server-driven UI primitive system. While "agentic" frameworks focus on text-based reasoning, AstralBody agents produce rich, interactive visualizations as first-class outputs.

2. **Unified Protocol Stack**: The combination of A2A (for agent discovery) and MCP (for tool invocation) with a custom UI protocol creates a clean, layered communication architecture that separates concerns (discovery, invocation, presentation).

3. **LLM-Powered Component Combining**: The ability to use the LLM to intelligently merge and condense UI components is a novel approach to dashboard assembly, allowing users to build custom views from agent outputs without manual configuration.

4. **Domain-Specific Agent Design for Healthcare**: The medical agent with synthetic patient generation, CSV analysis, and data modification tools, combined with the security architecture (Keycloak, role-based access, on-premise deployment), makes the system specifically suited for healthcare research environments where data privacy is paramount.

5. **Dynamic Agent Auto-Discovery**: The continuous port-scanning auto-discovery pattern means new agents can be deployed without any configuration changes to the orchestrator—they simply need to serve an agent card on a port within the scanned range.

6. **Safe Expression Evaluation**: The AST-validated expression evaluator provides a secure way for users to define data transformations without arbitrary code execution risk—an important safety feature for healthcare environments.

---

## 8. Limitations and Future Work

1. **Single-Node Deployment**: Currently, all agents must run on the same host (localhost port scanning). A distributed deployment model with service registry (e.g., Consul, Kubernetes) would enable horizontal scaling.

2. **SQLite Limitations**: SQLite's single-writer model may become a bottleneck under concurrent load. Migration to PostgreSQL or a similar RDBMS would improve scalability.

3. **Limited RAG Capabilities**: The system lacks built-in vector search or document embedding. Adding Retrieval-Augmented Generation would significantly enhance its utility for knowledge-intensive domains.

4. **No Agent-to-Agent Collaboration**: Unlike AutoGen, agents in AstralBody cannot communicate directly with each other; all coordination flows through the orchestrator. Enabling direct agent collaboration could unlock more sophisticated workflows.

5. **Static Tool Definitions**: Agent tools are defined at development time. A system for dynamically generating or modifying tools at runtime (perhaps using the LLM to write tool code) would increase flexibility.

6. **Limited Streaming**: While the system streams status updates (thinking, executing), it does not stream LLM token generation in real-time, which could improve perceived responsiveness.

7. **Testing Infrastructure**: The system would benefit from more comprehensive integration tests, particularly for the multi-turn ReAct loop and component combining system.

---

## 9. Conclusion

AstralBody represents a novel approach to multi-agent AI systems that prioritizes production readiness, rich user experience, and domain-specific utility. By combining server-driven UI primitives with standards-based agent communication (A2A + MCP), LLM-powered autonomous orchestration, and enterprise-grade authentication, it addresses a gap in the current landscape between research-oriented agent frameworks (LangChain, AutoGen, CrewAI) and production-ready but limited hosted solutions (OpenAI Assistants).

The system's architecture demonstrates that multi-agent systems can go beyond text-based reasoning to produce rich, interactive, saveable, and combinable visual outputs—making AI agents practical tools for professional workflows in domains like healthcare, scientific research, and data analysis.

Its key innovation—treating UI generation as a first-class concern of the agent framework rather than an afterthought—offers a template for how future agent systems might bridge the gap between AI capabilities and professional user needs.

---

*Document generated from codebase analysis on February 26, 2026. Based on AstralBody codebase at commit HEAD.*
