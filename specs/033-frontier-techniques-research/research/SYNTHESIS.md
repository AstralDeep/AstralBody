# Frontier Capabilities — Synthesis & Prioritized Capability Backlog

> Cross-stream synthesis of the eight research files in this folder, deduplicated and
> ranked by the project's priority order: **Novelty (paramount) > User Experience >
> Device Adaptation > Agentic Security.** Compiled 2026-06-16 for feature
> `033-frontier-techniques-research`.
>
> Source streams (read these for full per-finding detail, sources, and implementation notes):
> `commercial-openai.md` (17), `commercial-google.md` (24), `commercial-others.md` (25),
> `scholarly-agentic-frameworks.md` (20+8), `scholarly-generative-ui.md` (21),
> `scholarly-memory-personalization.md` (18), `scholarly-agentic-security.md` (19),
> `scholarly-device-adaptation.md` (20). **≈164 raw findings → 71 consolidated capabilities below.**

## 1. Method & corpus

Eight parallel analysts surveyed the mid-2026 commercial frontier (OpenAI, Google/DeepMind,
Anthropic, Microsoft, Meta, Amazon, Vercel, and agent startups) and the recent scholarly
literature (arXiv / CHI / UIST / IUI / NeurIPS / ICML / ICLR / ACL / IEEE S&P / USENIX / CCS /
NDSS / IETF / OWASP, 2023–2026), each against the same AstralBody baseline and the same
hard constraints: **Python backend only, no new third-party runtime libraries, the SDUI mandate
(astralprims defines → orchestrator renders → ROTE adapts), idempotent startup migrations,
fail-closed.** Every consolidated capability below is achievable inside those constraints unless
explicitly flagged in §6. Source quality was enforced: scholarly streams cite primary venues
(no Medium / listicles); commercial streams cite official docs/blogs/keynotes with preview-vs-GA
flags and explicit "vendor hype" call-outs.

Scoring legend per capability: **Nov** = novelty 1–5, **Imp** = impact 1–5, **Eff** = effort
S/M/L, **Consensus** = number of independent streams that surfaced it (a proxy for confidence —
≥3 streams = "convergent", the highest-confidence signal in the corpus).

## 2. Convergent themes (highest-confidence — surfaced independently by ≥3 streams)

1. **Enforce, don't hope: constrained-decoding structured output.** OpenAI (CFG token-masking,
   100% schema conformance), Google (`responseSchema`), and the reliability needs implicit in the
   agentic-frameworks/UI streams all converge. AstralBody runs several best-effort-JSON LLM loops
   (UI-designer layout tree, codegen, tool args) with retry/repair workarounds. **The single
   lowest-effort, highest-leverage change in the corpus.** → C-N14.
2. **Generate a *model*, render the UI.** The UI literature (task-driven data model, IRs, FSM
   interface representations) and Google's Dynamic View converge on separating a typed task/data
   representation from rendering. AstralBody arranges *finished* components and never models the
   task — the biggest structural UX/novelty gap. → C-N1.
3. **Move judgment from the LLM to a deterministic, learnable scorer.** Draco/optimization,
   adaptive-reward generative interfaces, AUIT/SituationAdapt, and Apple UICoder/designer-feedback
   all say: LLM *proposes*, code *scores/decides*. AstralBody's "keep-best" has no objective
   function. → C-U1.
4. **Deterministic interception / pre-action policy pipeline.** Anthropic Hooks, Semantic Kernel
   Filters, Llama Stack Shields, AgentSpec, GuardAgent, "Before the Tool Call", Google's Layer-1
   all converge on one ordered, fail-closed enforcement surface before every tool call. AstralBody's
   gates (PHI, scopes) are hand-coded one-offs. → C-S3.
5. **Security by construction, not detection.** The Design-Patterns paper, CaMeL, f-secure,
   IPIGuard, and "restrict data types" converge: once untrusted input is ingested, structurally bar
   consequential actions (plan-then-execute, dual-LLM, taint/provenance, typed values). AstralBody's
   fetch/summarize/parse flows have none of these. → C-S1/C-S2.
6. **Reconcile, don't just append (memory).** Mem0, A-MEM, Zep, Memory Bank (Vertex) converge on an
   LLM-mediated write path that links/supersedes/decays instead of monotonic store+summarize.
   AstralBody's "dreaming" only condenses. → C-M1/C-M2.
7. **Context engineering as the economic lever.** Manus (KV-cache stability), Anthropic
   (tool-search/`defer_loading`, context editing), Google (prompt caching) converge at ~100:1
   input:output token ratios. AstralBody "builds tool lists per chat" and injects volatile prefix
   content. → C-N16.
8. **Capability negotiation + declarative host-config for device adaptation.** Airbnb/Netflix/Lyft
   SDUI and Microsoft Adaptive Cards converge: client declares its renderer vocabulary; server
   returns only what it can render, as *data* not code, with versioned contracts + fallbacks.
   ROTE is a one-shot per-type code transform. → C-D1/C-D2.
9. **Trajectory-level evaluation + reliability metrics.** Google ADK trajectory metrics,
   Agent-as-a-Judge, τ-bench `pass^k`, debiased-judge studies converge: judge the *steps* and
   *consistency*, not the final answer. AstralBody self-tests are single-shot `pass^1`. → C-N5.
10. **Async / parallel / long-horizon agents are the new default**, with **fresh-context fan-out**
    to beat the documented >8-item context-degradation ("fabrication mode"). Google (Mariner/Spark,
    Jules), Manus (Wide Research), Cognition (managed Devins), Anthropic (multi-agent research)
    converge. AstralBody runs one synchronous turn. → C-N8.
11. **Runtime supervision + spotlighting are the cheap injection floor.** OpenAI monitor model,
    Sierra/Decagon supervisors, Meta LlamaFirewall AlignmentCheck, Microsoft spotlighting/datamarking
    converge on parallel review + string-level boundary marking (ASR ~50%→<3%). AstralBody has no
    runtime output supervision. → C-S4/C-S5.

## 3. Prioritized capability backlog (deduplicated)

IDs are stable references used by `spec.md`. "Sources" cite the per-stream finding IDs
(e.g. `OAI-F8` = `commercial-openai.md` F8; `GUI-F1` = generative-ui F1; `SEC-F2` = security F2;
`MEM-F1`; `DEV-F4`; `AF-F3` = agentic-frameworks; `GOO-F1`; `OTH-F9` = others).

### 3.1 Tier NOVELTY (priority #1) — structural / architectural moves

| ID | Capability | Sources | Nov | Imp | Eff | Consensus |
|----|-----------|---------|-----|-----|-----|-----------|
| C-N1 | **Task-model-first generative UI** — generate a typed task/data model (entities, typed attributes, dependency edges) first; derive the layout tree deterministically via `<function, render, editable>` annotation rules | GUI-F1, GUI-F2, GUI-F4, GOO-F1 | 5 | 5 | L | convergent |
| C-N2 | **Gated open-ended / generative primitives** — let the LLM compose *new* widgets/micro-interactions beyond the closed 31-type palette, expressed as a constrained grammar + post-validator, rendered via escape-by-default sanitizer / sandboxed `srcdoc`, new primitives ride the draft→self-test→admin-approval rail | GOO-F1, GOO-F2, OAI-F1(apps), OTH-F15, GUI-F6, GUI-F18, GUI-F19 | 5 | 5 | L | convergent |
| C-N3 | **Optimizable agent graph + dynamic team selection** — model the orchestrator→specialist fleet as a learnable graph (edge weights per task-fingerprint); recruit top-k specialist *teams* for hard turns by an importance score | AF-F1, AF-F2, AF-F11 | 5 | 5 | L | 1 stream (deep) |
| C-N4 | **Evolutionary, archive-conditioned auto-create + surrogate predictor** — store every draft's code+self-test score+gap fingerprint; condition codegen on top archived exemplars; pre-score drafts with a cheap LLM rubric *before* the costly self-test | AF-F3, AF-F4, AF-F6, MEM-F18 | 5 | 5 | M | 1 stream (deep) |
| C-N5 | **Trajectory-evaluation backbone** — Agent-as-a-Judge over the existing hash-chained audit/tool-dispatch trace + `pass^k` reliability + debiased (order-swapped) judging; becomes the metric powering C-N3/C-N4/C-N6 and a regression harness | AF-F12, AF-F13, AF-F14, GOO-F11 | 4 | 5 | M | convergent |
| C-N6 | **Compound-system optimization (ported, no lib)** — offline "dreaming"-style optimizer that A/B-scores prompt/instruction/topology variants on a held-out set and persists winners (DSPy/MIPRO + TextGrad textual-backprop + MASS staged search, technique not package) | AF-F9, AF-F10, AF-F11 | 4 | 4 | M-L | 1 stream (deep) |
| C-N7 | **Dual-ledger self-correcting orchestration** — Magentic Task-Ledger + per-step Progress-Ledger JSON + stall-counter replanning; converts single-hop dispatch into an inspectable multi-step controller | OTH-F9 | 4 | 5 | M | 1 stream |
| C-N8 | **Async / parallel fresh-context fan-out** — user-launchable concurrent background tasks, each an isolated `VirtualWebSocket` sub-run with a clean context; controller decomposes → scatter → self-verify → gather; fixes >8-item fabrication | GOO-F8, OTH-F10, AF (multi-agent) | 4 | 5 | L | convergent |
| C-N9 | **Mixture-of-Agents / multi-agent debate for hard turns** — difficulty-gated propose→aggregate (MoA) and pairwise debate-then-judge for high-stakes/low-confidence turns | AF-F7, AF-F8 | 3 | 5 | S | 1 stream |
| C-N10 | **Procedural / skill memory + workflow induction** — distill successful tool-call traces into retrievable, self-verified, parameterized recipes; replay under existing scopes+audit | MEM-F7, MEM-F8, AF-F17 | 4 | 4 | L | convergent |
| C-N11 | **Sleep-time compute** — reframe "dreaming" to *anticipate* likely next questions and precompute derived facts/answers during idle time, amortized across queries | MEM-F6 | 5 | 4 | M | 1 stream |
| C-N12 | **Create-and-retrieve tool library** — abstract verified tool code from successful generated agents into a deduped, multi-view-retrieved library; retrieve-before-generate on a new gap | AF-F15, AF-F16 | 4 | 4 | M | 1 stream |
| C-N13 | **External interop: A2A Agent Cards + MCP-server façade + agent identity** — serve `/.well-known/agent-card.json`, a JSON-RPC Task lifecycle, and an MCP-server re-export of the tool registry, all as pure-Python protocol shapes over existing dispatch + RFC 8693 | GOO-F12, GOO-F13, GOO-F22, SEC-F8, AF-HM | 4 | 4 | L | convergent |
| C-N14 | **Enforced structured output (constrained decoding)** — `response_format`/`strict` JSON-schema passthrough on the existing client; capability-probe + graceful fallback. *The quick win.* | OAI-F8, GOO-F3, GOO-F18 | 4 | 5 | **S** | convergent |
| C-N15 | **Two-tier tool output** — split every component/tool result into a short `model_digest` (enters the LLM) and a `render_only` payload (renderer-only, stripped before any `_call_llm`); cuts tokens + closes an injection channel | OAI-F1 | 4 | 5 | **S** | 1 stream |
| C-N16 | **Context engineering** — KV-cache-stable prompt prefix (volatile content last, deterministic key order), tool-search/`defer_loading` meta-tool over the growing catalog, in-loop context editing (tombstone stale tool results), prefix caching, reasoning-budget knob | OTH-F1, OTH-F2, OTH-F11, GOO-F17, GOO-F24 | 4 | 5 | S-M | convergent |

### 3.2 Tier USER EXPERIENCE (priority #2)

| ID | Capability | Sources | Nov | Imp | Eff | Consensus |
|----|-----------|---------|-----|-----|-----|-----------|
| C-U1 | **Deterministic layout scorer** — pure-Python `score_arrangement(tree, device)` (alignment, grouping, density, device-fit, effort proxies); LLM proposes k candidates, scorer selects; reframes the designer's open-ended self-critique as search-with-a-reward | GUI-F3, GUI-F5, GUI-F8, GUI-F10, DEV-F4, DEV-F5 | 4 | 5 | M | convergent |
| C-U2 | **Conservative adaptation with disruption cost** — penalize redesign by edit-distance from the user's current persisted layout; only re-arrange when net-beneficial vs a margin (the user's "predictability" dial) | GUI-F9, GUI-F12 | 4 | 5 | **S** | 1 stream |
| C-U3 | **Interaction-archetype selection up front** — classify the turn {compare, monitor, explore, summarize, decide, form} and seed a layout prior + scorer weights | GUI-F4 | 4 | 5 | M | 1 stream |
| C-U4 | **Bidirectional co-generative canvas** — feed `component_action`/filter/selection signals back into the designer + task model; in-component state becomes conversational context (`ui/update-model-context`) | GUI-F11, OAI-F6 | 5 | 4 | M | convergent |
| C-U5 | **Per-user UI-preference dials + RAG-from-history** — {predictability, efficiency, explorability} dials; retrieve the user's accepted arrangements for similar archetypes as exemplars | GUI-F7, GUI-F21 | 4 | 4 | M | 1 stream |
| C-U6 | **Provenance / uncertainty surfacing + fact-grounding + inline citations** — confidence/provenance attribute → subtle Badge; entity facts in components must trace to a tool/search result; pre-generation `[ref:id]` citation binding | GUI-F16, GUI-F17, GOO-F7, OTH-F16 | 4 | 5 | M | convergent |
| C-U7 | **Dark-pattern / persuasion-safety lint** — deterministic lint over designer-added garnish (false urgency, confirmshaming, destructive-CTA emphasis, preselected opt-ins); downgrade/strip + audit | GUI-F15 | 4 | 4 | M | 1 stream |
| C-U8 | **Proactive digest surface (Pulse) + conversational scheduled tasks** — overnight "dreaming" sweep emits a card-grid chrome surface; model-proposed schedule + user confirmation; push/email via egress-gated HTTP | OAI-F14, OAI-F15 | 4 | 4 | M | 1 stream |
| C-U9 | **Scoped / project memory boundary** — a `project_id` namespace grouping chats + files + instructions + an isolated memory slice | OAI-F16 | 3 | 4 | M | 1 stream |
| C-U10 | **In-place data-tool re-exec + streaming partial UI + async placeholder** — model-invisible data tools update a component without remount; skeleton→progressively-filled component over `ui_upsert`; slow tools return a placeholder and stream in | OAI-F2, OAI-F12, OTH-F15 | 3 | 4 | M | convergent |
| C-U11 | **Manipulable charts + expanded chart vocabulary** — hover/recolor/ask-against-the-chart; add heatmap/treemap/radar/waterfall/box renderers | OAI-F17 | 2 | 3 | M | 1 stream |
| C-U12 | **Reasoning-budget knob + reasoning disclosure** — per-call-site `reasoning_effort`/thinking-budget threaded through `_call_llm`; optional reasoning-summary disclosure primitive | GOO-F17 | 4 | 4 | **S** | 1 stream |
| C-U13 | **Editorial/magazine generative layout + in-result refinement modules** — labeled input/chip primitives embedded in the result that re-run the source tool with adjusted params | GOO-F2 | 4 | 4 | M | 1 stream |
| C-U14 | **MCP elicitation** — protocol-standard mid-tool "stop and ask for typed input" with accept/decline/cancel; "MUST NOT elicit sensitive info" check | OTH-F4 | 3 | 3 | M | 1 stream |
| C-U15 | **Build-an-agent-from-a-prompt (gated, non-admin) + annotation-mode editing** — wrap the 027 lifecycle for end users with per-user sandbox visibility + admin go-live; highlight-a-primitive-and-describe-a-change editing | GOO-F19 | 5 | 4 | L | 1 stream |

### 3.3 Tier USER EXPERIENCE — Memory & personalization (UX/Novelty blend)

| ID | Capability | Sources | Nov | Imp | Eff | Consensus |
|----|-----------|---------|-----|-----|-----|-----------|
| C-M1 | **Reconcile-don't-append write path** — LLM-mediated ADD/UPDATE/DELETE/NOOP with supersession (soft-delete + `superseded_by`) instead of monotonic growth | MEM-F1, GOO-F16 | 4 | 5 | M | convergent |
| C-M2 | **A-MEM linked notes + memory evolution** — each memory a note (keywords/tags/context/embedding/links); new memories rewrite neighbors' interpretation; powers graph retrieval | MEM-F2 | 5 | 5 | M | 1 stream |
| C-M3 | **Graph / Personalized-PageRank associative retrieval** — entity graph in Postgres; ~40-line pure-Python PageRank for single-step multi-hop "connect-the-dots" recall | MEM-F3 | 4 | 5 | M | 1 stream |
| C-M4 | **Multi-signal retrieval (recency × importance × relevance)** — add `importance`/`last_accessed_at`; retrieval becomes a Postgres `ORDER BY`. Cheapest big memory win | MEM-F4 | 2 | 5 | **S** | 1 stream |
| C-M5 | **Reflection insight nodes (cited)** — threshold-triggered synthesis of higher-order, provenance-linked insights queryable like memories | MEM-F5 | 3 | 4 | M | 1 stream |
| C-M6 | **Temporal validity + contradiction resolution + abstention** — `valid_from/valid_to/ingested_at`; as-of queries; clarify instead of guessing on conflict/low-confidence | MEM-F10, MEM-F11 | 3 | 5 | M | convergent |
| C-M7 | **Principled forgetting (Ebbinghaus) + safety-triggered forgetting** — strength/decay with reinforcement-on-recall; doubles as PHI minimization / GDPR data-minimization | MEM-F13 | 3 | 4 | **S** | 1 stream |
| C-M8 | **Evolving optimizable persona + preference feedback** — living human-readable persona refined by replaying recent turns (textual loss, keep-best); route feature-004 feedback into per-user steering | MEM-F15, MEM-F16 | 4 | 5 | M | 1 stream |
| C-M9 | **Memory provenance / editing / unlearning surface** — user-facing "forget/correct this"; external memory makes deletion genuine; audited | MEM-F17 | 3 | 4 | M | 1 stream |
| C-M10 | **Heat-based tiered memory** — heat = access×recency×importance drives short→long promotion vs eviction; durable personal tier separate from episodic | MEM-F12 | 2 | 4 | M | 1 stream |
| C-M11 | **Episodic segmentation by surprise + temporal-contiguity retrieval** — topic-shift episode boundaries; fetch a recalled memory's neighbors | MEM-F14 | 3 | 3 | M | 1 stream |

### 3.4 Tier DEVICE ADAPTATION (priority #3)

| ID | Capability | Sources | Nov | Imp | Eff | Consensus |
|----|-----------|---------|-----|-----|-----|-----------|
| C-D1 | **Capability-negotiated component contracts + versioned schemas + fallback ladder** — each renderer target publishes its supported-primitive set + contract version; ROTE filters/substitutes (timeline→list, chart→table→text) | DEV-F1, DEV-F2, DEV-F3 | 4 | 5 | M | convergent |
| C-D2 | **Declarative per-target host-config (data not code)** — supported types, density/contrast caps, max-actions, LoD default, `supports_interactivity` as a tunable dict; bounds what a compromised agent renders per surface | DEV-F20, OTH-F7, OTH-F8 | 4 | 4 | **S** | convergent |
| C-D3 | **Declarative multi-objective adaptation feeding the designer** — weighted-objective scorer (width-fit, interaction-cost, glanceability, speakability) replaces per-type branches; optional LLM/VLM-judged suitability cost; makes the designer device-aware | DEV-F4, DEV-F5 | 5 | 5 | L | convergent |
| C-D4 | **Real structured VOICE renderer** — SSML + navigable axis→series→point / header→rows tree + 3 verbosity tiers + deterministic earcon/sonification tokens (the emptiest, most-novel target) | DEV-F6, DEV-F7 | 5 | 5 | M | convergent |
| C-D5 | **AOM / semantic-tree renderer** — serialize the astralprims graph to a navigable role/name/state tree (not HTML); cleanest "add a target = add a renderer" proof; powers VOICE/AT | DEV-F15 | 4 | 4 | M | 1 stream |
| C-D6 | **Compute-placement model router + on-device lane** — device-capability-aware tier selection / cascade in front of `client_factory`; optional browser-built-in-AI (Gemini Nano / Chrome Summarizer) lane with server-authoritative fallback | DEV-F8, DEV-F9, GOO-F4, GOO-F5 | 5 | 5 | M | convergent |
| C-D7 | **Live viewport/theme/context feedback loop** — additive `viewport_update`/`device_context_changed` WS message; ROTE re-adapts the current canvas and pushes a targeted upsert (the `set_globals` analog); + connectivity/interruptibility signals | DEV-F10, DEV-F11, OAI-F3 | 3 | 4 | M | convergent |
| C-D8 | **Cross-surface component distribution + companion screen** — device-affinity tag routes different components to different simultaneous device sockets (controls→phone, canvas→TV) over the existing per-component overlay + multi-socket fan-out | DEV-F12, DEV-F13 | 5 | 4 | L | 1 stream |
| C-D9 | **Accessibility as a generation/render constraint** — WCAG-by-construction HTML (landmarks, aria, computed contrast) + WCAG checklist in the designer + deterministic a11y post-validator; ability profiles (low-vision/motor/reduced-motion/cognitive-load) as ROTE dimensions | DEV-F14, GUI-F20 | 4 | 4 | M | convergent |
| C-D10 | **Tiered level-of-detail ladder + modality routing** — author once as L1 index/L2 summary/L3 detail; ROTE pulls the depth per device; choose primary modality per surface (VOICE→1-sentence+offer-detail, TV→visual-first) | DEV-F16, DEV-F17 | 3 | 4 | M | 1 stream |
| C-D11 | **New render targets** — TV focus-graph (D-pad neighbor order), glasses/heads-up (single-line + one action, TTS-first), AR/spatial placement spec; each a new renderer, primitives unchanged | DEV-F18, DEV-F19, GOO-F21, GOO-F23 | 4 | 3 | L | convergent |

### 3.5 Tier AGENTIC SECURITY (priority #4)

| ID | Capability | Sources | Nov | Imp | Eff | Consensus |
|----|-----------|---------|-----|-----|-----|-----------|
| C-S1 | **Security-by-construction flow patterns** — route each turn to the minimal pattern: read-only summarize/fetch → context-minimization + action-selector (toolless model call on untrusted text); multi-tool → plan-then-execute (commit plan before untrusted data; refuse out-of-plan calls); parser → map-reduce (isolated per-file structured extraction) | SEC-F1, SEC-F16, AF-F19 | 5 | 5 | M | convergent |
| C-S2 | **Taint/provenance graph + value-level data-flow policy** — label every tool result `trusted`/`untrusted`; effective trust = min over data ancestors; refuse untrusted-tainted values reaching write/egress sinks (CaMeL enforcement idea) | SEC-F2, SEC-F3 | 5 | 5 | M-L | convergent |
| C-S3 | **Deterministic pre-action policy engine** — one ordered fail-closed rule chain (trigger/predicate/enforcement: allow/deny/confirm/rewrite) run before every tool call; PHI gate + scope check become two seed rules; admin-extensible as data; LLM may *propose* rules humans approve | SEC-F4, SEC-F5, SEC-F19, OTH-F5, OTH-F6 | 4 | 5 | M | convergent |
| C-S4 | **Spotlighting/datamarking + surgical sanitization** — per-turn sentinel + token datamarking around untrusted spans (ASR ~50%→<3%); optional span-level removal of instruction-like content from tool outputs | SEC-F7, SEC-F13 | 3 | 4 | **S** | 1 stream |
| C-S5 | **Runtime supervisor / intent-alignment gate** — pre-send review of a draft response/component (revise/block/escalate); intent-alignment check that a tool call matches the user's request; input-scan on untrusted ingress | OTH-F17, OAI-F9, SEC (AlignmentCheck), AF-F8 | 4 | 5 | M | convergent |
| C-S6 | **Isolated / sandboxed codegen + parser execution** — run generated agent/parser code in a child process with `resource` rlimits, stripped env, temp-scoped FS, blocked sockets; all cross-agent/egress via the single dispatch mediator | OTH-F12, SEC-F9 | 3 | 5 | M-L | convergent |
| C-S7 | **Adversarial red-team self-test + AstralDojo CI suite** — extend the VirtualWebSocket self-test with injected/hostile inputs + an LLM safety-evaluator over the trajectory; add a pytest "AstralDojo" CI job asserting zero out-of-scope tool calls / egress / PHI | SEC-F10, SEC-F12 | 3 | 5 | M | convergent |
| C-S8 | **Transaction tokens + agent identity + per-(agent,user) vault** — single-use authorization bound to `(agent, user, tool, hash(args))` via existing HMAC; agent as a first-class principal (`client_id` claim, user in `sub`); third-party tokens physically partitioned by {agent,user} | SEC-F8, OTH-F13, GOO-F13 | 4 | 5 | M | convergent |
| C-S9 | **Memory-poisoning defense** — refuse consolidating untrusted-derived content into durable memory without human confirm; HMAC-sign memory rows; retrieval-time trust filtering (defends the flagship "soul" feature) | SEC-F11 | 4 | 5 | M | 1 stream |
| C-S10 | **Typed-value privilege separation at trust boundaries** — parser/summarizer sub-calls must return structured typed objects (enums/numbers/IDs/records), not free text, before any privileged tool consumes them | SEC-F18 | 3 | 4 | M | 1 stream |
| C-S11 | **Runtime human-in-the-loop for high-risk actions + escalation policy** — typed risk codes (egress, cross-principal, irreversible, untrusted-tainted) → provenance-showing confirmation card; escalation triggers (confidence/sentiment/loop/policy) + warm handoff with summary | SEC-F17, OTH-F18, OAI-F10 | 3 | 4 | M | convergent |
| C-S12 | **OWASP ASI + Google-principles coverage matrix + observable planning** — publish an ASI01–ASI10 control matrix; persist the pre-execution plan into the audit chain so intended-vs-actual deviation is detectable | SEC-F14, SEC-F15 | 2 | 4 | S | 1 stream |
| C-S13 | **MCP descriptor pinning / integrity** — pin & integrity-check tool descriptors; re-run the security gate on any descriptor change (tool-poisoning/rug-pull defense for a self-generating-tools system) | SEC-HM | 3 | 4 | M | 1 stream |
| C-S14 | **Multi-agent-system attack defenses** — inter-agent message provenance/integrity over the audit chain + per-edge scoping + a TAMAS-style red-team suite (required the moment C-N3/C-N8/C-N9 multi-agent flows ship) | AF-F20 | 4 | 5 | M | convergent |

## 4. Recommended sequencing (waves)

> **Locked decisions (2026-06-16, with user):** Branch 033 delivers **research + roadmap only —
> no product code**. Implementation is delivered via approved follow-on feature branches. The
> **co-flagship trio — generative model-grounded UI (Wave 1), self-improving agent architecture
> (Wave 2), and living memory & personalization (Wave 2′) — lead together** as the first follow-on
> specs, each pulling in the Wave-0 enablers it depends on. Selection is **novelty-forward** (lead
> with the boldest structural bets, paired with the cheap convergent enabler each needs). Device
> (Wave 3) and preventive security (Wave 4) follow, except security controls timed to their
> dependents (see below). The corpus is **locked as sufficient**.

The waves below sequence by *dependency + risk-adjusted leverage*, while honoring the priority
order (novelty > UX > device > security) for *what* gets the deepest investment. Each wave is its
own approval-gated follow-on feature; none begins until the user opens its spec.

- **Wave 0 — Foundations & quick wins (high confidence, low effort, unblock everything).**
  C-N14 (structured output), C-N15 (two-tier output), C-N16 (context engineering), C-N5
  (trajectory-eval backbone), C-S4 (spotlighting/datamarking), C-M4 (multi-signal retrieval),
  C-U2 (conservative adaptation), C-D2 (declarative host-config), C-U12 (reasoning budget). These
  are mostly Effort-S, convergent, and de-risk later waves (the eval backbone is the metric for
  every self-improving loop; structured output removes the JSON-repair loops the designer/codegen
  depend on).
- **Wave 1 — Flagship novelty + UX (priority #1–#2).** C-N1 (task-model-first UI), C-U1
  (deterministic layout scorer), C-U3 (archetype selection), C-U6 (provenance/grounding),
  C-U7 (dark-pattern lint), C-M1/C-M2 (reconcile + linked memory). This wave is the differentiator
  and the system's signature SDUI thesis taken to the frontier.
- **Wave 2 — Self-improving agent architecture (priority #1).** C-N4 (evolutionary auto-create +
  surrogate), C-N7 (dual-ledger orchestration), C-N8 (async fan-out), C-N3 (optimizable graph),
  C-N9 (MoA/debate), C-N10 (procedural memory), C-N11 (sleep-time compute). Each rides the
  Wave-0 eval backbone; multi-agent items trigger C-S14.
- **Wave 3 — Device & multimodal reach (priority #3).** C-D1 (capability negotiation), C-D3
  (multi-objective device-aware design), C-D4 (VOICE renderer), C-D6 (compute-placement router),
  C-D7 (live feedback), C-D9 (accessibility). The VOICE renderer (C-D4) is the highest-novelty,
  currently-emptiest target.
- **Wave 4 — Preventive security hardening (priority #4, but a safety prerequisite for autonomy).**
  C-S1 (by-construction patterns), C-S2 (taint/provenance), C-S3 (policy engine), C-S5 (runtime
  supervisor), C-S6 (sandboxed codegen), C-S7 (red-team self-test + AstralDojo), C-S8 (transaction
  tokens), C-S9 (memory-poisoning defense). **Note:** C-S6/C-S7/C-S9 should land *with or before*
  the Wave-2 autonomy increases they protect — security is priority #4 for *investment depth*, not
  for *timing* when it guards a shipping capability.
- **Wave 5 — Ecosystem & advanced surfaces.** C-N13 (A2A/MCP-server interop), C-U8 (proactive
  digest), C-U15 (build-an-agent-for-users), C-D8 (cross-surface distribution), C-D11 (new targets).

## 5. AstralBody is already at/above the frontier here — do NOT regress

These were flagged repeatedly across streams as *strengths* to protect, not gaps:

- **SDUI layout intelligence.** AstralBody's adaptive UI designer *arranges a layout tree*; OpenAI's
  Apps SDK model only picks the *tool* while devs pre-declare the layout. The gaps are in the
  *contract* (digest/render split, live device signals), not layout smarts.
- **In-process driving + self-test.** The `VirtualWebSocket` server→client capture and in-process
  self-test are ahead of Vercel's still-maturing `ChatTransport`; agentic self-test exists (the gap
  is depth/adversariality, not absence).
- **Deterministic PHI gate + tamper-evident hash-chained audit.** Stronger than Llama Guard's
  tunable false-positives and CloudWatch-style trails; the audit chain is an ideal substrate for
  taint-awareness (C-S2) and trajectory eval (C-N5).
- **RFC 8693 delegated attenuated scopes + fail-closed posture.** The right on-ramp for transaction
  tokens (C-S8); don't replace, extend.
- **Agentic creation + persistent workspace + cross-session memory.** Real differentiators; the
  frontier moves are *depth* (evolution, reconciliation, procedural memory), not net-new subsystems.

## 6. Explicitly deferred / out-of-constraint

Flagged by streams as needing a new dependency, hardware, or a media stack — **out of scope** under
the no-new-runtime-libs / Python-only constraints, tracked as future negotiations:

- **Real-time speech-to-speech voice transport** (OAI-F11, GOO-F14) — needs a media/WebRTC stack.
  *Portable now:* semantic-VAD turn-detection concept, async-function-call-with-placeholder (→ C-U10),
  and the VOICE *output* renderer (C-D4, which IS in scope).
- **Computer-use / browser pixel automation** (OAI-F10, GOO-F9) — needs a headless-browser dependency.
  *Portable now:* the `pending_safety_checks → acknowledged_safety_checks` typed must-ack gate (→ C-S11).
- **True on-device LLM decoding / speculative decoding** (DEV-F9) — AstralBody consumes an
  OpenAI-compatible endpoint. *Portable now:* the draft-verify *orchestration* analogue and the
  device-aware *router* (C-D6).
- **Graph-diffusion topology generation (GTD), full EvoMAC textual-backprop** (AF-HM) — heavy
  machinery; track as future work behind C-N3/C-N6.
- **Heavyweight vector DB / external memory store** — explicitly avoided; all memory capabilities
  (C-M*) are designed for Postgres + the existing LLM client.

## 7. Hype / caveats logged (so the roadmap isn't built on marketing)

- "The model designs the layout" (OpenAI Apps SDK) is mostly marketing — AstralBody is *ahead* here.
- Vendor-internal benchmarks (Sierra 90%→99%, Anthropic multi-agent +90.2%, Ramp "hours") are
  illustrative, not independently verified — the *mechanisms* are the value, not the numbers.
- Several 2026-dated arXiv UI papers (AlignUI, Google Generative UI, Deception-at-Scale) are very
  recent; a few were cited from abstracts/HTML where PDFs resisted parsing (noted in `scholarly-generative-ui.md`).
- GPT Store monetization, OGX/Llama-Stack renaming instability, and some "production-ready" claims
  are flagged preview/unstable in the source files.
