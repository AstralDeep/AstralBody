<!--
SYNC IMPACT REPORT
==================
Version Change: 1.0.0 → 1.1.0 (MINOR bump: new principles added)

Modified Principles:
- None (existing principles unchanged)

Added Sections:
- VI. Agent Integration Testing (NON-NEGOTIABLE)
- VII. Agent Architecture Standardization

Removed Sections:
- None

Templates Requiring Updates:
- ✅ .specify/templates/plan-template.md (Constitution Check section should reference new agent testing principles)
- ✅ .specify/templates/spec-template.md (Should include agent integration testing in requirements)
- ✅ .specify/templates/tasks-template.md (Should include agent creation tasks with three-file pattern)
- ✅ .specify/templates/checklist-template.md (Should include agent validation checklist)
- ⚠️ .specify/templates/agent-file-template.md (May need updates for new agent standards)

Follow-up TODOs:
- Update agent creation documentation to reference backend/agents/general as reference
- Create integration test templates for new agents
- Add agent validation checklist to development workflow
-->

# Astral Constitution

## Core Principles

### I. Code Quality (NON-NEGOTIABLE)

All code must adhere to strict quality standards: comprehensive documentation, consistent style, linting, and peer review. Code must be modular, maintainable, and follow the project's architectural patterns. Technical debt must be tracked and addressed before accumulation.

### II. Testing Standards (NON-NEGOTIABLE)

Test-Driven Development (TDD) is mandatory for all features. Tests must be written before implementation, covering unit, integration, and contract tests. Test coverage must meet or exceed 80% for critical paths. All tests must pass before merging.

### III. User Experience Consistency

User interfaces and interactions must follow consistent design patterns, provide clear feedback, and maintain accessibility standards. UX must be validated with real users where possible. Error messages must be helpful and actionable.

### IV. Performance Requirements

Systems must meet defined performance benchmarks: latency under 200ms for interactive features, memory usage within budget, and scalability to handle expected load. Performance testing is required for all new features.

### V. Observability & Monitoring

All components must expose metrics, logs, and health checks. Real‑time monitoring must be enabled for production systems. Debuggability through structured logging is required.

### VI. Agent Integration Testing (NON-NEGOTIABLE)

All new specialist agents MUST include integration tests with the existing system architecture before being considered valid for deployment. Integration tests must verify:
- WebSocket connection establishment with the orchestrator
- Proper registration via A2A agent-card endpoint
- Correct handling of MCP tool requests and responses
- UI primitive generation and serialization
- Error handling and retry logic

Test coverage for agent integration must exceed 90% for connection logic. New agents without passing integration tests MUST NOT be merged into the main branch.

### VII. Agent Architecture Standardization

The connection logic and UI generation framework is contained in the `backend/agents/general` directory, which serves as the reference implementation. All new specialist agents MUST:

1. **Follow the three-file pattern**:
   - `{agent_name}_agent.py` - Main agent class with FastAPI server
   - `mcp_server.py` - MCP request dispatcher
   - `mcp_tools.py` - Tool registry with UI primitive functions

2. **Use proper naming conventions**:
   - Class names must reflect the agent's purpose (e.g., `MedicalAgent`, `ResearchAgent`)
   - File names must use the agent's name (e.g., `medical_agent.py`, not `general_agent.py`)
   - Docstrings must accurately describe the agent's specific capabilities

3. **Extend, don't copy**:
   - Use the general agent as a reference for connection patterns
   - Customize tool implementations for the agent's domain
   - Update agent card descriptions to reflect actual capabilities
   - Never copy documentation verbatim without context

4. **Maintain separation of concerns**:
   - Connection logic remains in the agent class
   - Tool dispatch remains in MCP server
   - UI generation remains in tool functions
   - Business logic specific to the agent's domain in tool implementations

## Implementation Guidelines
- **Focus on the Specialist Agent**: DO NOT ATTEMPT TO IMPLEMENT THE ORCHESTRATOR LOGIC or FRONTEND! The specialist agent is a completely backend service that PRODUCES UI definitions that are sent to the Orchestrator for rendering. If you need connection details for the orchestrator to test aspect of the specialist code, YOU MUST ASK THE USER FOR THOSE DETAILS! Do not create a frontend to test. You may only create the backend logic for the specialist agent.
- **Use of Python Virtual Environments**: You MUST use Python virtual environments before installing or running any Python code using `python -m venv .venv`.

## Development Standards

All development must follow the established workflow: feature specification → implementation plan → task breakdown → code review → automated testing → deployment. Code reviews are mandatory and must include at least one senior engineer. Continuous integration must run all tests and linting before merging.

## Security & Compliance

Security best practices must be integrated into the development lifecycle. All dependencies must be scanned for vulnerabilities. Authentication and authorization must be implemented following the principle of least privilege. Data protection regulations must be respected.

## Governance

Amendments to this constitution require a proposal, discussion, and approval by the project maintainers. Version increments follow semantic versioning: MAJOR for backward‑incompatible changes, MINOR for new principles or sections, PATCH for clarifications and non‑semantic refinements. All projects must undergo a compliance review before each major release.

**Version**: 1.1.0 | **Ratified**: 2026-01-06 | **Last Amended**: 2026-02-25
