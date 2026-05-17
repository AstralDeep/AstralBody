# US-22: Claude Agents/Connectors

## User Story

> As a user, I want all the Claude agents/connectors :)

14 specialized agent capabilities spanning office productivity, creative tools,
and developer workflows.

## Architecture

Create a **Claude Connectors Agent** — a unified agent that bundles multiple
tool groups. Each connector is an MCP tool in the catalog. This avoids 14
separate agent processes and keeps the system manageable.

### Agent Skeleton

```
backend/agents/connectors/
├── __init__.py
├── connectors_agent.py    # BaseA2AAgent subclass
├── mcp_server.py           # Registers all connector tools
├── mcp_tools_office.py     # Excel, PowerPoint, Word, Outlook, Pitches
├── mcp_tools_design.py     # Canva, Design, Interactive Artifacts, Visual Graphs
├── mcp_tools_dev.py        # Code Review, Constitution Critique
├── mcp_tools_runtime.py    # Adaptive Runtime Intelligence (task routing)
└── mcp_tools_creative.py   # Blender, Adobe CC (stubs for now)
```

## Implemented Connectors (Priority 1)

### 1. Office Suite

**Excel** — Table generation + downloadable CSV
- Takes a query/description, returns a Table primitive + FileDownload
- CSV export button on table output

**PowerPoint** — Presentation outline generator
- Takes a topic, returns structured slide outline as Collapsible > Text
- Each slide = topic + bullet points

**Word** — Document generator
- Takes content request, returns formatted markdown + FileDownload
- Supports report-style document generation

**Outlook** — Email composer
- Takes recipient/subject/body, returns email preview + send confirmation
- Uses existing email infrastructure if available

**Pitch Templates** — Template generation
- Takes industry/purpose, returns pre-structured pitch deck outline
- 6 standard templates: startup, sales, investor, product, project, strategy

### 2. Developer Tools

**Code Review** — Automated code analysis
- Takes code snippet, returns structured review: issues, suggestions, security notes
- Returns Collapsible with Alert for criticals, Text for suggestions

**Constitution Critique** — Spec-driven development review
- Takes a spec document, evaluates against constitution principles
- Returns compliance matrix + actionable recommendations

### 3. Runtime Intelligence

**Adaptive Runtime Intelligence** — Smart task routing
- Analyzes incoming request to determine optimal agent dispatch
- Returns a routing recommendation card
- Uses LLM to classify intent → maps to available agents

## Stubbed Connectors (Priority 2)

These have tool definitions and response templates but return "requires external
API access" messages:

- Blender (3D tooling) — stub, needs Blender Python API server
- Adobe Creative Cloud — stub, needs Adobe API credentials
- Canva/Affinity — stub, needs Canva/affinity API
- Interactive Artifacts/Dashboards — generates dashboard layout specs
- Visual Graph Networks — generates Obsidian-style graph data
- Claude Design — UI/UX design suggestions

## FileDownload Primitive Fix

The existing FileDownload renders a download button that calls the server.
For generated content (CSV, markdown), we need to ensure the download URL
works correctly. The current implementation proxies through the API.

## Test Plan

- Agent startup and registration
- Each office tool returns valid primitives (Table, FileDownload, Collapsible)
- Excel CSV generation
- PowerPoint outline structure
- Word document markdown generation
- Pitch template selection
- Code review output structure
- Constitution critique output structure
- Adaptive routing recommendation format

## Constitution Compliance

- ✅ No new third-party libraries
- ✅ Uses existing BaseA2AAgent, MCPServer patterns
- ✅ All outputs rendered through existing primitives
- ✅ No database changes for agent definitions