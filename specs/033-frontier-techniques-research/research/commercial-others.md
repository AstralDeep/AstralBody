# Anthropic / Microsoft / Meta / Amazon / Vercel / startups — findings

Research date: 2026-06-16. Scope: mid-2026 frontier of agentic + server-driven-UI (SDUI) techniques across Anthropic, Microsoft, Meta, Amazon, Vercel, and notable agent startups (Perplexity, Replit, Cognition/Devin, Manus, Sierra, Decagon, Lindy, Genspark). Goal: novel, concretely implementable techniques where these vendors are AHEAD of AstralDeep, mapped to AstralDeep's constraints (Python backend only, no new third-party runtime libs, SDUI mandate, idempotent migrations, fail-closed).

AstralDeep **already has**: MCP tools, Artifacts-like SDUI (astralprims → webrender → ROTE device adaptation), a multi-round adaptive UI designer, agentic creation of agents/tools (codegen → self-test → security gate → admin approval), persistent workspace with stable component identity + snapshot timeline, cross-session memory + consolidation ("dreaming"), Keycloak OIDC + RFC 8693 delegated/attenuated tokens, hash-chained audit, PHI gate. Findings below are deliberately scoped **beyond** that baseline.

## Executive summary

- **The single most consequential cluster is context-engineering mechanics** (Anthropic's tool-search/`defer_loading`, programmatic tool calling, context editing; Manus's KV-cache stability, mask-don't-remove, recitation, keep-errors-in-context). Several of these name **direct contradictions** with AstralDeep's documented "builds tool lists per chat" and inject/remove-meta-tools behavior — a quantifiable cost/latency/reliability leak given agent loops run ~100:1 input:output token ratios.
- **Deterministic interception layers are the highest-leverage security/UX primitive AstralDeep lacks as a generic surface**: Claude Code Hooks (`PreToolUse` deny + arg-rewrite + `Stop`-block-until-verified) and Semantic Kernel Filters (ordered `(context, next)` middleware) generalize AstralDeep's hand-coded permission chokepoints into one configurable pipeline.
- **Runtime (in-conversation) supervision is a genuine gap**: Sierra/Decagon run parallel supervisor models that review each agent OUTPUT before it reaches the user (revise/escalate). AstralDeep's gate is creation-time only; once an agent is approved+scoped, its conversational outputs are unsupervised.
- **Device adaptation has a strong declarative analog AstralDeep can adopt**: Adaptive Cards Host Config + responsive `layouts[]`/`targetWidth` express ROTE's exact concern (one component → many devices) as **data**, not imperative Python adapters — plus per-element show/hide by width and `supportsInteractivity:false` for constrained targets.
- **Agentic-creation has cheaper/safer alternatives**: declarative agent manifests (Copilot Studio) define an agent as validated JSON (no arbitrary code → sidesteps the codegen security gate for the large class of instruction+capability+action agents); MCP elicitation + a manifest-first path reduce reliance on codegen.
- **Two orchestration patterns are pure-Python, no-new-lib lifts with high leverage**: the Magentic dual-ledger loop (Task Ledger + per-step Progress Ledger + stall-counter replanning) converts single-hop dispatch into a self-correcting multi-step controller; and parallel fan-out with **fresh-context sub-runs** (Manus Wide Research / managed Devins) fixes the documented >8-item context-degradation ("fabrication mode") failure that AstralDeep's single sequential loop hits on any list task.
- **The model-chooses-component-per-tool-call pattern (Vercel `streamUI` / AI SDK UI typed tool parts) is architecturally opposite to AstralDeep** (which arranges *finished* primitives *after* tools complete) and is the cleanest "UI frontier" gap, alongside streaming partial UI (`streamObject`/`useObject`) and inline pre-generation citation binding (Perplexity).
- **Agent identity + per-(agent,user) credential isolation extends AstralDeep's RFC 8693**: AgentCore Identity and Entra Agent ID give each agent a first-class principal, a token vault keyed by {agent + user} so third-party tokens are physically partitioned, and a 3-legged on-behalf-of-user consent primitive for *external* APIs — beyond AstralDeep's user-token attenuation.
- **AstralDeep is already at/above the frontier on several axes** (don't regress): native WebSocket + in-process `VirtualWebSocket` transport (Vercel is *catching up* with `ChatTransport`); it already self-tests created agents (gap is depth, not absence); deterministic fail-closed PHI gate (vs Llama Guard's tunable false positives); hash-chained tamper-evident audit (vs CloudWatch/Watchtower trails); stricter PII handling than AgentCore Memory's PII-ignore-by-default.

## Findings

### F1. Context editing — automatic in-loop eviction of stale tool results

- **Source**: Anthropic — Context Editing (Messages API). https://platform.claude.com/docs/en/build-with-claude/context-editing ; engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **What it is**: When input tokens cross a threshold, the API automatically clears old tool calls/results from the live window (leaving a tombstone placeholder), keeping the last N tool-use pairs while full history stays client-side. Strategy `clear_tool_uses_20250919` with `trigger` (default 100k), `keep` (default 3 pairs), `clear_at_least` (cache-aware), `exclude_tools`, `clear_tool_inputs`; a second strategy `clear_thinking_20251015` clears stale extended-thinking blocks.
- **Frontier evidence**: BETA, header `anthropic-beta: context-management-2025-06-27`, launched 2025-09-29. Anthropic reports ~84% token reduction over a 100-turn eval (+39% paired with the memory tool) — vendor-internal, workload-shaped.
- **AstralDeep gap**: AstralDeep's cross-session *memory* is the persistence axis; this is the opposite, in-loop axis — automatically evicting stale tool-call transcript from the *active window* mid-task so long agentic creation/multi-tool runs don't hit context rot or blow budget. AstralDeep pastes large MCP/tool outputs into context during long flows with no automatic "clear old results, keep last few, leave a tombstone, preserve cache" discipline (distinct from component pruning, which operates on the workspace, not the model's tool transcript).
- **Priority**: High
- **How to implement in AstralDeep**: In the `_call_llm` context assembler, track a running token estimate of the tool-call/result history; once over a threshold, replace all but the last N tool-result blocks with a short tombstone (`[earlier tool result cleared; re-call <tool> to refetch]`) while keeping the full record in the chat/audit store. Make `keep`, `trigger`, and an `exclude_tools` set config. Pure Python over the existing message list — no new dependency.
- **Novelty 4 / Impact 4 / Effort M**

### F2. Tool Search Tool — on-demand loading of tool *definitions* (`defer_loading`)

- **Source**: Anthropic — Tool Search Tool. https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool ; pattern: https://www.anthropic.com/engineering/code-execution-with-mcp
- **What it is**: Mark tools `defer_loading: true` plus add a search tool (`tool_search_tool_regex_20251119` / `_bm25_20251119`); the model sees only the search tool + a few hot tools up front, searches names/descriptions/arg-schemas on demand, and the API expands matched `tool_reference` blocks inline **without invalidating the cached prompt prefix**. Scales toward ~10,000 tools; MCP toolsets support `defer_loading` via the connector.
- **Frontier evidence**: Released server-side tool, versions dated 2025-11-19. Anthropic reports ~85% token reduction on MCP evals and recovered selection accuracy that otherwise degrades past 30–50 tools (a multi-server setup can burn ~55k tokens in definitions before any work). Amazon's AgentCore Gateway ships the identical pattern as `x_amz_bedrock_agentcore_search` (embeddings of every tool description, retrieve-relevant-first via standard MCP `tools/call`) — cross-vendor convergence: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html
- **AstralDeep gap**: AstralDeep integrates MCP *and* auto-creates tools, so its catalog grows unbounded — exactly this failure mode. If it loads all agent/tool schemas into context it pays the token tax and degrades selection as the catalog grows. There is no "search tools, expand on demand" meta-tool.
- **Priority**: High (highest ROI for AstralDeep's growing-catalog architecture)
- **How to implement in AstralDeep**: Add a `search_tools(query)` meta-tool that BM25/regex-matches over the registered agents' tool names+descriptions+arg-schemas and returns the top-k tool definitions to inject for that turn; keep only that meta-tool + a few high-frequency tools resolved up front. Critically, place the meta-tool and hot tools in a **stable prefix** (see F11) so expansion doesn't break the cache. Re-uses the existing tool registry; no new lib.
- **Novelty 4 / Impact 5 / Effort M**

### F3. Programmatic tool calling — orchestrate tools in a code sandbox; intermediate results never hit context

- **Source**: Anthropic — Programmatic Tool Calling. https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
- **What it is**: Mark a tool `allowed_callers: ["code_execution_20260120"]`; the model then writes Python that calls your tools as functions inside a code-execution container, looping/fanning-out/filtering/aggregating in code. Each tool call pauses the script, the API returns a `tool_use` with a `caller` field, you return the result into the running script, and **only the final stdout enters context** — raw intermediate outputs never do.
- **Frontier evidence**: Released for the 4.5+/2026 model line, version `code_execution_20260120` (Jan 20 2026). Reported ~38% fewer billed input tokens on a 75-tool benchmark; explicitly ~8% *worse* on strictly sequential single-call turns (per-workload, not blanket).
- **AstralDeep gap**: A different lever than F2: not "load less" but "never surface intermediate tool outputs." For AstralDeep's fan-out workloads (ml_services batch jobs, multi-source `research_brief`, "check X across N items") this collapses N round-trips into one and keeps hundreds of KB of raw results out of the window. AstralDeep has no code-orchestration-over-tools seam. (Caveat: shines on fan-out/large-result/filter; hurts on sequential single-call turns — gate by workload.)
- **Priority**: Medium
- **How to implement in AstralDeep**: This needs a sandbox to be safe (see F12); within constraints, a stdlib-only restricted subprocess can host a generated orchestration script whose `tool(...)` calls are marshalled back to the orchestrator's `execute_single_tool`, returning only stdout to the model. Reserve for fan-out/aggregation tools (flag per tool). Pairs with F2 (discover cheaply → orchestrate in code) and F12 (sandbox).
- **Novelty 4 / Impact 4 / Effort L**

### F4. MCP elicitation — server requests typed user input mid-tool-call

- **Source**: MCP spec (Anthropic-led). https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation ; enhancements: https://modelcontextprotocol.io/specification/2025-11-25/changelog
- **What it is**: While executing a tool, a server can pause and send `elicitation/create` with a `message` + a restricted `requestedSchema` (flat object, primitive props only, `format` ∈ email/uri/date/date-time); the client renders a form and the user responds with one of three actions — `accept` (+content), `decline`, or `cancel`. 2025-11-25 added single/multi-select titled enums, default values, and **URL-mode elicitation** (server hands the client a URL for an out-of-band flow like OAuth/payment). Rule: servers MUST NOT elicit sensitive info.
- **Frontier evidence**: Introduced spec 2025-06-18, enhanced 2025-11-25; stable in the spec ("may evolve"). MCP elicitation overlaps with Copilot Studio's "auto-generate a clarifying question to fill a missing required tool input" (https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-generative-actions) and Adaptive Cards input validation (`isRequired`/`errorMessage`).
- **AstralDeep gap**: AstralDeep's turn loop and agentic-creation self-test lack a *protocol-standard* mid-execution "stop and ask the user for typed, schema-validated input" with the explicit accept/decline/**cancel** distinction. A tool needing one more field today either fails or the orchestrator improvises. The three-action model + client-side validation + the "MUST NOT elicit sensitive info" policy are directly relevant to the PHI posture.
- **Priority**: Medium
- **How to implement in AstralDeep**: Add a `ui_elicit {message, schema}` WS message rendered as an astralprims form (re-use input primitives + ROTE), with accept/decline/cancel replies threaded back into the paused tool via the existing async-task plumbing; enforce a server-side "no sensitive fields" check on the schema. SDUI-native; no new lib.
- **Novelty 3 / Impact 3 / Effort M**

### F5. Claude Code Hooks — deterministic lifecycle interception (deny / rewrite-args / block-until-verified)

- **Source**: Anthropic — Claude Code Hooks. https://code.claude.com/docs/en/hooks ; SDK twin: https://code.claude.com/docs/en/agent-sdk/hooks
- **What it is**: User-configured commands firing at lifecycle events (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `SessionStart/End`) that run *outside the model* — guaranteed, not prompted. Each gets a JSON event on stdin and controls flow via exit code 2 = block, or structured JSON: `PreToolUse` returns `permissionDecision: allow|deny|ask` plus optional **`updatedInput`** to rewrite tool args in flight; `Stop`/`SubagentStop` can return `decision:"block"` to **refuse to let the agent end its turn** until a check passes; any hook can inject `additionalContext`.
- **Frontier evidence**: GA. The semantic twin in the agent-platform world is Semantic Kernel Filters (F6) and Llama Stack shields-as-config (F19) — three independent vendors converging on "ordered interception with deny/short-circuit."
- **AstralDeep gap**: AstralDeep enforces policy at hand-chosen chokepoints in orchestrator code (scopes, overrides, the security gate). Hooks are a generic, declarative interception layer across the whole loop: deny a tool *before* it runs, **rewrite its arguments**, inject context on every prompt, or **block "stop" until the PHI gate / lint / self-test is green** — without a code change per policy. For a platform whose pitch is safe agentic creation, the deny + `updatedInput` + `Stop`-block triad is the highest-leverage primitive it lacks as a configurable surface.
- **Priority**: High (top candidate)
- **How to implement in AstralDeep**: Define a small in-process hook registry keyed by event name; the orchestrator calls registered hooks at `pre_tool`, `post_tool`, `prompt_submit`, and a new `turn_end` checkpoint, each returning `{decision, updated_input?, context?}`. Ship the PHI gate, scope check, and audit as hooks; add a `turn_end` hook that blocks completion until self-test/lint passes for created-agent flows. Pure Python; reuses existing gate logic, just relocated into a uniform pipeline.
- **Novelty 4 / Impact 5 / Effort M**

### F6. Semantic Kernel Filters — ordered `(context, next)` middleware pipeline

- **Source**: Microsoft — SK Filters (GA). https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters ; GA post: https://devblogs.microsoft.com/semantic-kernel/announcing-the-ga-release-of-filters-for-net-and-python-in-semantic-kernel/
- **What it is**: Three composable interception points around the tool/prompt lifecycle, each a delegate-chained middleware where `await next(context)` proceeds and **not calling `next` short-circuits (= deny)**: (1) **Function Invocation Filter** (every call; inspect/override result, retry e.g. switch model); (2) **Prompt Render Filter** (before LLM submission; rewrite the rendered prompt for RAG injection or **PII/PHI redaction**, or replace it to skip the LLM = semantic cache); (3) **Auto Function Invocation Filter** (inside the auto-calling loop, with iteration counters and `context.Terminate = true` to stop early). Filters nest onion-style in registration order.
- **Frontier evidence**: GA (2024-11-21). Now folded into the unified **Microsoft Agent Framework** (GA v1.0, 2026-04-03 — https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/), which merged Semantic Kernel + AutoGen and standardizes middleware hooks + MCP (client+server) + A2A + checkpointed graph Workflows.
- **AstralDeep gap**: The cleanest analog to AstralDeep's permission gates + audit hooks, generalized into a formal, ordered, composable pipeline. AstralDeep's gates are bespoke call-site logic. Lifting the pattern gives a single home for permission+audit+result-override (function filter), one chokepoint for PHI/PII redaction before any `_call_llm` (prompt-render filter), and a budget/iteration governor (`Terminate`).
- **Priority**: High (pairs with F5 — same principle, agent-platform framing)
- **How to implement in AstralDeep**: Same registry as F5 but expressed as the onion `(context, next)` contract so filters compose and short-circuit; add a prompt-render filter that runs PHI/PII redaction on the final prompt string before every `_call_llm`. Pure Python.
- **Novelty 3 / Impact 5 / Effort M**

### F7. Adaptive Cards Host Config + responsive `layouts[]`/`targetWidth` — declarative device adaptation (the ROTE analog)

- **Source**: Microsoft — Adaptive Cards Host Config + Container Layouts. https://learn.microsoft.com/en-us/adaptive-cards/rendering-cards/host-config ; https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/container-layouts
- **What it is**: **Host Config** is a JSON config object *separate from the card* that tells a renderer how to realize platform-agnostic elements for a given environment — the same card renders differently per host purely by swapping the config (spacing integer scale, font sizes/weights, color palettes, `containerStyles`, `actions.maxActions` default 5, `supportsInteractivity` boolean that disables all actions for read-only surfaces). **Responsive `layouts`**: a container carries a `layouts` array tagged with `targetWidth` (enum `VeryNarrow|Narrow|Standard|Wide`, plus `atLeast:`/`atMost:`), and the renderer auto-switches layout by available width (Stack / Flow-with-wrap / AreaGrid named areas); individual elements also take `targetWidth` to show/hide per width, with declarative fallback to Stack when narrower.
- **Frontier evidence**: GA/stable (Host Config v1.0; `layouts` in schema 1.5+; doc updated 2026-04-01).
- **AstralDeep gap**: This is *exactly* ROTE's concern (adapt one component to browser/tablet/mobile/watch/TV/voice) but expressed as **declarative data** rather than imperative Python in `rote/adapter.py`. AstralDeep's per-device branching could become "select a config." `supportsInteractivity:false` (watch/voice), `maxActions` caps (small screens), per-element show/hide by width, and the VeryNarrow→Wide ladder (maps cleanly onto watch→TV) are clean copyable knobs AstralDeep lacks as a typed contract.
- **Priority**: High
- **How to implement in AstralDeep**: Define a `HostConfig`-shaped dict per ROTE device profile (spacing scale, palettes, `supports_interactivity`, `max_actions`) consumed by webrender; add an optional `layouts`/`target_width` field on astralprims container primitives and have the renderer pick the matching layout (else fall back to Stack). Turns ROTE adaptation into data + a small selector. No new lib.
- **Novelty 4 / Impact 4 / Effort M**

### F8. Adaptive Cards templating — `$data`/`$when`/`$host` (declarative data-binding, conditional UI, device-bound values)

- **Source**: Microsoft — Adaptive Card Templating. https://learn.microsoft.com/en-us/adaptive-cards/templating/ ; language: https://learn.microsoft.com/en-us/adaptive-cards/templating/language
- **What it is**: A layer that separates card layout from data, expanded by an SDK on backend or client. Binding syntax `${expression}`; **`$data`** binds an element to a collection so it repeats once per array item; **`$when`** drops an element when its boolean is false (declarative show/hide on data); reserved scopes `$root`/`$data`/`$index` and notably **`$host`** — a host-supplied data blob so templates can bind to *device/host* values at expansion time.
- **Frontier evidence**: GA (.NET + JS SDKs; `${}` since 2020). Hype flag: the public template *service* at templates.adaptivecards.io is an explicit proof-of-concept, not production.
- **AstralDeep gap**: AstralDeep's agents build primitives imperatively in Python (`Text(...)`, `Table(...)`). Templating is the declarative counterpart: a reusable layout template + a data payload, with `$data` array-repetition and `$when` conditional rendering as schema features instead of Python loops/ifs. Wins: smaller wire payloads (send template once, then deltas — relevant to `ui_upsert`), declarative conditional UI, and `$host` as the templating-side bridge to device adaptation (bind a primitive's content to ROTE/device values).
- **Priority**: Medium
- **How to implement in AstralDeep**: Add an optional template-expansion step in webrender: a primitive subtree may carry `${}`/`$data`/`$when` plus a `data` payload and a `$host` dict (the active ROTE device profile); expand server-side before render. Additive; agents keep imperative builders where preferred. No new lib (a small expression evaluator over the existing dict model).
- **Novelty 3 / Impact 3 / Effort M**

### F9. Magentic dual-ledger orchestrator — Task Ledger + per-step Progress Ledger + stall-counter replanning

- **Source**: Microsoft Research — Magentic-One / AutoGen. https://arxiv.org/abs/2411.04468 ; verbatim prompts: https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_magentic_one/_prompts.py ; productized in MAF: https://learn.microsoft.com/en-us/agent-framework/user-guide/workflows/orchestrations/magentic
- **What it is**: An Orchestrator LLM runs an outer planning loop + inner execution loop over two explicit structures. The **Task Ledger** (outer) is prompted under GIVEN/VERIFIED FACTS, FACTS TO LOOK UP, FACTS TO DERIVE, EDUCATED GUESSES + a bullet plan. The **Progress Ledger** (inner) is regenerated every step as strict JSON answering five questions — each with a `reason` AND `answer`: `is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`, `instruction_or_question`. A **stall counter** increments on detected loop/no-progress; over a threshold (≤2 paper / `max_stalls=3` code) it breaks to the outer loop, reflects/self-refines, updates the task ledger, revises the plan, and restarts — clearing agent context on each plan update.
- **Frontier evidence**: Paper Nov 2024; prompts stable in repo; GA in Microsoft Agent Framework 1.0 (`MagenticBuilder`, `max_round_count`/`max_stall_count`/`max_reset_count`). Hype flag: GAIA 38% / WebArena 32.8% — "competitive," not dominant; the *pattern* is the value.
- **AstralDeep gap**: AstralDeep's orchestrator is effectively single-hop request/response dispatch. The dual-ledger loop is a stateful, self-correcting, multi-step controller: an inspectable plan/facts object, a per-step structured self-assessment of done/looping/progress *with reasons*, and automatic replanning on a stall counter — exactly the introspection an audit/eval layer wants.
- **Priority**: High (highest-leverage single lift; pure prompt + two dicts + a counter over `_call_llm`)
- **How to implement in AstralDeep**: Add an optional orchestrator mode for multi-step turns: build a Task Ledger via one prompt, then loop — each step ask `_call_llm` for the Progress Ledger JSON, dispatch to the chosen specialist, track a stall counter, and on stall re-prompt the Task Ledger and restart. Fits the "Python-only, no new libs" posture; the JSON schema is copyable verbatim.
- **Novelty 4 / Impact 5 / Effort M**

### F10. Parallel fan-out with fresh-context sub-runs (Wide Research / managed Devins) — fixes the >8-item "fabrication mode"

- **Source**: Manus — Wide Research (https://manus.im/blog/introducing-wide-research, https://manus.im/blog/manus-wide-research-solve-context-problem); Cognition — "Devin can now manage Devins" (https://cognition.ai/blog/devin-can-now-manage-devins, Mar 19 2026). Convergent with Anthropic's multi-agent research pattern (https://www.anthropic.com/engineering/multi-agent-research-system).
- **What it is**: A controller decomposes a high-volume task and spawns N sub-agents **in parallel, each with its own FRESH EMPTY context window** (Manus: 100+ full instances, no inter-agent chat — all coordination via the controller); each child self-verifies before reporting; the controller scopes/monitors/resolves conflicts/compiles results. Explicitly a *context-window* solution: a single context degrades past ~8 items ("items 1-5 genuine, 6-8 generic, 9+ fabrication mode"), so fresh-context-per-item keeps the 50th item as well-researched as the first. Anthropic's variant: lead Opus spawns 3–5 parallel Sonnet subagents each returning ~1–2k-token distillates (+90.2% over single-agent on internal research eval, ~15× tokens).
- **Frontier evidence**: Manus Wide Research GA; managed Devins GA (decomposition algorithm undisclosed — vendor claim). Anthropic numbers vendor-internal.
- **AstralDeep gap**: AstralDeep's LLM runs tools in a single sequential loop in one context — the exact architecture this warns degrades past ~8 items. Any task over a list ("summarize these 40 attachments," "compare these 12 agents") hits the fabrication threshold. AstralDeep has background jobs but no controller-decomposes → isolated clean-context sub-runs → aggregate scatter/gather.
- **Priority**: High (largest architecture opportunity; expressible on existing infra)
- **How to implement in AstralDeep**: Reuse the in-process `VirtualWebSocket` (already used for self-test and auto-continue) to launch N isolated sub-turns each with a clean context + a single item's scope, run them concurrently with a bounded pool, and have the orchestrator aggregate distillates. Add per-child metering and a stall/timeout bound (F22). No new lib.
- **Novelty 4 / Impact 5 / Effort L**

### F11. KV-cache stable-prefix + append-only context — the 100:1 economics fix

- **Source**: Manus — "Context Engineering for AI Agents: Lessons from Building Manus." https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus (Jul 2025)
- **What it is**: KV-cache hit rate is "the single most important metric for a production-stage agent" (Manus avg 100:1 input:output; cached input is ~10× cheaper). Three rules: (1) **byte-stable prompt prefix** — never put a second-precision timestamp/changing ID near the front (one token change invalidates everything after it, autoregressively); (2) **append-only context** — never edit prior actions/observations; enforce **deterministic JSON key ordering** (many languages don't guarantee it, silently breaking cache); (3) explicit cache breakpoints + route a session to the same worker.
- **Frontier evidence**: Battle-tested primary source (Manus rebuilt its framework 4×). Corroborated by Anthropic's prompt-caching guidance and the explicit "doesn't invalidate the cached prefix" design of the Tool Search Tool (F2).
- **AstralDeep gap**: AstralDeep "builds tool lists per chat" and injects dynamic per-chat context (memory injection, "Attachments on this turn" blocks, narrative scaffolding). Verify in `_call_llm`: is the system-prompt prefix byte-stable across turns, or does it interpolate timestamps/changing IDs near the front? Is context strictly append-only, or are earlier messages mutated/reordered on `load_chat` rehydration? Are tool schemas / component dicts serialized with deterministic key order? Given 100:1 economics, a non-stable prefix is a quantifiable cost/latency leak.
- **Priority**: High (verify-first; likely the cheapest large win)
- **How to implement in AstralDeep**: Audit the `_call_llm` prefix; move all volatile content (timestamps, per-turn IDs, "attachments on this turn") *after* a fixed system+tools prefix; enforce `json.dumps(..., sort_keys=True)` for every tool schema and serialized component; make context construction strictly append-only on rehydration. Pure refactor, no new lib.
- **Novelty 3 / Impact 5 / Effort S**

### F12. Sandboxed execution for generated/parser code — no-egress, resource-bounded, throwaway

- **Source**: Amazon — AgentCore Code Interpreter (`Sandbox`/`Public` modes) + Runtime per-session microVM isolation. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html ; https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html . Convergent: Manus per-task E2B Firecracker microVM (https://manus.im/blog/manus-sandbox).
- **What it is**: A managed containerized sandbox for agent-written code, network configured per interpreter as **`Sandbox` (no internet)** or `Public`, with per-session isolated state/filesystem and an execution role scoping access; AgentCore Runtime goes further — each *session* gets a dedicated microVM that is terminated and memory-sanitized on end (idle 15 min / max 8 h).
- **Frontier evidence**: GA (2025-10-13). Manus microVM GA. (Full microVM isolation is incompatible with AstralDeep's in-process/no-new-libs posture — the *transferable* part is the no-egress, resource-bounded, throwaway boundary.)
- **AstralDeep gap**: Both agentic creation AND attachment auto-parsing generate code at runtime that today executes **in the orchestrator's own Python process**, sandboxed only by the security gate + self-test + admin approval — there is no runtime memory/CPU/filesystem/network jail. AstralDeep's codegen rules say "stdlib + installed-only, no pip," but nothing *enforces* it at execution; the egress gate is applied at the HTTP-helper layer, not as a hard boundary around the whole generated process.
- **Priority**: High (strongest *actionable* security gap within constraints)
- **How to implement in AstralDeep**: Run generated/parser code in a child process via stdlib `subprocess` with `resource` rlimits (CPU/memory/file-size), a stripped environment, a working dir scoped to a temp path, and **no network namespace / blocked sockets** (a hard egress boundary, not a helper-layer gate). The `Sandbox`-vs-`Public` toggle maps onto AstralDeep's existing egress gate but enforced at the process boundary. stdlib only; hardens AstralDeep's most security-sensitive feature.
- **Novelty 3 / Impact 5 / Effort M**

### F13. Agent-as-principal + per-(agent,user) token vault + 3-legged on-behalf-of-user consent

- **Source**: Amazon — AgentCore Identity (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html, https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/understanding-agent-identities.html); Microsoft — Entra Agent ID (https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity).
- **What it is**: Each agent gets a first-class **workload identity** distinct from the user. Inbound auth: caller authenticates to the agent (IAM SigV4 or a `customJWTAuthorizer` with `discoveryUrl`/`allowedClients`/`allowedAudience`/`allowedScopes`). Outbound auth: the agent obtains tokens to call third-party APIs **on behalf of the user** via 2-legged (M2M) or **3-legged (`auth_flow="USER_FEDERATION"`, authorization-code + user consent)** OAuth, exposed as a decorator `@requires_access_token(provider, scopes, auth_flow, on_auth_url)`. Critically the **Token Vault keys every stored downstream token by {agent workload identity + user ID}**, so one user's tokens can never be accessed when processing another user's request. Entra's parallel: a blueprint→instance governance split, attended-OBO vs unattended-app-only modes, audience-scoped downstream tokens, a tenant-wide agent inventory.
- **Frontier evidence**: AgentCore Identity GA (2025-10-13); Entra Agent ID core identity + OBO GA-grade (Build 2025, updated 2026-05-15).
- **AstralDeep gap**: This is the direct, higher-fidelity counterpart to AstralDeep's Keycloak OIDC + RFC 8693 delegation, and complementary. AstralDeep attenuates the *user's* token; it lacks (a) a distinct **agent identity** (the `act`/`may_act` actor in RFC 8693 terms) for cleaner per-agent attribution/scoping; (b) a **vault keyed by {agent + user}** physically partitioning third-party credentials per (agent,user); (c) a **3LO user-consent on-behalf-of primitive** for *external* APIs (AstralDeep's delegation handles its own resources). The Entra patterns (blueprint→instance governance, attended-vs-unattended modes, audience-scoped tokens) are mostly already expressible because AstralDeep owns the token-exchange machinery.
- **Priority**: High
- **How to implement in AstralDeep**: Promote each agent (especially runtime-created ones) to a distinct Keycloak service-account client (per-agent revocation + audit attribution); store external-API tokens keyed by `(agent_id, user_id)` in an idempotent-migrated table so cross-(agent,user) access is structurally impossible; add a reusable "agent needs external consent → emit a consent card → cache token until expiry" flow over the existing OIDC plumbing; use the RFC 8693 `audience`/`resource` parameter to scope downstream tokens to the service, not the tool URL; formalize scheduled/background jobs as unattended (app-only).
- **Novelty 4 / Impact 4 / Effort L**

### F14. Declarative agent manifest — define an agent as validated JSON (no arbitrary code)

- **Source**: Microsoft — M365 Declarative Agent Manifest (schema v1.7). https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.7 ; "agents are apps": https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/agents-are-apps
- **What it is**: A versioned JSON document fully defining an agent as data: required `version`/`name`(≤100)/`description`(≤1000)/`instructions`(≤8000); optional `capabilities` (enum: WebSearch, OneDriveAndSharePoint, GraphConnectors, CodeInterpreter, Dataverse, …, each scoped as data), `conversation_starters`(≤12), and `actions` (array of `{id:<GUID>, file:<OpenAPI-backed plugin manifest>}`). The LLM specializes from the manifest at runtime — there is no compiled agent logic.
- **Frontier evidence**: GA (schema versioned 1.0→1.7). AG2's CaptainAgent adds the adjacent "retrieve an existing agent BEFORE generating a new one" decision (https://docs.ag2.ai/latest/docs/user-guide/reference-agents/captainagent/).
- **AstralDeep gap**: AstralDeep's agentic creation *generates Python code* then sandboxes/self-tests/admin-approves it. The declarative-manifest pattern is the alternative: a new agent is a **validated JSON document the orchestrator interprets** — no arbitrary code, so the entire codegen security gate is sidestepped for the (large) class of agents that are just instructions + scoped capabilities + tool/action references. The bounded validation contract (8k instructions, ≤12 starters, ≤1-of-each-capability, GUID-keyed actions) is directly copyable. Relatedly, AstralDeep may always *generate* rather than first *searching* its 10-agent catalog for a match.
- **Priority**: High
- **How to implement in AstralDeep**: Add a **manifest-first creation path**: when a gap is fillable by composing existing tools + instructions + scoped capabilities, produce a validated JSON manifest (bounded fields) that the orchestrator interprets at runtime, reserving codegen only for genuinely novel tools. Add a "search existing agents/tools before generating" step (CaptainAgent's retrieve-or-generate). Reduces the attack surface and the approval burden of the headline feature.
- **Novelty 4 / Impact 4 / Effort M**

### F15. Model-chooses-component-per-tool-call + streaming partial UI (Vercel generative UI)

- **Source**: Vercel — AI SDK generative UI. `streamUI`/RSC: https://vercel.com/blog/ai-sdk-3-generative-ui ; current production path (typed tool parts): https://ai-sdk.dev/docs/ai-sdk-rsc/migrating-to-ui , https://vercel.com/blog/ai-sdk-5 ; `streamObject`/`useObject`: https://ai-sdk.dev/docs/ai-sdk-ui/object-generation
- **What it is**: Three related mechanics. (1) `streamUI`: each tool maps 1:1 to a component; **calling the tool IS the choice of component**, and `yield <Spinner/>` … `return <Final/>` is the streaming-partial-UI primitive. (2) The current GA successor (AI SDK UI): server tools return *data*; the client switches on typed message parts (`tool-{name}`) with per-tool lifecycle states `input-streaming → input-available → output-available → output-error` for progressive loading. (3) `streamObject`/`useObject`: stream a single structured object against a schema, rendering ever-deeper partials (or `elementStream` appending fully-validated rows one at a time).
- **Frontier evidence**: RSC `streamUI` officially de-emphasized ("experimental; use AI SDK UI for production"); typed-tool-parts + object streaming are GA (AI SDK 5, Jul 2025; AI SDK 6 GA Dec 2025). Perplexity ships the same "system decides which typed widget by intent" inline (https://perplexity.ai/finance/UI — decision mechanism undisclosed).
- **AstralDeep gap**: Architecturally opposite to AstralDeep, which arranges *finished* primitives *after* tools complete; the model never selects "render the Weather widget" as part of the tool call, and components appear only once fully built (no `yield`-loading-then-`return`-final, no field-by-field streaming). Two concrete moves: (a) let an agent's tool declaratively bind to a target primitive ("this tool means this widget") so intent → component is explicit and immediate; (b) stream a partial component (skeleton → progressively filled) over `ui_upsert` rather than withholding until the tool fully completes.
- **Priority**: Medium
- **How to implement in AstralDeep**: Add an optional `renders: <primitive_type>` hint on a tool definition so the orchestrator can emit a loading skeleton + progressively-filled component keyed to that tool before the result lands, pushing partials over the existing `ui_upsert` (stable `component_id`); for list-producing tools, append validated rows incrementally. SDUI-native; no client rewrite (the upsert/morph anchors already exist).
- **Novelty 3 / Impact 4 / Effort M**

### F16. Inline pre-generation citation binding (Perplexity answer engine)

- **Source**: Perplexity — answer-engine citation pipeline (third-party reverse-engineering; flagged). https://ziptie.dev/blog/how-perplexity-ai-answers-work/ ; product: https://perplexity.ai/hub/blog/introducing-perplexity-deep-research
- **What it is**: Perplexity does not retrofit citations — its orchestration embeds citation markers + source metadata + ranked excerpts into the structured prompt *before* generation; the model synthesizes prose **bound to pre-assembled evidence**, attaching inline numbers as it tracks which document informed each claim. A fail-safe discards and re-retrieves rather than serving weak citations.
- **Frontier evidence**: GA (core product). Flag: the citation-binding *mechanism* is third-party reverse-engineering, not an official Perplexity engineering post; the *pattern* (inject sources with IDs, prompt the model to cite inline) is standard and well-attested.
- **AstralDeep gap**: AstralDeep's `_chat_narrative` renders markdown and agents emit components, but there is no mechanism binding spans of generated text to source IDs at prompt-assembly time. Provenance lives in audit events / `workspace_snapshot`, not inline in answer text. Injecting `[ref:id]` markers into the synthesis prompt and rendering them as provenance chips would attribute any claim to a `memory_item`, a specific tool result, or an uploaded attachment.
- **Priority**: Medium
- **How to implement in AstralDeep**: When assembling the synthesis prompt for answers grounded in tool results / memory / attachments, prepend a numbered source list and instruct the model to emit `[n]` markers; post-process markers into astralprims provenance chips/badges linking to the workspace component or attachment. Turns existing audit/provenance plumbing into user-visible inline citations. No new lib.
- **Novelty 3 / Impact 4 / Effort M**

### F17. In-conversation supervisor models as runtime output guardrails (+ layered input/output stack)

- **Source**: Sierra (https://sierra.ai/blog/confidence-in-every-conversation, https://sierra.ai/blog/constellation-of-models); Decagon (https://decagon.ai/resources/designing-layered-guardrails-for-reliable-ai-agents).
- **What it is**: Dedicated **supervisor models run in parallel with the primary agent during a live conversation** — each reviews each response *as generated*, verifies facts, enforces policy, and can redirect/revise before it reaches the user. Distinct roles: a threat-detection supervisor on user *input* (multi-turn poisoning, jailbreak, injection) and policy/harm auditors on *output*. Decagon publishes the same as a layered stack: a parallel bad-actor detector + a supervisor reviewing every message before send (revise-or-escalate on hallucination) + **Watchtower** always-on post-conversation QA on 100% of conversations.
- **Frontier evidence**: GA. Hype flag: Sierra's "90%→99% combined accuracy" is illustrative/marketing-grade (the primary blogs don't restate it); the *mechanism* (parallel review + revise-before-send) is solid and independently described by both vendors. Converges with Anthropic's classifier-scan-then-confirm injection defense (https://www.anthropic.com/research/prompt-injection-defenses) and Meta's LlamaFirewall AlignmentCheck on tool outputs (https://github.com/meta-llama/PurpleLlama/blob/main/LlamaFirewall/README.md).
- **AstralDeep gap**: AstralDeep has a creation-time security gate + per-user permission scopes but **no runtime guardrail/supervision on agent OUTPUTS during a live conversation** — no pre-send output review, no parallel adversarial-input detector at conversation time, no automated 100%-coverage QA. Once a created agent is approved+scoped, its conversational outputs are unsupervised. (Hash-chained audit ≈ the Watchtower *audit* layer, but it is a tamper-evident log, not an active revise/QA loop.) This is also the precise defense for AstralDeep's indirect-injection exposure via `fetch_page`/summarizer/attachment auto-parse — untrusted content currently flows in with no scan-then-confirm layer.
- **Priority**: High (highest-value, best-documented enterprise gap)
- **How to implement in AstralDeep**: Add a lightweight pre-send supervisor pass (a second `_call_llm` call, or a deterministic rule-set for PHI/policy) that reviews a draft response/component before delivery and can revise, block, or escalate (F18); add an input-scan pass on untrusted ingress (fetched pages, attachment parse output). Both fit the F5/F6 hook/filter pipeline. No new lib (re-uses `_call_llm` + the PHI gate).
- **Novelty 4 / Impact 5 / Effort M**

### F18. Trigger-based escalation policy + warm (context-preserving) human handoff

- **Source**: Decagon — AI escalation policy. https://decagon.ai/glossary/what-is-an-ai-escalation-policy ; engine: https://decagon.ai/resources/the-ai-agent-engine
- **What it is**: Escalation-to-human formalized as a **policy object** with six triggers: confidence-threshold (most common), sentiment (sustained anger/safety), explicit user request (honored unconditionally), policy-based (legal/fraud/medical → human unconditionally), repeat-contact in a window, and loop detection (same intent cycled N times). The handoff is a **warm transfer** — summary + user data + resolution attempts delivered to the human *before* they engage (vs a cold queue), with routing to the right team.
- **Frontier evidence**: GA. Flag: the glossary page is partly SEO; the trigger taxonomy + warm-transfer payload are implementation-grade; routing internals undisclosed. Devin's confidence-gated autonomy (🟢/🟡/🔴 proceed-vs-ask) is the adjacent autonomy-gating pattern (https://cognition.ai/blog/devin-2-1).
- **AstralDeep gap**: AstralDeep has **no escalation-to-human pattern** — no confidence/sentiment/loop-detection triggers, no warm-transfer payload, no routing. For a system that auto-creates agents and runs them live, the absence of a "give up / hand to a person with full context" path is a notable safety/UX gap — acute for regulated topics (Decagon routes legal/medical/fraud to humans unconditionally; directly relevant to AstralDeep's medical agent + PHI posture).
- **Priority**: High
- **How to implement in AstralDeep**: Define an escalation policy evaluated each turn (loop-detection over repeated intents/tools, a low-confidence signal from the model, explicit-request keyword, and an unconditional policy list incl. medical/PHI); on trigger, render an astralprims "handed to a person" surface carrying a generated summary + transcript + attempts, and notify via the existing job/notification path. Confidence-gates also govern unattended-vs-admin approval for auto-created/auto-parser agents (Devin's pattern). No new lib.
- **Novelty 4 / Impact 4 / Effort M**

### F19. Safety shields as a first-class API — typed verdict, symmetric input/tool-output/output screening

- **Source**: Meta — Llama Stack Safety / Shields. https://github.com/ogx-ai/ogx/blob/v0.2.11/docs/source/building_applications/safety.md ; LlamaFirewall (role-routed scanner pipeline): https://github.com/meta-llama/PurpleLlama/blob/main/LlamaFirewall/README.md
- **What it is**: Safety is its own API with a Shield as a registerable resource: `run_shield(shield_id, messages)` returns a structured **`violation`** verdict (typed pass/deny + a user message), NOT a free-text completion. Shields attach **declaratively** via `AgentConfig.input_shields`/`output_shields` and screen at **three touchpoints**: input before inference, **tool-input before each tool execution**, and final output. LlamaFirewall generalizes this to a pipeline routed by `ScannerType` + `Role` across loop positions (input scan → reasoning/tool-output auditor → generated-code scan). Llama Guard 4 adds category **S14 "Code Interpreter Abuse"** — classify a tool/code action *before it runs*.
- **Frontier evidence**: Llama Stack Safety GA at 0.2.x (note: the project was renamed to "OGX" 2026-04-28 and the dependency is unstable/mid-migration — adopt the *pattern*, not the lib). LlamaFirewall released 2025-04-29 (AlignmentCheck experimental + needs an external API key). Caveat from Red Hat (2026-05): Llama Guard mis-fires on the Privacy category and needs tuning.
- **AstralDeep gap**: Closest external analog to the PHI gate, instructive both ways. What it does that AstralDeep's gate may not: (1) a **typed verdict** (auditable pass/deny + user message) rather than an inline gate function; (2) **symmetric input AND output shields PLUS a per-tool-input shield** — AstralDeep likely screens at fixed points, but this screens user input, *every tool call's arguments*, and final output (catches PHI a tool *produces* or that is injected via tool args — relevant to web_research/summarizer); (3) declarative attachment. Where AstralDeep is **ahead**: its gate is deterministic/fail-closed (presidio/spacy) vs an 8B model with documented false positives — keep that.
- **Priority**: Medium
- **How to implement in AstralDeep**: Refactor the PHI gate to a `Shield` shape returning a typed verdict, and attach it declaratively at three points (input, each tool-call's arguments, final output) via the F5/F6 pipeline — adding the per-tool-argument screen catches the indirect-injection/PHI-in-tool-output vectors AstralDeep is exposed to. Keep the deterministic engine. No new lib.
- **Novelty 3 / Impact 4 / Effort M**

### F20. Recitation (todo.md) + keep-errors-in-context — cheap attention/adaptation fixes

- **Source**: Manus — "Context Engineering for AI Agents." https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- **What it is**: Two distinct, cheap, no-architecture-change lessons. (a) **Recitation**: Manus tasks avg ~50 tool calls and the model drifts; the agent maintains a `todo.md` it continuously rewrites and checks off, **reciting objectives into the *end* of context each step** to push the global plan into recent attention (fights lost-in-the-middle). (b) **Keep the wrong stuff in**: do NOT scrub failed actions/errors/stack traces — seeing a failed action *and its error* shifts the model's prior away from repeating it ("erasing failure removes the evidence the model needs to adapt").
- **Frontier evidence**: Primary battle-tested source. Mirrors Perplexity Deep Research's self-revising plan artifact (https://perplexity.ai/hub/blog/introducing-perplexity-deep-research) and the Magentic Task Ledger (F9).
- **AstralDeep gap**: (a) AstralDeep "calls tools in a loop" with no described persistent self-rewritten goal artifact — over long agentic-creation/multi-step turns the user's objective sits at the *start* of a growing context (the lost-in-the-middle failure). No equivalent exists; cheap to add. (b) AstralDeep's narrative/designer layer (`_chat_narrative`, retirement Alerts, fallback paths) is built to present *clean* output — verify that when a tool call fails inside the loop, the **raw failure + error detail remains in the model's context for the next step** rather than being scrubbed before the model sees it. Hiding failures (even while showing a tidy Alert to the user) removes exactly the evidence that prevents repeats.
- **Priority**: Medium (both are small, high-leverage)
- **How to implement in AstralDeep**: (a) For multi-step turns, maintain a `todo` list the orchestrator re-appends to the *end* of context each step (complements the Magentic ledger). (b) Audit the loop so the model sees raw tool failures (separately from the user-facing Alert); never replace an in-loop error with a sanitized summary before the next model call. Pure context-assembly changes; no new lib.
- **Novelty 3 / Impact 4 / Effort S**

### F21. Workspace checkpoints + bidirectional rollback (incl. opt-in state) and Plan→Build gate

- **Source**: Replit — Checkpoints & Rollbacks (https://docs.replit.com/core-concepts/agent/checkpoints-and-rollbacks), snapshot engine (https://replit.com/blog/inside-replits-snapshot-engine), Plan Mode (https://docs.replit.com/replitai/plan-mode); Cognition — Devin Interactive Planning (https://docs.devin.ai/work-with-devin/interactive-planning). Anthropic's enforced Plan Mode + checkpoint/rewind are the adjacent primitives (https://code.claude.com/docs/en/permission-modes, https://code.claude.com/docs/en/checkpointing).
- **What it is**: Two patterns. (a) **Checkpoint + bidirectional rollback**: a snapshot at milestone "doneness" capturing files/config, **the AI conversation context + agent memory**, and (opt-in, OFF by default) state; rollback restores the whole environment and is bidirectional (roll forward again). (b) **Plan→Build gate**: a read-only plan mode emits an ordered dependency-aware task list (with the files it will touch and code citations that deep-link), gated by human review/edit before any code is written; "the plan is a starting point, not a contract" (dynamic re-planning). Anthropic makes Plan Mode an *enforced capability boundary* (the agent mechanically cannot mutate state until the plan is approved).
- **Frontier evidence**: Replit checkpoints/Plan Mode GA; opt-in DB rollback BETA at announcement (defaults OFF — a strong safety precedent). Devin Interactive Planning GA (2025-04). Hype flag: "time travel / vibe code" promotional; the Neon-branch/Alembic specifics circulating online are not in official sources.
- **AstralDeep gap**: AstralDeep has a per-turn `workspace_snapshot` + a **read-only** timeline ("mutations refused while viewing history") — SDUI component state, *not* a restorable whole-environment checkpoint, and **no user-facing rollback**. And agentic creation jumps gap-detection → auto-create → generate_code → self-test → approve/refine/discard with **no user-inspectable plan artifact gating the build** (no "here are the files I'll touch / scopes I'll need / self-test I'll run" *before* code generation). Two transferable moves: snapshot the *conversation/agent-memory context* alongside the workspace so rollback restores "what the agent knew"; surface a first-class editable plan (with the consent/scope/self-test it implies) before building, and consider making it an *enforced* read-only boundary (Anthropic) rather than narration.
- **Priority**: Medium
- **How to implement in AstralDeep**: (a) Extend `workspace_snapshot` to capture the conversation/memory context per turn and add a guarded `restore` that re-hydrates workspace + context (bidirectional), defaulting any state mutation OFF given the PHI/audit posture. (b) Before codegen, emit a plan card (files/tools/scopes/self-test) for admin review/edit; optionally enforce a read-only mode until approved. Idempotent migration; re-uses the draft lifecycle. No new lib.
- **Novelty 3 / Impact 4 / Effort L**

### F22. Composable, externally-cancellable termination conditions + deterministic-vs-LLM routing edges

- **Source**: Microsoft AutoGen — Termination (https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html), SelectorGroupChat (https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html); AG2 — `OnContextCondition` vs `OnCondition` (https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/orchestration/group-chat/patterns/). Vercel's `stopWhen` is the same idea (https://ai-sdk.dev/docs/agents/loop-control).
- **What it is**: (a) Loop-stopping as **first-class stateful objects** fed only the *delta* of new messages, composing with `|`/`&`: `MaxMessageTermination`, `TextMentionTermination`, `TokenUsageTermination` (budget cap), `TimeoutTermination` (wall-clock), and crucially **`ExternalTermination`** (toggled from outside the run — e.g. a UI Stop button). (b) AG2's two handoff-edge kinds: **`OnContextCondition`** fires on a boolean over shared context (**zero LLM cost, deterministic, auditable**); **`OnCondition`** is LLM-judged — route most dispatch on cheap predictable conditions, reserve LLM speaker-selection for genuine ambiguity. AutoGen's SelectorGroupChat adds a `candidate_func` to narrow the speaker pool first (maps onto scopes).
- **Frontier evidence**: Stable. Vercel `stopWhen` GA (composable `stepCountIs`/`hasToolCall`/custom). Bedrock's SUPERVISOR vs SUPERVISOR_ROUTER fast-path is the same "skip full planning for unambiguous single-agent requests" idea (https://docs.aws.amazon.com/bedrock/latest/userguide/create-multi-agent-collaboration.html).
- **AstralDeep gap**: Any multi-step loop AstralDeep adopts (F9/F10) needs principled stopping it currently lacks as reusable objects: **`ExternalTermination` driven from the WebSocket** (cancel a running agent loop mid-flight), a per-turn `TokenUsageTermination`, the **delta-fed** contract (don't re-scan history each step). And AstralDeep routes *everything* through LLM reasoning — the **deterministic boolean edge** (route on cheap auditable conditions, LLM only for ambiguity) is a cost/latency/auditability win aligned with its hash-chained-audit ethos, plus a cheap-path classifier (Bedrock router) that skips full planning for unambiguous single-agent requests.
- **Priority**: Medium
- **How to implement in AstralDeep**: Implement termination as small composable predicates (`max_steps`, token-budget, wall-clock, external-cancel flag set by a WS `stop` event) fed the message delta; add a deterministic routing pre-check (boolean context conditions / a fast single-agent classifier) before invoking the LLM speaker-selector, with a `candidate_func` that filters by the user's scopes. Pure Python; no new lib.
- **Novelty 3 / Impact 4 / Effort M**

### F23. Atom-decomposition + between-step state assertions (Nova Act reliability discipline)

- **Source**: Amazon — Nova Act. https://labs.amazon.science/blog/nova-act ; GA: https://aws.amazon.com/blogs/aws/build-reliable-ai-agents-for-ui-workflow-automation-with-amazon-nova-act-now-generally-available/
- **What it is**: Reliability philosophy: NOT one giant goal — decompose into many small `act()` calls each scoped to a narrow sub-task, stitched with deterministic Python; keep each call small, lower `max_steps` so failures surface early. Between calls, interleave Python to **assert on state** (`act_get("Am I logged in?", schema=BOOL)` → branch) and pass extracted structured data forward. Explicit anti-pattern: one "do the whole task" instruction.
- **Frontier evidence**: GA (2025-12-02). Hype flag: "90%+ reliability" is vendor-internal on hand-picked workflows; Nova Act loses element-grounding benchmarks (GroundUI Web) to Claude/OpenAI and WebVoyager is conspicuously absent — so treat the *discipline*, not the numbers, as the value.
- **AstralDeep gap**: Architecture-agnostic, zero-new-lib lesson for `_call_llm`, agentic-creation codegen prompts, and multi-tool sequences: a single large "figure it out" instruction is the failure mode; fix = decompose to smallest reliably-completable units, put deterministic Python between units (don't make the LLM carry control flow), and **assert on state between steps** (a structured "did step N succeed?" check) + a `max_steps`-style hard bound. AstralDeep's bounded `ui_designer` loop and 031 auto-parser self-test partially embody this — the gap is whether specialist multi-tool sequences and codegen prompts apply it *uniformly* vs one big prompt.
- **Priority**: Medium
- **How to implement in AstralDeep**: In codegen/agent prompts, require explicit step decomposition + a typed success assertion between steps + a hard step bound; in orchestrator multi-tool sequences, insert deterministic checks between tool calls (re-using the Magentic Progress Ledger's `is_progress_being_made` is one form). Prompt/control-flow discipline; no new lib.
- **Novelty 2 / Impact 3 / Effort S**

### F24. Reusable procedure objects: Skills / Playbooks / tunable-determinism AOPs

- **Source**: Anthropic — Agent Skills (https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills, spec https://agentskills.io/specification); Cognition — Devin Playbooks/Skills (https://docs.devin.ai/product-guides/creating-playbooks, https://docs.devin.ai/product-guides/skills); Decagon — AOPs (https://decagon.ai/product/aop); Sierra — tunable-flexibility skill modules (https://sierra.ai/product/develop-your-agent).
- **What it is**: A spectrum of "capability as a reusable, structured, model-triggered object" lighter than a full agent. **Agent Skills** = a `SKILL.md` folder loaded by **progressive disclosure** (Level 1 = name+description only, ~100 tokens, so you can install many nearly free; Level 2 = full body only when the description matches; Level 3 = bundled scripts/resources loaded/executed only when referenced, script *source* never enters context). **Devin Playbooks** = versioned Markdown procedure templates with structured sections — Procedure (MECE, imperative), Specifications (postconditions), **Forbidden Actions**, **Required from User**. **Decagon AOPs / Sierra skills** = NL-authored business logic that "compiles to code," with **per-step tunable determinism** (some steps deterministic, others LLM-reasoned) and full decision-trace visibility.
- **Frontier evidence**: Agent Skills GA across surfaces (Oct 2025), open standard (Dec 2025) — but on the Messages API gated behind 3 betas + a no-network/no-pip sandbox. Devin Playbooks/Skills GA. Decagon "compiles to code" mechanism + GA date undisclosed (marketing-dense) — concept real, internals opaque.
- **AstralDeep gap**: AstralDeep's agentic creation produces *agents/tools* (heavy, gated); its closest construct to a procedure is an auto-created agent. It lacks: (1) a **metadata-first progressive-disclosure** capability (tell the model a capability *exists and when to use it* for ~100 tokens; pay the full cost only on a match — the inverse of injecting full agent prompts/MCP schemas up front), with lazy reference-triggered file loads and script-output-only execution; (2) a **structured procedure object** (Procedure / Specifications / **Forbidden Actions** / **Required from User** — the latter two map directly onto AstralDeep's scope/consent + PHI gates) with explicit human-attach vs auto-discover and versioning; (3) **per-step tunable determinism** within one agent. The published Skill frontmatter is also the *interop* format to make AstralDeep capabilities portable.
- **Priority**: High
- **How to implement in AstralDeep**: Add a Skills-style capability registry: each capability is a folder with metadata (name+description, ~loaded always) + a body (loaded on description match) + optional scripts run in the F12 sandbox (output only). Adopt the Playbook section schema (incl. Forbidden Actions / Required-from-User wired to scopes/consent) for replayable procedures — a natural fit for AstralDeep's 031 auto-continue replay machinery. Re-use the agentskills.io frontmatter for portability. No new lib.
- **Novelty 4 / Impact 4 / Effort M**

### F25. Span-tree observability + agent evaluators + repeated-run (pass^k) reliability testing

- **Source**: Microsoft Foundry — tracing + agent evaluators + continuous eval (https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/tracing, https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators); Sierra — τ-bench / pass^k (https://sierra.ai/blog/benchmarking-ai-agents, https://github.com/sierra-research/tau2-bench); Amazon — AgentCore Observability (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-telemetry.html). All follow the OTel `invoke_agent → chat → execute_tool` span model.
- **What it is**: Three convergent pieces. (a) **Span-tree tracing**: a navigable parent/child tree of every LLM call / tool invocation / agent decision per request (span names `invoke_agent`/`execute_tool`/`agent_to_agent_interaction`, token-usage + duration attributes), with **two-tier content gating** (metadata always; sensitive prompts/args opt-in). (b) **Agent evaluators** ("unit tests for agents," Pass/Fail + reasoning): Task Completion, Intent Resolution, Tool Call Accuracy, Tool Selection, Tool Input Accuracy — runnable continuously against live traces with scores joined to the trace. (c) **pass^k**: probability of solving the *same* task across k repeated trials — exposes that good-on-average agents collapse on repetition (GPT-4o ~50% pass^1 → ~25% pass^8 on τ-retail).
- **Frontier evidence**: Foundry tracing + core evaluators + red-teaming GA (Ignite 2025); τ-bench GA/open-source (de-facto standard); AgentCore Observability GA (2025-10-13). (Full OTel SDK is a new dep — forbidden; emulate the *data model*.)
- **AstralDeep gap**: AstralDeep's hash-chained audit is strong on *integrity/forensics* but its `correlation_id` is a **flat per-action record, not a nested span tree** — it can't show "for this turn: parent-agent → child-specialist → MCP-tool → LLM-call timing tree." It also lacks **reusable LLM-judge evaluators** and, critically, a **policy-aware repeated-run reliability harness**: AstralDeep self-tests a created agent *once*, but the pass^k insight is that single-shot success ≠ reliable. Where AstralDeep is **ahead**: tamper-evident integrity (CloudWatch/App-Insights trails aren't hash-chained).
- **Priority**: Medium
- **How to implement in AstralDeep**: (a) Layer span nesting (`parent_span_id`) + durations onto the existing audit/correlation records to produce a per-turn tree, with two-tier content gating tied to the PHI gate. (b) Add LLM-judge evaluators (Tool Call Accuracy, Task Adherence) scoring each turn via `_call_llm`, attaching scores to the audit/trace record. (c) Promote the one-shot self-test to a **pass^k regression harness** that runs a created agent against a fixed task several times before approval, asserting consistent rule-following (e.g. "every prompt that should hit the PHI shield does"). Re-uses `_call_llm` + `VirtualWebSocket`; emulate the OTel data model without the SDK.
- **Novelty 3 / Impact 4 / Effort M**

## Sources

Anthropic / MCP:
- https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation
- https://modelcontextprotocol.io/specification/2025-11-25/client/sampling
- https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- https://modelcontextprotocol.io/specification/2025-11-25/changelog
- https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/
- https://modelcontextprotocol.io/community/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp
- https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/
- https://platform.claude.com/docs/en/build-with-claude/context-editing
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- https://agentskills.io/specification
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/permission-modes
- https://code.claude.com/docs/en/checkpointing
- https://code.claude.com/docs/en/agent-sdk/hooks
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/code-execution-with-mcp
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- https://www.anthropic.com/engineering/multi-agent-research-system
- https://www.anthropic.com/research/prompt-injection-defenses
- https://claude.com/blog/claude-for-chrome
- https://www.anthropic.com/product/claude-cowork

Microsoft:
- https://learn.microsoft.com/en-us/adaptive-cards/rendering-cards/host-config
- https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/container-layouts
- https://learn.microsoft.com/en-us/adaptive-cards/templating/
- https://learn.microsoft.com/en-us/adaptive-cards/templating/language
- https://learn.microsoft.com/en-us/adaptive-cards/authoring-cards/universal-action-model
- https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.7
- https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/agents-are-apps
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-generative-actions
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about
- https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/model-context-protocol-mcp-is-now-generally-available-in-microsoft-copilot-studio/
- https://arxiv.org/abs/2411.04468
- https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_magentic_one/_prompts.py
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/swarm.html
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html
- https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/orchestration/group-chat/patterns/
- https://docs.ag2.ai/latest/docs/user-guide/reference-agents/captainagent/
- https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters
- https://devblogs.microsoft.com/semantic-kernel/announcing-the-ga-release-of-filters-for-net-and-python-in-semantic-kernel/
- https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
- https://learn.microsoft.com/en-us/agent-framework/overview/
- https://learn.microsoft.com/en-us/agent-framework/user-guide/workflows/orchestrations/magentic
- https://learn.microsoft.com/en-us/agent-framework/workflows/
- https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/tracing
- https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators
- https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/connected-agents
- https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity
- https://techcommunity.microsoft.com/blog/microsoft-entra-blog/announcing-microsoft-entra-agent-id-secure-and-manage-your-ai-agents/3827392

Meta:
- https://github.com/ogx-ai/ogx/blob/v0.2.11/docs/source/building_applications/agent_execution_loop.md
- https://github.com/ogx-ai/ogx/blob/v0.2.11/docs/source/building_applications/safety.md
- https://github.com/ogx-ai/ogx/blob/v0.2.11/docs/source/building_applications/evals.md
- https://github.com/ogx-ai/ogx/blob/main/ARCHITECTURE.md
- https://github.com/meta-llama/PurpleLlama/blob/main/LlamaFirewall/README.md
- https://ai.meta.com/research/publications/llamafirewall-an-open-source-guardrail-system-for-building-secure-ai-agents/
- https://github.com/meta-llama/PurpleLlama/blob/main/Llama-Guard4/12B/MODEL_CARD.md
- https://github.com/pytorch/executorch/blob/main/examples/models/llama/README.md
- https://ai.meta.com/blog/meta-llama-quantized-lightweight-models/
- https://developers.redhat.com/articles/2026/05/04/guardrails-enterprise-safety-shields-llama-stack

Amazon:
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/understanding-agent-identities.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html
- https://aws.amazon.com/blogs/machine-learning/build-agents-to-learn-from-experiences-using-amazon-bedrock-agentcore-episodic-memory/
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-telemetry.html
- https://labs.amazon.science/blog/nova-act
- https://aws.amazon.com/blogs/aws/build-reliable-ai-agents-for-ui-workflow-automation-with-amazon-nova-act-now-generally-available/
- https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agent-collaboration.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/create-multi-agent-collaboration.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html

Vercel:
- https://vercel.com/blog/ai-sdk-3-generative-ui
- https://ai-sdk.dev/docs/ai-sdk-rsc/migrating-to-ui
- https://vercel.com/blog/ai-sdk-5
- https://vercel.com/blog/ai-sdk-6
- https://ai-sdk.dev/docs/ai-sdk-ui/object-generation
- https://ai-sdk.dev/docs/agents/loop-control
- https://ai-sdk.dev/docs/ai-sdk-ui/transport
- https://vercel.com/blog/v0-composite-model-family
- https://v0.app/docs
- https://v0.app/docs/design-mode

Startups:
- https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- https://manus.im/blog/introducing-wide-research
- https://manus.im/blog/manus-wide-research-solve-context-problem
- https://manus.im/blog/manus-sandbox
- https://ziptie.dev/blog/how-perplexity-ai-answers-work/
- https://perplexity.ai/hub/blog/introducing-perplexity-deep-research
- https://perplexity.ai/finance/UI
- https://docs.replit.com/core-concepts/agent/checkpoints-and-rollbacks
- https://replit.com/blog/inside-replits-snapshot-engine
- https://docs.replit.com/replitai/plan-mode
- https://replit.com/blog/introducing-agent-3-our-most-autonomous-agent-yet
- https://docs.devin.ai/work-with-devin/interactive-planning
- https://docs.devin.ai/product-guides/creating-playbooks
- https://docs.devin.ai/product-guides/skills
- https://docs.devin.ai/product-guides/knowledge
- https://cognition.ai/blog/devin-2
- https://cognition.ai/blog/devin-can-now-manage-devins
- https://cognition.ai/blog/devin-2-1
- https://sierra.ai/blog/confidence-in-every-conversation
- https://sierra.ai/blog/constellation-of-models
- https://sierra.ai/blog/benchmarking-ai-agents
- https://github.com/sierra-research/tau2-bench
- https://decagon.ai/resources/designing-layered-guardrails-for-reliable-ai-agents
- https://decagon.ai/product/aop
- https://decagon.ai/glossary/what-is-an-ai-escalation-policy
- https://decagon.ai/resources/the-ai-agent-engine
- https://lindy.ai/blog/no-code-ai-agent-builder
- https://genspark.ai/spark/enhancements-in-mixture-of-agents
