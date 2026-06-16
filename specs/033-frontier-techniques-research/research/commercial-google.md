# Google / DeepMind frontier — findings

> Research date: 2026-06-16 · Domain: Google / DeepMind product & platform frontier (mid-2026)
> Comparison target: **AstralBody** — server-driven-UI (SDUI) agentic platform (Python FastAPI + WebSocket orchestrator, ~10 MCP agents, `astralprims` fixed primitive palette rendered server-side, ROTE device adaptation, adaptive UI designer, agentic creation, persistent workspace, cross-session memory/"soul", Keycloak OIDC + RFC 8693 delegated tokens + hash-chained audit, PHI gate, fail-closed).
> Constraints honored in every "How to implement": **Python backend only · NO new third-party runtime libs · SDUI mandate (server defines/renders, escape-by-default) · idempotent startup migrations.**

## Executive summary

- **Generative UI is the headline gap.** Google's *Dynamic View* (Gemini 3 Pro, experimental, Nov 2025) codes a **bespoke HTML/CSS/JS interface per prompt**. AstralBody's adaptive designer only *arranges* a closed 31-primitive palette — it never invents new widgets. This is the single biggest novelty delta and maps directly onto AstralBody's SDUI thesis (a sandboxed "generative primitive" path).
- **Compute-placement device adaptation > layout-only adaptation.** Firebase AI Logic + Chrome built-in AI (Gemini Nano) route inference *to where the device can run it* (`PREFER_ON_DEVICE` / `ONLY_CLOUD`, offline, private). AstralBody's ROTE adapts only *presentation*. Extending ROTE with a `compute_capability` dimension + an optional browser-AI client lane is the highest-leverage device move and stays server-authoritative.
- **Enforced structured output is the highest-ROI, lowest-effort hardening.** Gemini's `responseSchema` constrained decoding *guarantees* valid JSON. AstralBody parses free text and spends UI-designer rounds on repair/retry. A single `response_format` parameter on the existing `_call_llm` client collapses that loop — Effort S, Impact 5.
- **Async, parallel, long-horizon agents are productized everywhere** (Mariner/Spark up to 15 concurrent tasks; Jules GA with 60 concurrent; Antigravity "Agent Manager"). AstralBody runs one synchronous turn at a time. Promoting its scheduled-jobs/`async_tasks` machinery into a user-launchable concurrent **task runner + manager surface** unlocks a whole class of UX.
- **Verification & trust patterns beat binary approval gates.** Antigravity emits inspectable **Artifacts** (plans, screenshots, recordings) with *non-blocking* comment-and-continue feedback; Vertex/ADK score agent **trajectories** (6 named tool-sequence metrics). AstralBody has a one-shot self-test + admin yes/no. Both are implementable on its existing audit/correlation-id trail.
- **Interop & agent identity are standardizing.** A2A reached **stable v1.0.0** (Linux Foundation, Mar 2026) with signed **Agent Cards** at `/.well-known/agent-card.json` and a JSON-RPC **Task** lifecycle; Cloud **Agent Identity** makes the agent a SPIFFE-based principal with cert-bound tokens. AstralBody has no cross-org interop and no per-agent cryptographic identity — both are implementable as pure-Python protocol shapes over its existing dispatch + RFC 8693 exchange.
- **Model-native tools change what a backend can do:** Search **grounding with span-anchored citations**, a **code-execution** sandbox (real charts/data over an uploaded CSV), **thinking budgets**, and **context caching/batch** are all GA Gemini-API capabilities AstralBody doesn't exploit through its OpenAI-compatible client.
- **Personalization is moving to consented cross-source context** (Personal Intelligence: Gmail/Photos/YouTube/Search, opt-in, off by default). AstralBody personalizes only from its own memory; it can add scope-gated "connected source" read tools through its existing 030 consent + egress paths.

---

## Findings

### F1. Generative UI — "Dynamic View" (bespoke interface coded per prompt)

- **Source**: Google Research, "Generative UI: A rich, custom, visual interactive user experience for any prompt" — https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/ ; The Keyword, "Gemini 3 brings upgraded smarts and new capabilities to the Gemini app" — https://blog.google/products/gemini/gemini-3-gemini-app/
- **What it is**: Gemini 3 Pro uses its agentic coding ability to **design and code a fully customized, interactive response (raw HTML/CSS/JS)** for every prompt, sent to the browser as a complete bespoke experience rather than a selection from fixed components. The interface is tailored to intent (Google's example: explaining the microbiome to a 5-year-old vs an adult yields different content *and* different features). Architecture = a server providing tools (image gen, web search) + detailed system instructions + a post-processor stage.
- **Frontier evidence**: "Gemini designs and codes a custom user interface in real-time, perfectly suited to your prompt." **Experimental / selective A/B** (Pro & Ultra, U.S.), launched **2025-11-18**. NOT GA.
- **AstralBody gap**: This is the central gap. The adaptive UI designer only *arranges* the ~31 fixed primitives into a layout tree; it cannot invent a brand-new widget, control, or micro-interaction per query the way Dynamic View codes a one-off interface. AstralBody is a closed palette; Google's surface is open-ended generated code.
- **Priority**: **Novelty**
- **How to implement**: Add a gated "generative primitive" path: let the LLM emit a **constrained HTML/CSS subset** (or a richer composite primitive-tree grammar with new container/interaction nodes) that the orchestrator renders through its existing escape-by-default sanitizer into a **sandboxed `<iframe srcdoc sandbox>`** (no script, or a tiny vetted JS shim), with interactive elements posting back as existing `ui_event` actions. Mirror Google's three-part pattern — tool-providing server, strict system instructions, **post-processor/validator** against an allow-list before render — preserving the SDUI mandate with no new runtime dependency.
- **Novelty 5 / Impact 5 / Effort L**

### F2. Visual Layout — magazine-style generative result with inline refinement modules

- **Source**: The Keyword, "Gemini 3 brings upgraded smarts and new capabilities to the Gemini app" — https://blog.google/products/gemini/gemini-3-gemini-app/
- **What it is**: A sibling generative experiment to Dynamic View where Gemini "generates an immersive, magazine-style view complete with photos and **modules that invite your input to further tailor the results**." It blends generated imagery, structured modules, and *in-result* interactive refinement controls (example: "plan a 3-day trip to Rome" → a visual itinerary you tweak in place).
- **Frontier evidence**: "one generated by the model the moment you prompt it"; modules "invite your input to further tailor the results." **Experimental**, rolling out alongside Dynamic View, **2025-11-18**. Not GA.
- **AstralBody gap**: AstralBody's Hero+Card+image primitives approximate the look, but it has no notion of interactive refinement modules embedded *in* the result that loop back to re-tailor the same view; the designer arranges, it doesn't compose an editorial layout with inline inputs.
- **Priority**: **UX**
- **How to implement**: Extend the adaptive designer with an "editorial layout" template plus a new **"refinement module" primitive** (labeled input/chip-set that emits a `component_action` re-running the source tool with adjusted params). Reuses the existing `component_action` re-execution path + dashboard primitives (Hero, Badge, KeyValue), staying within the fixed palette while adding loop-back tailoring.
- **Novelty 4 / Impact 4 / Effort M**

### F3. Enforced Structured Output (responseSchema / constrained decoding)

- **Source**: Gemini API — Structured Output, https://ai.google.dev/gemini-api/docs/structured-output
- **What it is**: The API constrains generation to a caller-supplied **JSON Schema** via `response_format` (`mimeType: application/json` + `schema`), enforced through **constrained generation** (not prompt-only). Supports `enum`, `format`, `properties`/`required`, `items`/`prefixItems`/`min`/`maxItems`, and `propertyOrdering`. Output is guaranteed-valid JSON of the declared shape; Gemini 3 can combine it with built-in tools.
- **Frontier evidence**: "The API enforces schema compliance through constrained generation." **GA** on Gemini 3.5 Flash, 2.5 Pro/Flash/Flash-Lite, 2.0 Flash; combining with tools is preview on Gemini 3. Docs updated 2026-06-05.
- **AstralBody gap**: AstralBody parses **free LLM text** to emit primitives and to drive the UI-designer layout-tree JSON, leaning on validators + format-retries + omission-repair to handle malformed/incomplete output. It has no enforced-schema path despite that being the single biggest reliability lever for an SDUI system.
- **Priority**: **Security** (reliability/safety of rendered output)
- **How to implement**: Most OpenAI-compatible providers expose `response_format={"type":"json_schema", "json_schema":{…}}` (or `json_object`). Pass a JSON Schema for the primitive-emission and layout-tree calls through the existing `_call_llm` client, collapsing the retry/repair loop, with graceful fallback to today's text-parse when a provider lacks the field. Request-parameter change only — **no new library**. Highest ROI / lowest effort here.
- **Novelty 4 / Impact 5 / Effort S**

### F4. Hybrid On-Device / Cloud inference routing (Firebase AI Logic)

- **Source**: Firebase AI Logic — Hybrid on-device inference, https://firebase.google.com/docs/ai-logic/hybrid-on-device-inference ; Android, https://developer.android.com/ai/hybrid
- **What it is**: A unified SDK that runs inference on a **local** model (Gemini Nano via AICore on Android; via the Prompt API in Chrome desktop) when available and falls back to **cloud** Gemini otherwise. The developer sets an explicit per-request routing policy: `PREFER_ON_DEVICE`, `PREFER_CLOUD`, `ONLY_ON_DEVICE`, `ONLY_CLOUD` (default cloud model `gemini-2.5-flash-lite`). Same calling code targets both compute locations, including structured output.
- **Frontier evidence**: Four named routing modes; "On-device inference is available from Chrome v139 and higher"; reconfirmed/expanded at **I/O 2026 (May 2026)**. Rationale: sensitive-data local processing + offline AI. **GA-ish** on the Android SDK path; web on-device portion gated to Chrome 139+ desktop.
- **AstralBody gap**: AstralBody places **100% of compute server-side** and adapts only *layout* via ROTE — no inference routing, no offline path, no "keep sensitive prompt local" option. This is the biggest device-adaptation gap: Google adapts *compute placement*, AstralBody adapts only *presentation*.
- **Priority**: **Device**
- **How to implement**: Extend ROTE's capability model from layout-only to a **`compute_capability` dimension** reported in `register_ui` (`has_builtin_ai`, `model_id`, `max_context`). The orchestrator then picks a routing policy per turn (trivial summarize/rewrite → emit a client directive to run the browser model and post the result back; complex/multi-tool → server LLM). **SDUI authority stays server-side** (server decides *what* runs and renders the result); only inference for tagged simple tasks is delegated, with automatic server fallback when the client reports no on-device model. New WS directive type + thin optional client hook — no new Python libs.
- **Novelty 5 / Impact 5 / Effort M**

### F5. Chrome Built-in AI APIs — Gemini Nano in the browser (Summarizer / Translator / Language Detector / Prompt)

- **Source**: Chrome for Developers, "Built-in AI updates (I/O 2025)" — https://developer.chrome.com/blog/ai-api-updates-io25 ; Built-in APIs index — https://developer.chrome.com/docs/ai/built-in-apis
- **What it is**: JavaScript Web Platform APIs that run **Gemini Nano inside Chrome** — summarization, translation, language detection, general prompting — with **zero server round-trip**, working **offline** after a one-time shared model download (downloaded once by the browser, near-zero per-site cost). The Prompt API supports a `responseConstraint` JSON Schema and multimodal (text+image) input.
- **Frontier evidence**: "Starting from Chrome 138, the Summarizer API, Language Detector API, and Translator API are available in **stable**, as is the Prompt API for use in Chrome Extensions" (2025-05-20). Hardware floor: ~22 GB free storage, >4 GB VRAM, 16 GB RAM. **GA/stable** for the three task APIs + extensions Prompt API.
- **AstralBody gap**: AstralBody's thin vanilla-JS client uses **no** browser-built-in AI; every summarize/translate/detect action makes a server WebSocket round-trip and fails offline. Google ships instant, offline, private versions of exactly these high-frequency UX tasks in the browser AstralBody already runs in.
- **Priority**: **Device**
- **How to implement**: Client feature-detects `'Summarizer' in self`, `'Translator' in self`, `LanguageDetector` at `register_ui` and reports to ROTE. For SDUI-tagged "instant" affordances the server renders (e.g., "Summarize this component" / "Translate"), the server emits a directive the client fulfills **locally** via the built-in API and echoes back into the workspace; if absent, the same directive falls through to the server LLM. Server keeps full SDUI authority + audit — it gains an optional zero-latency, offline-capable lane.
- **Novelty 4 / Impact 4 / Effort M**

### F6. Code Execution tool — Python sandbox → real charts/data on the fly

- **Source**: Gemini API — Code Execution, https://ai.google.dev/gemini-api/docs/code-execution
- **What it is**: Enabling the `code_execution` tool lets the model **author and run Python in a server-side sandbox**, iterate on results, and return `executable_code` + `code_execution_result` + inline matplotlib images. The sandbox ships Pandas/NumPy/SciPy/scikit-learn/Matplotlib/OpenPyXL/PyPDF2/python-docx, accepts CSV/text input, runs ≤30 s with up to 5 self-correcting retries.
- **Frontier evidence**: "generate and run Python code … learn iteratively … until it arrives at a final output," matplotlib output + file input, "no additional charge." **GA** (explicitly "not a preview offering").
- **AstralBody gap**: AstralBody **explicitly does NOT** use code-execution-as-a-tool; ml_services/connectors emit fixed widgets with sample/series data, and any real computation/chart must be pre-coded into an agent. It cannot let the LLM compute over an uploaded CSV and render a real chart on the fly.
- **Priority**: **Novelty**
- **How to implement**: Where the provider exposes a hosted code-execution tool through the OpenAI-compatible client, enable it and convert returned matplotlib images → astralprims image/chart primitive, code-result → table/text primitive. If staying self-hosted (sandbox concern, no new lib), gate a constrained internal "compute tool" through the **existing agentic-creation security path** so generated analysis code runs only inside the established gate + self-test, not freely.
- **Novelty 5 / Impact 5 / Effort M**

### F7. Grounding with Google Search — span-anchored citations + grounding metadata

- **Source**: Gemini API — Grounding with Google Search, https://ai.google.dev/gemini-api/docs/google-search
- **What it is**: The `google_search` tool fetches live web content and returns **structured grounding data**: `groundingMetadata` with `webSearchQueries`, `groundingChunks` (source `uri`+`title`), and `groundingSupports` linking text **`segment`s (`startIndex`/`endIndex`) → `groundingChunkIndices`** for inline citations, plus a `searchEntryPoint`. Reduces hallucination, answers beyond the cutoff, and combines with code execution / URL context / custom tools.
- **Frontier evidence**: "provides citations to build user trust by showing the sources"; structured `groundingSupports`/`groundingChunks` give "complete control over how you display sources." **GA** across Gemini 3.5 Flash, 3.1, 3 Preview, 2.5/2.0 Flash.
- **AstralBody gap**: AstralBody's `web_research` agent does keyless DuckDuckGo HTML parsing / optional Tavily and assembles "cited" briefs manually — no model-native grounded generation returning **text-span-to-source offsets**, so citations aren't structurally guaranteed or position-anchored.
- **Priority**: **Novelty**
- **How to implement**: For models exposing native search-grounding through the OpenAI-compatible surface, enable it and render `groundingChunks`/`groundingSupports` as an astralprims **citation primitive** (offset spans → inline footnote markers). Where staying provider-neutral, replicate the contract: have the model emit a **schema-enforced** `{answer, claims:[{text_span, source_idx}]}` (reusing F3) over `web_research` results so citations become first-class and position-anchored.
- **Novelty 4 / Impact 5 / Effort M**

### F8. Async parallel agents — Project Mariner / Gemini Spark (Agent Mode), up to ~15 concurrent

- **Source**: Google I/O 2025 keynote — https://blog.google/innovation-and-ai/technology/ai/io-2025-keynote/ ; Gemini Spark (consumer Agent Mode) — https://gemini.google/overview/agent/spark/
- **What it is**: A browser/web agent (introduced Dec 2024) that autonomously executes multi-step web tasks (research, bookings, purchases). At I/O 2025 it moved from a local Chrome-extension tab-takeover to **cloud-based VMs**, freeing the user's machine, and gained the ability to run **up to ~10 tasks in parallel**. The capabilities now ship as consumer **Gemini Spark** (Agent Mode rebrand): runs in a remote browser + code-execution sandbox, caps at **15 concurrent tasks**, and **asks for confirmation** before sending communications, modifying data, purchasing, or submitting forms.
- **Frontier evidence**: "a system of agents that could complete up to 10 tasks at a time" (I/O May 2025); standalone Mariner retired **2026-05-04** with capabilities folded into Gemini Agent/Spark; Spark 15-concurrent cap + confirmation gates documented. GA-adjacent for Google AI Ultra (US).
- **AstralBody gap**: AstralBody runs **one synchronous chat turn at a time**; no concept of N concurrent long-horizon background tasks each owning an isolated execution context that the user can fire-and-forget and check back on.
- **Priority**: **Novelty**
- **How to implement**: Promote the existing scheduled-jobs / `async_tasks` machinery into user-launchable **"background task" objects**, each with its own `VirtualWebSocket` + `job_run` row; render a live **"tasks tray"** SDUI surface (Table/Badge) that fans out status over the existing per-socket WS, capping concurrency (N≈10) with a worker pool — reuse the in-process self-test executor as the runner.
- **Novelty 5 / Impact 5 / Effort M**

### F9. Computer Use model + Interactions API (browser as a tool, with a safety-decision gate)

- **Source**: Gemini API — Computer Use, https://ai.google.dev/gemini-api/docs/interactions/computer-use ; DeepMind, "Gemini 2.5 Computer Use model" — https://blog.google/innovation-and-ai/models-and-research/google-deepmind/gemini-computer-use-model/
- **What it is**: A productized model (`gemini-2.5-computer-use-preview-10-2025`, also `gemini-3-flash-preview`) that drives a real browser via a **screenshot-action loop**: client sends goal + screenshot, model returns a `function_call` UI action (`click_at`, `type_text_at`, `scroll_document`, `navigate`, `key_combination`, `hover_at`, `drag_and_drop`, normalized 0–999 coords), client executes (Playwright) and returns a new screenshot, repeating until done. Exposed as the `computer_use` tool.
- **Frontier evidence**: Public **preview** since **2025-10-07**; built-in `safety_decision: require_confirmation` gate for purchases/CAPTCHAs/sensitive data; ~70%+ on Online-Mind2Web at ~225 s latency; ~$1.25/M input tokens.
- **AstralBody gap**: AstralBody agents act only through **curated MCP tools against known APIs**; there is no general "operate an arbitrary UI from screenshots" capability, so any site without an API/tool is unreachable.
- **Priority**: **Security** (the confirmation-gate pattern is the transferable part)
- **How to implement**: Add a `computer_use` agent whose tool wraps the orchestrator's existing **egress-gated HTTP** + a headless-browser screenshot loop fed by the configured LLM client; gate every high-stakes action through the existing **PHI-gate / confirmation** pattern (mirror `safety_decision`) and the **hash-chained audit**, and surface each step as a **workspace screenshot component** rather than acting invisibly. A headless-browser dependency would be the one carve-out to negotiate against the no-new-libs rule.
- **Novelty 5 / Impact 4 / Effort L**

### F10. Verifiable Artifacts — agent self-evidence + non-blocking comment-and-continue (Antigravity)

- **Source**: Google Developers Blog, "Build with Google Antigravity" — https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/ ; https://en.wikipedia.org/wiki/Google_Antigravity
- **What it is**: Antigravity (agent-first IDE, public preview Nov 2025) has agents emit **Artifacts — task lists, implementation plans, screenshots, browser recordings** — instead of raw tool logs, so a human verifies reasoning *at a glance*. Crucially, users **comment directly on an Artifact** (like commenting on a doc) and "the agent will incorporate your input **without stopping** its execution flow." A "Manager view" spawns/orchestrates/observes **multiple agents working asynchronously across workspaces**.
- **Frontier evidence**: "verifiable deliverables… rather than raw tool outputs, designed to build user trust"; non-blocking comment-on-artifact feedback (preview, Nov 2025); Manager = "control center for orchestrating multiple agents working in parallel."
- **AstralBody gap**: AstralBody's agentic creation produces a **binary self-test result + admin approve/refine/discard**; it does not produce rich human-inspectable **evidence artifacts** (step plan, before/after screenshots, walkthrough) for ongoing trust, and feedback is a stop-and-decide gate, not a live non-blocking annotation the running agent absorbs. There is also no "manager" surface to watch several parallel tasks at a glance.
- **Priority**: **Security** (trust/verification)
- **How to implement**: Extend the self-test/agentic-creation flow to emit a structured **verification-artifact set** as astralprims components (a Timeline of the plan, KeyValue of checks, captured outputs) persisted in the workspace and chained into audit; add a `component_action`-style **"comment on this step"** event that appends user feedback to the running task's context so it adapts mid-flight rather than halting. Pair with an **"Agent Manager" chrome surface** listing active background tasks (from F8's runner). Pure SDUI + existing audit/workspace — no new deps.
- **Novelty 5 / Impact 5 / Effort M**

### F11. Trajectory evaluation — scoring an agent's tool-call sequence (Vertex / ADK)

- **Source**: Google Cloud, "Introducing Agent Evaluation in Vertex AI Gen AI Evaluation Service" — https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service ; ADK eval criteria — https://adk.dev/evaluate/criteria/
- **What it is**: Google evaluates an agent's **reasoning path** — the ordered sequence of tool calls — not just the final answer, via six deterministic metrics: `trajectory_exact_match`, `trajectory_in_order_match`, `trajectory_any_order_match`, `trajectory_precision`, `trajectory_recall`, `trajectory_single_tool_use`. ADK surfaces the same as `tool_trajectory_avg_score` (EXACT / IN_ORDER / ANY_ORDER) averaged per invocation against a golden trajectory; runnable via `adk eval` / `AgentEvaluator.evaluate()` in pytest with `.evalset.json` files.
- **Frontier evidence**: Agent evaluation launched **public preview 2025-01-24**; the six metric names/definitions are verbatim from the official blog; ADK eval is **GA** (ADK Python 2.0). Latency + failure metrics auto-attach to every eval.
- **AstralBody gap**: AstralBody has **no formal agent-evaluation harness** beyond a one-shot self-test of new draft agents — it never scores an agent's *trajectory* against an expected golden path, so there is no regression signal for routing/tool-selection quality.
- **Priority**: **Novelty**
- **How to implement**: AstralBody already records ordered tool dispatches in its **hash-chained audit / per-correlation-id**; add a pure-Python evaluator that reads that trajectory and scores it against reference trajectories using the exact six set-comparison formulas, plus a ROUGE-1 response match. Store eval cases as JSON fixtures and wire a `pytest` runner so the existing self-test becomes a **scored, repeatable trajectory-eval gate**. No new libs.
- **Novelty 4 / Impact 5 / Effort M**

### F12. A2A Agent Cards + cross-agent Task delegation (stable v1.0.0)

- **Source**: A2A Protocol Specification (Linux Foundation) — https://a2a-protocol.org/v0.3.0/specification/ ; A2A-vs-MCP — https://a2a-protocol.org/latest/topics/a2a-and-mcp/ ; launch — https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- **What it is**: A2A's discovery layer is a **signed JSON Agent Card** an agent publishes at **`/.well-known/agent-card.json`** describing identity, `skills[]`, `url`, transports, `securitySchemes`, and `signatures[]` (JWS). Its collaboration layer is a stateful **Task** object (`submitted → working → input-required → completed/canceled/failed/rejected/auth-required`) exchanged between *opaque* agents via **JSON-RPC 2.0 over HTTPS**, with SSE streaming (`message/stream`) and webhook push for multi-hour work. Methods: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, `tasks/list`, `tasks/pushNotificationConfig/*`. Explicitly *complements* MCP ("A2A = agents partnering; MCP = agents using capabilities").
- **Frontier evidence**: Well-known path verified (renamed from `agent.json` in v0.3.0); **first stable v1.0.0 on 2026-03-12** (patch 1.0.1 2026-05-28); donated to the Linux Foundation 2025-06-23; **150+ orgs** by 2026-04-09; signed cards in schema.
- **AstralBody gap**: AstralBody auto-discovers agents **only locally**, has no Agent Card, no `/.well-known/` discovery endpoint, and no peer Task object — it cannot advertise or consume capabilities across an org boundary, and no external agent can delegate work to it (or vice versa).
- **Priority**: **Novelty**
- **How to implement**: Add a **pure-Python serializer** emitting each agent's existing MCP tool registry as an A2A-shaped Agent Card (tools → `skills[]`, Keycloak/OIDC → `securitySchemes`), served at `GET /.well-known/agent-card.json`; sign with the existing audit HMAC/JWS for `signatures[]`. Implement the **Task state machine + JSON-RPC method set** as a thin FastAPI router, mapping inbound `message/send` onto existing orchestrator dispatch and persisting Task rows alongside the jobs table; reuse WS/SSE for `message/stream` and scheduled-jobs for `pushNotificationConfig`. Protocol-shape only — **no SDK import**.
- **Novelty 5 / Impact 5 / Effort L**

### F13. Agent Identity — SPIFFE-based first-class principal with cert-bound tokens

- **Source**: Google Cloud IAM, "Agent Identity overview" — https://docs.cloud.google.com/iam/docs/agent-identity-overview ; platform govern view — https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview
- **What it is**: Google Cloud made the **agent a distinct IAM principal** with a cryptographic identity based on **SPIFFE** — each agent gets a `spiffe://` ID and appears in policy as `principal://…`. Unlike service accounts, agent identities aren't shared across workloads, can't be impersonated, and forbid long-lived keys; access tokens are **certificate-bound (mTLS, X.509)** to prevent token theft. Supports own-authority and **user-delegated 3-legged OAuth** to authenticate to MCP servers, resources, and other agents.
- **Frontier evidence**: **Preview** (Pre-GA); SPIFFE ID format + cert-bound-token/mTLS enforcement documented verbatim; integrates with IAM, Principal Access Boundary, VPC-SC; auditable trail mapped to authorization policy (Next '26, 2026-04-22).
- **AstralBody gap**: AstralBody authenticates **users** via Keycloak and issues RFC 8693 delegated tokens with attenuated per-user scopes, but **agents are not first-class cryptographic principals** — cross-agent calls can't prove which agent is acting, and there is no agent-scoped (vs user-scoped) authorization.
- **Priority**: **Security**
- **How to implement**: Mint a per-agent identity in pure Python by **extending the existing RFC 8693 exchange** to issue an agent-scoped JWT whose subject is a stable agent URI (mirroring the SPIFFE `principal://` shape) bound to a per-agent keypair; sign Agent Cards (F12) and A2A requests with that key and validate server-side. Reuses `python-jose`/`cryptography` already in the stack (**no new lib**) and lets the hash-chained audit record *which agent* acted, not just which user.
- **Novelty 4 / Impact 4 / Effort M**

### F14. Live API — bidirectional streaming multimodal session (barge-in, proactive/affective audio)

- **Source**: Gemini API — Live API overview, https://ai.google.dev/gemini-api/docs/live-api ; capabilities, https://ai.google.dev/gemini-api/docs/live-api/capabilities ; DeepMind native-audio — https://blog.google/innovation-and-ai/models-and-research/google-deepmind/gemini-2-5-native-audio/
- **What it is**: A stateful **bidirectional WebSocket** that streams continuous audio (PCM 16 kHz in / 24 kHz out), images (≤1 FPS JPEG), and text to Gemini and streams back audio + transcripts in real time — the engine behind Gemini Live / Project Astra. **Barge-in**: automatic VAD (tunable `startOfSpeechSensitivity`/`silenceDurationMs`) instantly cancels in-flight generation *and* pending tool calls so users interrupt mid-sentence (`interrupted` flag). **Proactive audio** lets the model decide *not* to respond to ambient/irrelevant speech; **affective dialog** (`enableAffectiveDialog`) adapts reply tone to the user's vocal expression.
- **Frontier evidence**: "real-time voice and vision interactions"; "Users can interrupt the model at any time… the ongoing generation is canceled and discarded"; proactive/affective behaviors gated behind `v1alpha` on Gemini 2.5 native audio. **Preview** (2025–2026).
- **AstralBody gap**: AstralBody's WebSocket carries **turn-based JSON chat + SDUI ops only** — no continuous audio/video ingest, no streaming output, no live-vision channel, and no way to cancel an in-flight generation or tool dispatch. A user cannot hold a spoken see-what-I-see conversation or interrupt a long answer.
- **Priority**: **UX**
- **How to implement**: Add a parallel **binary WebSocket subprotocol** on the existing `/ws` accepting chunked PCM/JPEG frames, forwarded to a streaming-capable LLM endpoint via the already-present client; emit incremental text as a new `chat_stream_delta` op and continue rendering primitives at turn boundaries. For barge-in, track the asyncio task per in-flight dispatch and `task.cancel()` on a new `chat_message`/`cancel`, sending an `interrupted` op. FastAPI/Starlette already support binary WS frames; `websockets` is already a dependency — **no new lib**.
- **Novelty 5 / Impact 5 / Effort M**

### F15. Personal Intelligence — consented cross-source personalization (Gmail/Photos/YouTube/Search)

- **Source**: The Keyword, "Personal Intelligence: Connecting Gemini to Google apps" — https://blog.google/innovation-and-ai/products/gemini-app/personal-intelligence/ ; foundation — https://blog.google/products-and-platforms/products/gemini/gemini-personalization/
- **What it is**: Connects Gmail, Photos, YouTube, and Search "in a single tap" so Gemini **reasons across the user's own data** for proactive, personalized answers (demo: combining road-trip photos + a license plate read from a picture + Gmail trim details to find minivan tire specs). Explicitly **opt-in and off by default**; Google does "not train directly on your Gmail inbox or Google Photos library."
- **Frontier evidence**: Connections "off by default"; users "decide exactly which apps to connect." **Beta, U.S. only, Pro/Ultra first** (2026-01-14); earlier Search-history version ran on experimental Gemini 2.0 Flash Thinking.
- **AstralBody gap**: AstralBody personalizes only from its **own** memory/past-chat signals (`memory_item`, `user_personalization`) — no consented connectors pulling live cross-source user data (mail/photos/history) into context, and no proactive synthesis across sources.
- **Priority**: **UX**
- **How to implement**: AstralBody already has the right primitives — the **030 consent path**, `agent_scopes`/`tool_overrides`, and the attachment/agent model. Add **opt-in "connected source" read tools** (off by default, per-source scope-gated, audited) that inject retrieved context into the turn the way "Attachments on this turn" already does, reusing the existing **fail-closed** posture and the egress-gated `shared.external_http` — no new runtime libs.
- **Novelty 4 / Impact 5 / Effort M**

### F16. Managed long-term Memory Bank — extract → consolidate → contradiction-resolve + embedding recall

- **Source**: Google Cloud, "Vertex AI Memory Bank in public preview" — https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-memory-bank-in-public-preview ; GA — https://cloud.google.com/blog/products/ai-machine-learning/new-enhanced-tool-governance-in-vertex-ai-agent-builder ; overview — https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview
- **What it is**: Agent Engine's managed memory: a Gemini model **asynchronously reads session history, extracts durable facts/preferences, and consolidates them against existing memories — explicitly resolving contradictions** (e.g., updating a changed preference). Memories are **scoped by a developer key (e.g., user ID)** and retrieved either as all-facts or via **embedding similarity search**. Integrated with ADK (`VertexAiMemoryBankService`) + Sessions.
- **Frontier evidence**: Public preview **2025-07-08**, **GA 2025-12-18**; method accepted to ACL 2025; pricing $0.25/1k stored, $0.50/1k retrieved. Background async extraction + **contradiction-resolving consolidation** is the load-bearing novelty; Next '26 added "Memory Profiles" (low-latency recall).
- **AstralBody gap**: AstralBody has cross-session memory + a "dreaming" consolidation sweep, but the frontier delta is the **managed extract→consolidate→contradiction-resolve loop with embedding-similarity retrieval**; if its memory is store/recall without active LLM reconciliation of conflicting facts, it accumulates stale/contradictory memories.
- **Priority**: **Novelty**
- **How to implement**: Add a pure-Python **consolidation pass** on a scheduled job: run the existing `_call_llm` over recent session events to extract candidate memory items, then a second pass to **merge/supersede conflicting** existing items (write-through to the memory table, keyed by per-user scope). For retrieval, compute embeddings via the existing OpenAI-compatible client and do **cosine top-k in Postgres** — no new runtime dependency.
- **Novelty 4 / Impact 4 / Effort M**

### F17. Thinking Budgets + Thought Summaries (reasoning-cost control)

- **Source**: Gemini API — Thinking, https://ai.google.dev/gemini-api/docs/thinking
- **What it is**: A `thinkingBudget` parameter caps reasoning tokens per request: `-1` dynamic, `0` off (Flash/Flash-Lite), or an explicit cap (2.5 Pro 128–32,768; 2.5 Flash 0–24,576). `includeThoughts: true` returns organized **thought summaries**; `thoughtsTokenCount` reports consumption. Gemini 3 returns encrypted `thoughtSignatures` required to preserve reasoning context across multi-turn function-calling.
- **Frontier evidence**: "thinkingBudget … guides the model on the specific number of thinking tokens"; summaries on free + paid tiers; thought signatures required with function-calling + thinking. **GA** on all 2.5 and 3 series.
- **AstralBody gap**: AstralBody has **no explicit reasoning-budget control** — every call (cheap routing vs agentic codegen vs UI design) uses the same uncontrolled reasoning, so it can't trade latency/cost on simple turns or buy more reasoning for hard ones, and surfaces no reasoning summary.
- **Priority**: **UX**
- **How to implement**: Add a **per-call-site reasoning knob** threaded through `_call_llm` (a `reasoning_effort`/`thinking_budget` arg mapped to the provider's field — OpenAI-compatible endpoints expose `reasoning_effort`): minimal for routing, high for agentic creation / UI design. Optionally pipe returned thought-summary text into an SDUI "reasoning" disclosure primitive. Request-shaping only — no new lib.
- **Novelty 4 / Impact 4 / Effort S**

### F18. Function-Calling modes (forced ANY / VALIDATED + `allowed_function_names`) for security-critical steps

- **Source**: Gemini API — Function Calling, https://ai.google.dev/gemini-api/docs/function-calling
- **What it is**: `function_calling_config.mode` controls tool behavior: `AUTO` (model decides), **`ANY`** (forced to always emit a schema-adherent call), **`VALIDATED`** (call-or-text with guaranteed schema adherence; default when tools + structured output combine), `NONE` (forbidden); **`allowed_function_names`** restricts the selectable set. Parallel calling returns multiple `id`'d calls; compositional calling chains outputs (native in Gemini 3 via internal thinking). Gemini 3 returns `thought_signature` to preserve reasoning across stateless calls.
- **Frontier evidence**: `ANY` "constrained to always predict a function call and ensures function schema adherence"; `VALIDATED` "ensures function schema adherence." **GA** for core function calling; multimodal responses + native MCP **preview** on Gemini 3.
- **AstralBody gap**: AstralBody injects tools into chat tool lists but its OpenAI-compatible path doesn't expose an equivalent hard **"force a call from this allow-list"** / schema-adherence guarantee, so gap-detection and the agentic-creation meta-tools (`create_capability`/`extend_agent`) lean on prompt steering rather than a constrained tool-choice contract.
- **Priority**: **Security**
- **How to implement**: Map MCP tool definitions to the existing client's `tools=[…]` + `tool_choice` ("required"/named) for **schema-validated args + forced selection** on security-critical steps (the meta-tools especially), and thread any returned reasoning/thought token back on subsequent turns. Same `_call_llm` client with `tools`/`tool_choice` params — no new SDK.
- **Novelty 3 / Impact 4 / Effort S**

### F19. AI-Studio "Build / Vibe Coding" — build-an-app/agent-from-a-prompt for everyone

- **Source**: The Keyword, "Introducing the new full-stack vibe coding experience in Google AI Studio" — https://blog.google/innovation-and-ai/technology/developers-tools/full-stack-vibe-coding-google-ai-studio/ ; docs — https://ai.google.dev/gemini-api/docs/aistudio-build-mode
- **What it is**: AI Studio **Build mode** turns a natural-language prompt into a real, runnable **full-stack app** (React/Angular/Next frontend + Node backend), auto-provisioning **Cloud Firestore + Firebase Auth** when it detects a database/login is needed. An agent ("Antigravity") manages the multi-file project; users refine via **Annotation Mode** (highlight UI → describe change), seed with "I'm Feeling Lucky"/AI Chips, fork Starter Apps, and one-click **deploy to Cloud Run** for a shareable URL. Framed for everyone, with agents "building while you do other things."
- **Frontier evidence**: Creates "production-ready applications" with auto-provisioned DB + auth; one-click Cloud Run deploy; downloadable as ZIP. Announced **2026-03-18**; presented as current functionality (GA in AI Studio).
- **AstralBody gap**: AstralBody's agentic creation (LLM codegen of new agents) is **admin-only** and produces backend MCP agents, not an end-user "describe an app/agent → get a usable thing" surface. Google exposes full creation to **every user**; AstralBody gates it behind admin approval.
- **Priority**: **UX**
- **How to implement**: Build an SDUI **"build-an-agent-from-a-prompt" surface** wrapping the EXISTING 027 lifecycle (create_draft → generate_code → self_test) for non-admins, but keep the security posture by routing the result through draft → VirtualWebSocket self-test → admin approval (or a **scoped per-user sandbox visibility**) rather than instant global go-live. Add an **annotation-mode equivalent**: let users highlight a rendered primitive and describe a change, feeding selection + instruction back through the UI designer / draft-refine path. New orchestration + chrome surfaces over existing flows — no new libs.
- **Novelty 5 / Impact 4 / Effort L**

### F20. ADK composition primitives — agent-as-tool + deterministic Sequential/Parallel/Loop agents

- **Source**: ADK — Function tools / AgentTool, https://adk.dev/tools-custom/function-tools/ ; Workflow agents, https://adk.dev/agents/workflow-agents/
- **What it is**: ADK provides composition beyond LLM routing: (1) **AgentTool** wraps an entire agent so another agent calls it as a tool and gets control *back* (vs full transfer to a sub-agent), with `skip_summarization` to pass output verbatim; and (2) **deterministic workflow agents** — `SequentialAgent` (ordered, state via `output_key`), `ParallelAgent` (concurrent isolated branches), `LoopAgent` (iterate to `max_iterations` or until a tool sets `escalate=True`) — that orchestrate sub-agents **without consulting an LLM**.
- **Frontier evidence**: ADK Python **GA (2.0)**, latest v2.2.0 (2026-06-04), Apache-2.0; workflow agents documented as deterministic; AgentTool's "control returns to caller" vs sub-agent full-transfer documented verbatim.
- **AstralBody gap**: AstralBody's orchestrator routes chat to specialists but exposes **no reusable deterministic composition primitives** — no agent-as-tool wrapper letting one specialist invoke another and resume, and no first-class sequential/parallel/loop orchestrators for multi-step pipelines with controlled iteration.
- **Priority**: **Novelty**
- **How to implement**: Implement three small pure-Python orchestrator helpers — a **sequential** runner threading a shared state dict between dispatches, a **parallel** runner using `asyncio.gather` over isolated contexts, and a **loop** runner with a max-iteration cap + `escalate`-style early exit — plus an **"agent-as-tool" adapter** registering another specialist's entrypoint into a caller's MCP tool list and returning control after one call. All over existing dispatch — no new libs.
- **Novelty 3 / Impact 4 / Effort M**

### F21. Android XR smart glasses — true heads-up, form-factor-adaptive modality

- **Source**: blog.google, "Android XR (I/O 2026)" — https://blog.google/products-and-platforms/platforms/android/android-xr-io-2026/ ; Android XR SDK Developer Preview 3 — https://developer.android.com/blog/posts/build-for-ai-glasses-with-android-xr-sdk-developer-preview-3
- **What it is**: Gemini on lightweight glasses that see/hear context and surface **minimal, glanceable** help — direction-aware turn-by-turn, "ask Gemini about anything you see," summarize missed messages, tone-matched real-time translation, even agentic actions ("prepare your coffee order on DoorDash while your phone stays in your pocket"). Two form factors: audio-only and display glasses with an optional **in-lens one-line display**.
- **Frontier evidence**: I/O 2025 live in-lens translation/navigation demo; audio glasses "launch **fall 2026**" (Gentle Monster, Warby Parker); developer path is the **Android XR SDK Developer Preview 3** (Dec 2025). Hardware imminent; SDK in Developer Preview.
- **AstralBody gap**: ROTE enumerates watch/TV/voice but has **no true wearable/glasses target** and no model of glanceable, hands-free, in-lens "one-line heads-up" UX — its watch/voice adaptation is layout reflow of the same server payload, not a genuinely different interaction modality.
- **Priority**: **Device**
- **How to implement**: Add a **`glasses`/`heads-up` ROTE capability profile** whose adapter aggressively reduces any server payload to a single primary line + one optional action and prefers the VOICE channel, registering a new render target via the documented `webrender.register_target` seam. No physical glasses needed to start — a **"heads-up" web profile** (extreme minimal layout, TTS-first) proves the form-factor-adaptive path within the SDUI mandate; full glasses delivery is L and beyond the current web-only client.
- **Novelty 5 / Impact 3 / Effort L**

### F22. Native MCP interoperability across model + framework layer

- **Source**: Gemini API — Function Calling (native MCP), https://ai.google.dev/gemini-api/docs/function-calling ; ADK MCP (both directions), https://adk.dev/mcp/ ; official Google MCP servers — https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services
- **What it is**: Google adopted MCP at two layers: the Gemini API / Gen AI SDK lets you pass an **MCP client session directly into the `tools` list** (auto tool-calling loop); and ADK acts as both MCP **client** (`MCPToolset`) and MCP **server** (wrap ADK tools to expose them to any MCP client). Google also shipped first-party MCP servers (BigQuery/GCE/GKE GA).
- **Frontier evidence**: Gemini API built-in MCP **experimental** (tools-only); ADK MCPToolset (consume + expose) **GA**; official Google MCP servers **2025-12-10** (BigQuery/Compute/GKE GA). Framing: MCP standardizes agent↔tool, A2A standardizes agent↔agent.
- **AstralBody gap**: AstralBody already uses an MCP-*like* internal protocol but it's **closed** — agents can't consume *external* MCP servers, and AstralBody doesn't expose its own tools as a **standards-compliant MCP server** that an outside Gemini/Claude agent could call. It is MCP-shaped but not MCP-interoperable.
- **Priority**: **Device** (interop reach)
- **How to implement**: Add a pure-Python **MCP server façade** (JSON-RPC over HTTP/SSE implementing `tools/list` + `tools/call`) re-exporting the existing tool registry through the current permission-override + delegated-token gates, plus a thin MCP **client** shim so a specialist can register an allow-listed external server's tools into its own registry. Both are protocol shapes over existing dispatch — no SDK, no new runtime dependency.
- **Novelty 3 / Impact 3 / Effort S**

### F23. On-screen visual highlighting over a live camera feed (Gemini Live "agent highlighting")

- **Source**: The Keyword, "Gemini Live updates (August 2025)" — https://blog.google/products/gemini/gemini-live-updates-august-2025/
- **What it is**: When the user shares their phone camera in Gemini Live, Gemini **draws visual indicators directly onto the live view** to point at real-world objects (highlight the matching sneakers, pinpoint the right tool), pairing spoken guidance with spatially-anchored on-screen markup — closing the loop between what the assistant sees and what it points you to.
- **Frontier evidence**: "visual guidance by highlighting things directly on your screen" when sharing the camera; rolled out **Pixel 10 (2025-08-28)**, then Android that week, iOS soon after. **GA / rolling out** in the consumer Gemini app.
- **AstralBody gap**: AstralBody has **no camera/vision input** and no **spatial overlay primitive** — it renders structured cards/tables, never annotations anchored to an image's coordinates.
- **Priority**: **Device**
- **How to implement**: Add an **`annotated_image` SDUI primitive** (image URL + list of normalized bbox/point overlays with labels) rendered as absolutely-positioned divs over the image in the thin client; have a vision-capable tool return bounding boxes for uploaded photos (start **static-image only**, since live camera needs F14). Renderer + one primitive dict + ROTE adaptation — fits the SDUI mandate with no new runtime dependency.
- **Novelty 5 / Impact 4 / Effort L**

### F24. Context Caching + Batch API + long context (1M+ tokens)

- **Source**: Gemini API — Context Caching, https://ai.google.dev/gemini-api/docs/caching ; Batch API, https://ai.google.dev/gemini-api/docs/batch-api
- **What it is**: **Explicit caching** stores a large reusable prefix (system prompts, tool catalogs, docs — any modality) once and bills cached tokens at **~10% of normal** on 2.5+ models; **implicit caching** is on by default for all 2.5+ models. Caching spans 2,048 tokens up to the full window (2.5 Pro >1M). The **Batch API** runs async jobs at **50% cost**, 24-hour turnaround, supporting `cached_content` reuse.
- **Frontier evidence**: "pay only 10% of standard input token cost for cached tokens"; "Batch API … 50% of the standard interactive API cost"; caching up to a >1M-token window. **GA**; implicit caching default-on for Gemini 2.5+.
- **AstralBody gap**: AstralBody **re-sends** its system prompt, injected tool/agent catalog, and (for agentic creation) large codegen context every turn with no caching, and runs scheduled jobs synchronously rather than via a discounted async batch path — repeated large-prefix calls cost full price.
- **Priority**: **UX** (latency/cost)
- **How to implement**: If the provider behind `_call_llm` supports prompt/prefix caching (many OpenAI-compatible endpoints now do, often automatically or via a cache hint), **stabilize the prompt prefix order** (system + tool catalog first) so cache hits land, and route scheduled-job LLM work through a **batch/async endpoint** where available. Pure request-shaping + job-scheduling changes — no new runtime dependency.
- **Novelty 3 / Impact 4 / Effort M**

---

## Sources

**Gemini API / AI Studio docs (ai.google.dev)**
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/function-calling
- https://ai.google.dev/gemini-api/docs/thinking
- https://ai.google.dev/gemini-api/docs/google-search
- https://ai.google.dev/gemini-api/docs/code-execution
- https://ai.google.dev/gemini-api/docs/caching
- https://ai.google.dev/gemini-api/docs/batch-api
- https://ai.google.dev/gemini-api/docs/live-api
- https://ai.google.dev/gemini-api/docs/live-api/capabilities
- https://ai.google.dev/gemini-api/docs/interactions/computer-use
- https://ai.google.dev/gemini-api/docs/aistudio-build-mode

**Google / DeepMind blogs & research (blog.google, research.google, deepmind.google)**
- https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/
- https://blog.google/products/gemini/gemini-3-gemini-app/
- https://blog.google/products/gemini/gemini-collaboration-features/
- https://blog.google/innovation-and-ai/products/gemini-app/personal-intelligence/
- https://blog.google/products-and-platforms/products/gemini/gemini-personalization/
- https://blog.google/innovation-and-ai/products/nano-banana-pro/
- https://deepmind.google/models/gemini-image/pro/
- https://blog.google/innovation-and-ai/technology/ai/io-2025-keynote/
- https://blog.google/innovation-and-ai/technology/developers-tools/full-stack-vibe-coding-google-ai-studio/
- https://blog.google/innovation-and-ai/models-and-research/google-deepmind/gemini-computer-use-model/
- https://blog.google/innovation-and-ai/models-and-research/google-deepmind/gemini-2-5-native-audio/
- https://blog.google/products/gemini/gemini-live-updates-august-2025/
- https://blog.google/technology/google-deepmind/gemini-universal-ai-assistant/
- https://deepmind.google/models/project-astra/
- https://gemini.google/overview/agent/spark/
- https://support.google.com/gemini/answer/16047321

**Developers / Cloud / Android / Chrome (developers.googleblog.com, cloud.google.com, developer.android.com, developer.chrome.com, firebase.google.com)**
- https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/
- https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- https://developers.googleblog.com/en/meet-jules-tools-a-command-line-companion-for-googles-async-coding-agent/
- https://developers.googleblog.com/developers-guide-to-ai-agent-protocols/
- https://blog.google/innovation-and-ai/models-and-research/google-labs/jules-tools-jules-api/
- https://jules.google/
- https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service
- https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-memory-bank-in-public-preview
- https://cloud.google.com/blog/products/ai-machine-learning/new-enhanced-tool-governance-in-vertex-ai-agent-builder
- https://cloud.google.com/blog/products/ai-machine-learning/announcing-official-mcp-support-for-google-services
- https://firebase.google.com/docs/ai-logic/hybrid-on-device-inference
- https://developer.android.com/ai/hybrid
- https://developer.android.com/ai/gemini-nano
- https://developer.chrome.com/blog/ai-api-updates-io25
- https://developer.chrome.com/docs/ai/built-in-apis
- https://android-developers.googleblog.com/2025/05/on-device-gen-ai-apis-ml-kit-gemini-nano.html
- https://android-developers.googleblog.com/2025/10/ml-kit-genai-prompt-api-alpha-release.html
- https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html
- https://blog.google/products-and-platforms/platforms/android/android-xr-io-2026/
- https://developer.android.com/blog/posts/build-for-ai-glasses-with-android-xr-sdk-developer-preview-3
- https://developers.googleblog.com/en/introducing-gemma-3n-developer-guide/
- https://ai.google.dev/gemma/docs/gemma-3n

**ADK / A2A / Agent Identity (adk.dev, a2a-protocol.org, docs.cloud.google.com)**
- https://adk.dev/evaluate/criteria/
- https://adk.dev/agents/workflow-agents/
- https://adk.dev/tools-custom/function-tools/
- https://adk.dev/mcp/
- https://a2a-protocol.org/v0.3.0/specification/
- https://a2a-protocol.org/latest/topics/a2a-and-mcp/
- https://github.com/a2aproject/A2A/releases
- https://docs.cloud.google.com/iam/docs/agent-identity-overview
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview

**Reference / corroboration**
- https://en.wikipedia.org/wiki/Google_Antigravity
