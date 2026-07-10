# OpenAI frontier — findings

> Research analyst report, mid-2026. Domain: OpenAI's product + platform frontier, mapped against the AstralDeep SDUI agentic platform to find **gaps** (things OpenAI ships that AstralDeep does not). Priorities in order: **novelty (highest), UX, device adaptation, agentic security.**
>
> **Sourcing caveat (important):** Most `openai.com/index/*`, `platform.openai.com/*`, and `help.openai.com/*` pages sit behind a Cloudflare bot challenge and return HTTP 403 to automated fetchers. Load-bearing mechanism detail below comes from pages that fetched cleanly — chiefly **`developers.openai.com/apps-sdk/*`** and **`developers.openai.com/api/docs/*`**, the **Agents SDK docs** (`openai.github.io`), OpenAI **system-card / framework PDFs** on `cdn.openai.com`, and OpenAI **GitHub repos** — corroborated by search-result excerpts of the blocked blog/help pages. Where a model-version string (e.g. "GPT-5.5", "gpt-image-2") or a metric comes from a third-party aggregator rather than an official page, it is flagged. Mechanisms and API field names below are quoted verbatim from official docs and are high-confidence; exact current model strings should be reconfirmed before quoting in production.
>
> **Status legend:** GA = generally available; Preview = research preview / beta; Policy = governance document, not a runtime guarantee.

---

## Executive summary

The single most strategically important finding is that **OpenAI's Apps SDK is a direct, production analog of AstralDeep's "primitives define → orchestrator renders → ROTE adapts" architecture** — and it solves several problems AstralDeep has not. Highest-novelty, most-implementable ideas:

- **F1 — Two-tier tool output (`structuredContent` for the model vs `_meta`/`privateContent` the model never sees).** Apps SDK splits every tool result into data the model reads, data only the widget renders, and data the model is forbidden to see. AstralDeep passes one component blob through the LLM; adopting a "model-visible digest vs render-only payload" split cuts tokens, prevents prompt-injection via rendered data, and lets large tables/charts render without poisoning context. **Lowest-effort, highest-leverage idea in this report.**
- **F2 — Decoupled data-tool / render-tool pattern.** OpenAI explicitly separates "data tools" (return `structuredContent`, no UI) from "render tools" (bind a template, draw once), and lets the *widget itself* call data tools for local interactions ("Re-roll") **without remounting**. This is a cleaner contract than AstralDeep's component-action re-execution and maps onto its existing `component_action` re-dispatch.
- **F3 — Host-provided global-context signals (`theme`, `displayMode`, `maxHeight`, `safeArea`, `locale`, `userAgent`) + a runtime `openai:set_globals` event.** OpenAI hands every component a typed device/theme context and re-fires it when the viewport changes. This is exactly the contract AstralDeep's ROTE *lacks* — ROTE adapts server-side once, but never gives primitives a live per-device signal. **Directly device-adaptation-relevant.**
- **F4 — Canvas as a *trained* "when to open a richer surface" decision, with measured lift (+30% trigger accuracy, +16% edit quality vs zero-shot).** OpenAI treats "should I surface a different UI / do a targeted edit vs full rewrite" as a fine-tunable capability, not a heuristic. AstralDeep's adaptive UI designer is prompt-only; the framing (targeted-section edit vs full re-render, learned trigger) is novel and adoptable as a few-shot/eval-graded routing policy.
- **F8 — Structured Outputs via constrained decoding (`strict: true` → CFG token masking → 100% schema conformance).** OpenAI guarantees schema-valid JSON by masking invalid tokens during sampling. AstralDeep's LLM loops (UI designer layout-tree JSON, agentic codegen, tool args) rely on best-effort JSON + retries; switching those calls to strict structured outputs removes a whole class of parse-retry failures. **High impact, low effort if the LLM provider supports it.**
- **F11/F12 — Realtime API (speech-to-speech) + image-input-to-voice.** A single speech-native model with semantic VAD, barge-in, async function calling, and SIP telephony. AstralDeep has a "voice" ROTE device target but no real-time bidirectional voice path. Large effort, but the **semantic-VAD turn-detection** and **async-function-call-with-placeholder** patterns are the novel, portable ideas.
- **F9 — Agentic prompt-injection defense as a *separate monitor model* + intent-alignment tool-call check.** OpenAI runs a dedicated injection-monitor that pauses a session (hot-patchable in hours) and an open-source Guardrails check that validates *tool calls align with user intent* (blocks `wire_money` when the user asked about weather). AstralDeep has a PHI gate and audit but no injection monitor or intent-alignment gate on tool calls — a concrete security gap given its untrusted-agent-output threat model.
- **F14/F15 — Proactive card surfaces (Pulse) + model-scheduled Tasks with push.** OpenAI ships an overnight-research card grid and conversational scheduled tasks with push/email delivery. AstralDeep has `scheduled_job`/job-auto-post but no proactive *non-conversational* card surface and no native push — adoptable atop its existing snapshot/timeline + memory machinery.

Cross-cutting reality check: OpenAI's "the model designs the layout" story is **mostly marketing** — in the Apps SDK the model picks the *tool/app*, but the developer pre-declares the *layout/display mode*. AstralDeep's adaptive UI designer (LLM arranges a layout tree) is actually *ahead* of OpenAI here; the gaps are in the **contract** (data/render split, model-vs-render payload, live device signals), not in layout intelligence.

---

## Findings

### F1. Two-tier tool output: `structuredContent` (model-visible) vs `_meta` / `privateContent` (render-only, never reaches the model)

- **Source:** Apps SDK — Build your ChatGPT UI / MCP server / Managing State. https://developers.openai.com/apps-sdk/build/chatgpt-ui , https://developers.openai.com/apps-sdk/build/mcp-server , https://developers.openai.com/apps-sdk/build/state-management
- **What it is:** Every Apps SDK tool result is split into three explicitly-scoped fields. **`structuredContent`** = "concise JSON the widget uses **and the model reads**" (drives the component *and* lets the model narrate). **`content`** = optional markdown narration. **`_meta`** = "large or sensitive data exclusively for the widget — **`_meta` never reaches the model**." Persisted widget state has the same split: a structured shape with **`modelContent`** (text/JSON the model should see), **`privateContent`** (UI-only, model must not see), and **`imageIds`**. So a single tool emission carries (a) a tight model-readable digest, (b) a bulky/private render payload, and (c) host directives — each with a distinct audience.
- **Frontier evidence:** Documented as a first-class contract with a verbatim rule ("`_meta` never reaches the model"; "keep `structuredContent` tight and idempotent — the model may retry tool calls"). OpenAI guidance: "Separate data-processing tools from render tools." This is shipped in the Apps SDK that launched DevDay Oct 6 2025 (beta).
- **AstralDeep gap:** AstralDeep's persistent workspace upserts the *entire* rendered component (and feeds component output through the adaptive-UI-designer LLM and chat narration). There is no notion of "the model sees a 200-token digest; the 50-row table renders but never enters context." This means (1) large components bloat LLM context and cost, (2) any untrusted text inside a rendered component (agent/tool output, fetched web data) is a prompt-injection vector because it flows into the model, and (3) the UI designer reasons over full payloads it doesn't need. This is the **single highest-leverage, lowest-effort** adoption in the report.
- **Priority:** Novelty (primary), Security (secondary).
- **How to implement in AstralDeep:** Extend the astralprims `Primitive`/`.to_dict()` contract (or the workspace upsert envelope) with two optional sibling fields alongside the component dict: a `model_digest` (short text/JSON the orchestrator injects into the LLM transcript and the UI designer) and a `render_only` payload (large/sensitive data the renderer consumes but the orchestrator strips before any `_call_llm`). Default `model_digest` to a truncated/summarized projection of the component when an author doesn't supply one. Enforce in `webrender` + the workspace/`_chat_narrative` path: components carry full data to `render()`, but only `model_digest` reaches `_call_llm` / `ui_designer`. No new dependency — pure dict-shape + a strip step.
- **Novelty 4 / Impact 5 / Effort S**

---

### F2. Decoupled data-tool vs render-tool pattern; widget calls data tools for local interaction without remounting

- **Source:** Apps SDK — Build your ChatGPT UI; Managing State; `window.openai.callTool`. https://developers.openai.com/apps-sdk/build/chatgpt-ui , https://developers.openai.com/apps-sdk/build/state-management
- **What it is:** OpenAI recommends splitting tools into **data tools** (return only `structuredContent`, no `_meta` template — the model reasons over them) and **render tools** (carry `_meta["openai/outputTemplate"]`, take already-validated data IDs, and draw the widget once). Crucially, after a widget is rendered, the **widget itself can call data tools directly** via `window.openai.callTool(name, args)` for "local interactions like 'Re-roll'" — updating in place **"without remounting the widget."** Tool visibility is controllable: `_meta.ui.visibility = ["app"]` makes a tool callable only from the widget and **hidden from the model**, so UI-only helpers don't pollute model tool-selection.
- **Frontier evidence:** Verbatim guidance: "Let the UI call data tools directly for local interactions without remounting the widget" / "keep reruns intentional." This is the mechanism behind in-widget refresh/pagination in shipped example apps (kanban, listings). Shipped in Apps SDK beta.
- **AstralDeep gap:** AstralDeep's `component_action` ui_event re-executes a component's *source tool* through the chat permission gates and updates it in place — conceptually similar — but there is no formal separation of "data tools vs render tools," no widget-callable tool that's hidden from the model, and the re-execution always routes back through the full orchestrator turn. AstralDeep could express richer in-place interactions (filter, sort, re-roll, paginate — `table_paginate` already exists) as cheap, model-invisible data calls.
- **Priority:** UX (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Formalize a tool annotation `render: false` / `model_visible: false` in the agent MCP tool registry. Let the orchestrator's `component_action`/`table_paginate` path dispatch such "data tools" without injecting them into the chat LLM's tool list or transcript (they update the component via the existing `ui_upsert` op and re-run the designer only if structure changed). This reuses 028's component-action re-dispatch and 029's overlay-layout model; the new piece is the *model-invisible* dispatch flag.
- **Novelty 3 / Impact 4 / Effort M**

---

### F3. Host-provided global-context signals (`theme`, `displayMode`, `maxHeight`, `safeArea`, `locale`, `userAgent`) + runtime `openai:set_globals` event

- **Source:** Apps SDK — Reference; Managing State; Troubleshooting. https://developers.openai.com/apps-sdk/reference , https://developers.openai.com/apps-sdk/build/state-management
- **What it is:** ChatGPT injects a typed environment context into every component via `window.openai`: **`theme`** (light/dark), **`displayMode`** (inline/fullscreen/PiP), **`maxHeight`** (available pixel height in the current mode), **`safeArea`** (safe render bounds, for notches), **`locale`** (BCP-47), **`userAgent`** (client id), plus `view`, `toolInput`, `toolOutput`, `toolResponseMetadata`, `widgetState`. When any of these change at runtime, the host fires a **`openai:set_globals` (`SetGlobalsEvent`)** event so the component can re-layout live ("For layout problems on mobile, inspect `window.openai.displayMode` and `window.openai.maxHeight` to adjust layout"). The example `useOpenAiGlobal` hook subscribes via `SET_GLOBALS_EVENT_TYPE`.
- **Frontier evidence:** Reference page enumerates these properties verbatim; troubleshooting docs direct developers to read `displayMode`/`maxHeight` for responsive layout. Shipped in Apps SDK beta.
- **AstralDeep gap:** This is the **device-adaptation gap most worth closing.** ROTE adapts a `ui_render` *server-side, once*, at send time, based on the device capabilities captured in `register_ui`. But (a) there is no live channel to re-adapt when a device rotates / a watch face wakes / a TV viewport changes without a full re-render, and (b) primitives themselves never receive a structured device/theme/locale/safe-area context — adaptation is entirely an opaque server transform. Components can't make fine-grained "I have 240px of height on a watch, collapse to a single metric" decisions because they don't get the signal. AstralDeep has *more* device targets than OpenAI (watch, TV, voice) but a *coarser* per-device contract.
- **Priority:** Device (primary), UX (secondary).
- **How to implement in AstralDeep:** Two parts. (1) Server-side: have ROTE pass a structured `device_context` ({theme, viewport_max_px, safe_area, locale, device_type, capabilities}) alongside each rendered component as data attributes (`data-astral-device-*`) so the no-build client can read them; this requires no new dependency and rides the existing `ui_render`/`ui_upsert` wire. (2) Add a lightweight WS message `device_context_changed {chat_id, device_context}` that the thin client emits on resize/orientation/theme change, which the orchestrator uses to re-run ROTE adaptation and push a targeted `ui_upsert` (not a full canvas re-render) — the live-event analog of `openai:set_globals`. ROTE's `capabilities.py`/`adapter.py` already model device types; this extends them with a *push-on-change* path.
- **Novelty 4 / Impact 4 / Effort M**

---

### F4. Canvas: model-*trained* decision to open a side surface and to do targeted-section edits vs full rewrites (measured lift)

- **Source:** Introducing Canvas. https://openai.com/index/introducing-canvas/ ; Canvas help. https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it
- **What it is:** Canvas is a side-by-side editing surface, but the architecturally interesting part is that **the model itself decides when to open it, when to make a targeted edit to a highlighted span, and when to fully rewrite.** OpenAI post-trained the model (originally GPT-4o) on these behaviors using **synthetic data distilled from o1-preview**, explicitly optimizing both *trigger accuracy* (open canvas for "write a blog post…" but not for general Q&A — avoid over-triggering) and *edit granularity* (patch a section vs regenerate). Structured generative actions are exposed as shortcuts (adjust length, change reading level, port-to-language, add comments/logs, code review with inline suggestions), and Python in canvas runs in a sandbox with inline output.
- **Frontier evidence:** OpenAI reports the canvas-trained model **outperforms zero-shot GPT-4o by 30% on trigger accuracy and 16% on edit-quality** — direct, quantified evidence that "when to surface a richer UI and at what edit granularity" is a *trainable* capability, not a prompt heuristic. GA (launched beta Oct 2024, now default).
- **AstralDeep gap:** AstralDeep's adaptive UI designer is a **bounded prompt-only LLM loop** (draft → critique → improve/DONE, fail-open to flat append). It decides *arrangement* but: (a) it always runs when ≥2 rich components exist — there's no learned "should I even design vs just stack" trigger; (b) it has no concept of *targeted re-edit of one region* vs *full re-arrangement* — every refinement re-emits the whole layout tree; (c) there's no eval/quality signal training the trigger or edit-granularity decisions. Canvas's targeted-edit framing maps directly onto AstralDeep's overlay-layout model (where components keep identities) and would make the designer cheaper and more stable.
- **Priority:** Novelty (primary), UX (secondary).
- **How to implement in AstralDeep:** (1) Add a cheap pre-pass "design trigger" classifier (few-shot, or a tiny rubric) so the designer only runs when arrangement actually helps — analogous to canvas trigger-training but achievable without fine-tuning. (2) Introduce a **targeted-edit op** to `ui_designer.py`: when refining, allow the model to return a patch addressing only specific `component_id`/region refs (move/regroup just those leaves) instead of the whole tree, reusing the `workspace_layout` overlay's ref-stealing semantics — fewer tokens, less churn, keep-best stays valid. (3) Capture designer outcomes (`stable`/`rejected:incomplete`/`fallback`) as an eval set to grade trigger + edit decisions over time (feeds 004 feedback infra). No new dependency.
- **Novelty 4 / Impact 4 / Effort M**

---

### F5. Apps SDK MCP-resource UI templates bound to tools via `_meta["openai/outputTemplate"]` + `text/html;profile=mcp-app`

- **Source:** Apps SDK — MCP server / Build your ChatGPT UI. https://developers.openai.com/apps-sdk/build/mcp-server , https://developers.openai.com/apps-sdk/build/chatgpt-ui
- **What it is:** A component template is registered as an **MCP resource** (via `registerAppResource(...)`) with URI like `ui://widget/kanban-board.html` and MIME `text/html;profile=mcp-app`. A tool binds to it by returning `_meta["openai/outputTemplate"]` (alias `_meta.ui.resourceUri`) = that URI. The host fetches the registered resource and renders it in a sandboxed iframe, passing the tool's `structuredContent` over the bridge. Additional resource `_meta`: `ui.csp` (Content-Security-Policy for the iframe's allowed domains), `ui.prefersBorder`, `ui.domain`. This is "UI shipped as data, addressed by URI, late-bound to tool output" — the same shape as AstralDeep's SDUI, but with the renderer living client-side in an iframe rather than server-side.
- **Frontier evidence:** Verbatim registration signature and MIME type in docs; CSP-per-widget is a concrete sandbox control. Shipped in Apps SDK beta; launch partners (Spotify, Zillow, Canva, Figma, Booking, Expedia) ship such widgets.
- **AstralDeep gap:** AstralDeep renders primitives **server-side to HTML** (no iframe, escape-by-default) and has no per-component CSP or sandbox boundary because there's no untrusted client code — which is *safer* than iframes. The genuine gap is **per-component CSP / capability scoping as data** and the **late-binding-by-URI** indirection: AstralDeep primitives are inline structured dicts, so there's no clean way for an *agentically-created* tool to ship a richer, reusable, versioned UI template that the renderer resolves by reference. As AstralDeep's agentic-creation system grows, a "register a render template as an addressable resource" concept would let auto-created agents ship novel layouts safely.
- **Priority:** Security (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Mostly an *avoid-the-iframe* validation: keep server-side rendering, but (1) add an optional per-component CSP/capability descriptor in the workspace envelope that `webrender` honors when a component embeds external media (images/links) — tightening the existing `esc()`-by-default posture with explicit allowlists; (2) for agentic-creation, let a generated agent register a *named astralprims composition template* (a layout tree of existing primitive types, addressed by id) that the orchestrator resolves at render time — reusing the 029 `workspace_layout` ref-leaf model — so novel UI is expressed as composition-of-vetted-primitives, never as arbitrary HTML. No new dependency; preserves the SDUI mandate.
- **Novelty 3 / Impact 3 / Effort M**

---

### F6. `ui/update-model-context` + structured `widgetState.modelContent`: pushing component UI-state back into the model's context

- **Source:** Apps SDK — Managing State. https://developers.openai.com/apps-sdk/build/state-management
- **What it is:** When a user interacts with a rendered component (selects a row, stages an edit, applies a filter), the component pushes that state back into the model's context via the JSON-RPC method **`ui/update-model-context`** (so the model's *next* turn knows "the user selected listing #3"), and/or persists it with `setWidgetState` using the structured `{modelContent, privateContent, imageIds}` shape where only `modelContent`/`imageIds` are visible to the model on follow-up turns. This closes the loop: not only model → UI (render), but UI → model (the user's in-component actions become conversational context).
- **Frontier evidence:** Verbatim methods/fields in docs. OpenAI even documents a *known bug* (issue #221: stale selection context after `ui/update-model-context`), confirming the mechanism is real and load-bearing. Shipped (beta).
- **AstralDeep gap:** AstralDeep's `component_action` re-executes a tool, but a user's *in-component selections/filters that don't trigger a tool* don't become conversational context — the next chat turn doesn't know "the user is currently looking at the Q3 tab with rows 4–6 selected." There's no UI→model state channel short of a full tool re-dispatch. This limits multi-turn flows where the user manipulates a component and then asks a follow-up ("summarize the ones I selected").
- **Priority:** UX (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Add a WS message `component_context_update {chat_id, component_id, model_context}` that the thin client emits when a user interacts with a workspace component (selection/filter/tab), carrying a small model-visible digest. The orchestrator stashes it on the chat's transient state and prepends it to the next `_call_llm` transcript as an "Active component state" block (mirroring 031's "Attachments on this turn" injection pattern). Persist alongside the component's `workspace_snapshot` so it survives reload. Reuses existing per-chat state + snapshot machinery; no new dependency.
- **Novelty 3 / Impact 4 / Effort M**

---

### F7. Responses API: server-side conversation state, hosted tools, and an internal agentic tool-loop as one primitive

- **Source:** Why we built the Responses API; Conversation state guide; Using tools. https://developers.openai.com/blog/responses-api , https://developers.openai.com/api/docs/guides/conversation-state , https://developers.openai.com/api/docs/guides/tools
- **What it is:** The Responses API replaces the flat `choices[0].message` with an ordered **`output[]` of typed items** (`message`, `reasoning`, `function_call`, `function_call_output`) and keeps conversation state server-side via **`previous_response_id`** (chains turns; OpenAI rehydrates history), **`store: true`** (30-day retention), and the **Conversations API** (`conv_…` containers, persist indefinitely, sync across devices). It runs an **internal agentic loop**: the model can invoke hosted tools (`web_search`, `file_search`, `code_interpreter`, `image_generation`, `computer_use`, `mcp`) **server-side** and report back without client round-trips. A top-level **`instructions`** field replaces the system message and is re-applied each turn (not inherited via `previous_response_id`).
- **Frontier evidence:** OpenAI reports GPT-5 scores ~5% higher on TauBench via Responses vs Chat Completions (reasoning state survives turns) and 40–80% better prompt-cache utilization (first-party blog metrics). The Assistants API is deprecated (Aug 26 2025) and sunsets Aug 26 2026 — Responses is the sanctioned successor. GA.
- **AstralDeep gap:** Architecturally AstralDeep *already is* a stateful agentic orchestrator (its orchestrator threads conversation, dispatches MCP tools, persists per-chat workspace) — so this is **largely not a gap**; AstralDeep's hand-rolled orchestrator is the equivalent of the Responses loop. The transferable ideas: (1) the **typed reasoning-item** notion — AstralDeep doesn't preserve/replay model reasoning across turns the way reasoning items do, which can improve multi-step tool reliability; (2) **explicit retention semantics** as a contract (30-day vs permanent) is cleaner than AstralDeep's implicit persistence. Flag as low-priority "already covered" with two small borrowable ideas.
- **Priority:** Novelty (secondary). (Mostly parity, not gap.)
- **How to implement in AstralDeep:** Optionally persist a compact "reasoning carryover" per turn in the chat state and replay it into the next `_call_llm` for multi-step tool tasks (bounded, opt-in), mirroring reasoning-item replay. Low priority relative to F1–F4.
- **Novelty 2 / Impact 2 / Effort M**

---

### F8. Structured Outputs / strict function calling via constrained decoding (CFG token masking → guaranteed schema conformance)

- **Source:** Introducing Structured Outputs in the API; Structured outputs guide. https://openai.com/index/introducing-structured-outputs-in-the-api/ , https://developers.openai.com/api/docs/guides/structured-outputs
- **What it is:** Set `response_format: {type:"json_schema", json_schema:{…, strict:true}}` (for responses) or `strict:true` inside a function/tool definition (for tool args). The schema is compiled into a **context-free grammar**; during sampling a grammar engine **masks every token that would violate the grammar**, so non-conforming output is *literally unsamplable* — constrained decoding, not post-hoc validation. First use of a new schema pays a one-time grammar-build latency, then caches. Requirements: `additionalProperties:false` at every object, **all properties in `required`** (optional → nullable union `["string","null"]`). Safety refusals surface as a separate **`refusal`** string field, so "model declined" is detectable without parsing.
- **Frontier evidence:** OpenAI reports **100% schema compliance** on its evals with `gpt-4o-2024-08-06` vs ~35–40% for prompt-only JSON on the same model — a hard guarantee, not "usually valid." Distinct from legacy `json_object` (syntactic validity only). GA since Aug 2024, supported on all current models.
- **AstralDeep gap:** AstralDeep runs several **JSON-out LLM loops on best-effort prompting**: the adaptive UI designer's layout-tree JSON (which already has format-retry-with-failure-fed-back logic — a workaround for exactly this problem), agentic-creation codegen scaffolding, and tool-argument generation. If AstralDeep's configured OpenAI-compatible LLM endpoint supports `response_format: json_schema`/strict tools (many do; vLLM/TGI/llama.cpp expose grammar-constrained decoding), switching these calls eliminates a whole class of malformed-JSON retries and the designer's "unusable draft JSON → format-retry" path.
- **Priority:** Novelty (primary), UX (secondary).
- **How to implement in AstralDeep:** In the `llm_config.client_factory` seam, add an optional `response_format`/`strict` passthrough so call sites can request schema-constrained output. Define a JSON schema for the UI-designer layout tree (nodes = allowed astralprims types from `webrender.allowed_primitive_types()`, leaves = `{type:"ref", component_id}`) and pass it on the designer's draft/refine calls; same for codegen's structured fields. Gracefully degrade to the current best-effort + retry path when the endpoint rejects `response_format` (capability-probe once, cache). No new third-party dependency — it's a request-field addition the existing client already round-trips.
- **Novelty 4 / Impact 4 / Effort S**

---

### F9. Agentic prompt-injection defense: dedicated monitor model (hot-patchable) + intent-alignment tool-call guardrail

- **Source:** ChatGPT Agent System Card §3.1.2.1–2. https://cdn.openai.com/pdf/839e66fc-602c-48bf-81d3-b21eacc3459d/chatgpt_agent_system_card.pdf ; Operator/CUA. https://openai.com/index/computer-using-agent/ ; open-source Guardrails (Prompt-Injection Detection check). https://github.com/openai/openai-guardrails-python ; https://guardrails.openai.com/
- **What it is:** Three-layer defense. (a) **Model-level robustness training** so the agent disregards instructions embedded in tool output / web pages. (b) A **dedicated "monitor model"** that watches the session and **pauses the task** on suspected injection — **hot-patchable with new attack signatures within hours, no retrain**. (c) Always-on classifiers scanning 100% of traffic. The open-source **Guardrails** layer adds a **Prompt-Injection Detection** check that is *agent-specific*: it validates that **a tool call aligns with the user's stated intent** (LLM-based, default `gpt-4.1-mini`, `confidence_threshold`) — e.g. blocks a `wire_money` tool call when the user only asked about the weather. A violation raises `GuardrailTripwireTriggered` and halts the run.
- **Frontier evidence:** Operator's monitor achieved **99% recall / 90% precision** on a red-team set, raised 79%→99% **in a single day** after new findings. Model-level mitigations cut injection susceptibility to 23% (vs 62% unmitigated). OpenAI candidly states prompt injection is "unlikely to ever be fully 'solved'" (defense-in-depth, not elimination). Monitor + training shipped; Guardrails open-source GA.
- **AstralDeep gap:** AstralDeep's threat model is *exactly* this — agents act under delegated tokens, tool output is untrusted, and the system is fail-closed — yet it has **no injection-monitor and no intent-alignment gate on tool calls.** It has a PHI gate and append-only audit (great for *forensics*), but nothing that *pauses a turn* when a tool's output appears to be steering the model, or that checks "does this tool call match what the user asked for" before dispatch. Given F1 (untrusted component data currently flows into the model), this is a concrete, high-value security gap.
- **Priority:** Security (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Add an orchestrator-side **intent-alignment pre-dispatch check**: before `execute_single_tool` runs a consequential tool, run a cheap bounded `_call_llm` (or rubric) that scores "does this tool+args align with the user's request this turn?"; on low confidence, pause and surface a confirmation card (reuse 027's draft-decision card surface) and emit an audit event (new `event_class` e.g. `tool_intent_gate`). Separately, a lightweight **injection monitor** can scan tool *output* (and any fetched web content, e.g. web_research's `fetch_page`) for instruction-like patterns before it enters the next LLM turn, dropping/flagging and auditing. Both are Python + existing `_call_llm` + existing audit infra — no new dependency. Pairs naturally with F1 (digest-only model exposure).
- **Priority secondary note:** Most novel within AstralDeep's security model precisely because its delegation/audit posture is already strong but *reactive*; this adds a *preventive* layer.
- **Novelty 4 / Impact 5 / Effort M**

---

### F10. Computer-Use Agent (CUA): screenshot→reason→action loop with API-level safety-check acknowledgement (`pending_safety_checks` → `acknowledged_safety_checks`)

- **Source:** Computer-Using Agent. https://openai.com/index/computer-using-agent/ ; computer-use tool guide. https://developers.openai.com/api/docs/guides/tools-computer-use ; safety-check contract (verbatim mirror). https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/computer-use
- **What it is:** A multimodal loop — raw **screenshots** are the visual state, the model **reasons** over current+prior frames (an "inner monologue"), and emits coordinate-based **actions** (`click`, `double_click`, `scroll`, `type`, `keypress`, `drag`, `move`, `wait`, `screenshot`); the developer executes the action, captures a fresh screenshot, returns it as `computer_call_output`, repeat. Each turn the API may attach **`pending_safety_checks`** (codes: `malicious_instructions`, `irrelevant_domain`, `sensitive_domain`) that the developer **must echo back as `acknowledged_safety_checks`** before the model proceeds — a forced human-/policy-in-the-loop gate baked into the API contract.
- **Frontier evidence:** SOTA at launch (OSWorld 38.1%, WebArena 58.1%, WebVoyager 87%); OpenAI candidly notes 38.1% means "not yet highly reliable." `computer-use-preview` model: **research preview** as of June 2026 (snapshot `computer-use-preview-2025-03-11`, $3/$12 per 1M tokens, tiers 3–5). Consumer Agent mode (merged into ChatGPT, GA).
- **AstralDeep gap:** AstralDeep has **no computer-use / browser-automation capability** at all — its agents call MCP tools, not GUIs. This is a large capability gap but **only partially in scope**: AstralDeep's value is structured tool agents, not pixel automation. The portable, in-scope idea is the **`pending_safety_checks` → `acknowledged_safety_checks` pattern**: a *forced, typed, must-acknowledge safety gate embedded in the dispatch contract* (not a side audit), with named risk codes (off-task domain, sensitive target, adversarial content). AstralDeep's permission overrides are static allow/deny; CUA's per-call dynamic safety codes are a more expressive model.
- **Priority:** Security (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Don't build computer-use. Do adopt the **acknowledgement-gate contract** for consequential tool dispatch: extend the MCP dispatch envelope so a tool (or the orchestrator's gate) can return `pending_safety_checks: [{id, code, message}]` with codes like `sensitive_scope`, `off_request`, `untrusted_input`; the orchestrator refuses to proceed until the user (or an admin, for global tools) returns `acknowledged_safety_checks` via a confirmation card. This generalizes 027's approval cards into a typed, reusable per-call safety protocol and writes through the existing audit chain. No new dependency.
- **Novelty 3 / Impact 4 / Effort M**

---

### F11. Realtime API: single speech-to-speech model with semantic-VAD turn detection and barge-in

- **Source:** Introducing gpt-realtime; Realtime conversations guide. https://openai.com/index/introducing-gpt-realtime/ , https://developers.openai.com/api/docs/guides/realtime-conversations
- **What it is:** A **single end-to-end speech-to-speech model** (no STT→LLM→TTS pipeline) ingesting and emitting audio directly, preserving prosody and cutting latency. Transports: **WebRTC** (browser media), **WebSocket** (JSON event protocol), **SIP** (telephony). Turn detection is configurable: **`server_vad`** (audio-energy endpointing) or **`semantic_vad`** (the model decides when the user is *semantically* finished — fewer premature cut-ins), or `null` for push-to-talk. **Barge-in**: WebRTC/SIP auto-truncate unplayed assistant audio on interruption; WebSocket clients send `conversation.item.truncate`.
- **Frontier evidence:** **GA Aug 28 2025** (`gpt-realtime`, replacing the 2024 preview). Scored 82.8% on Big Bench Audio (vs 65.6% preview); companion transcription ~90% fewer hallucinations than Whisper v2 (first-party). Voices `marin`, `cedar`.
- **AstralDeep gap:** AstralDeep has a **VOICE device target in ROTE** (it adapts components to voice) but **no real-time bidirectional voice transport** — it's text-render-adapted-for-voice, not speech-in/speech-out. There's no WebRTC/WebSocket-audio path, no turn detection, no barge-in. This is the biggest *interaction-modality* gap.
- **Priority:** UX (primary), Device (secondary).
- **How to implement in AstralDeep:** This is genuinely Large and brushes the "no new third-party runtime libraries" constraint (a realtime audio path typically needs a media stack). The *constraint-respecting* path: keep ROTE's voice target for output adaptation, and treat speech-to-speech as a **future bridge to an external realtime provider** rather than something built in-process. The portable, buildable-now ideas are the **`semantic_vad` turn-detection concept** and **async-function-call-with-placeholder** (F12) — these can inform AstralDeep's text-turn handling (e.g., "is the user done?" gating) without an audio stack. Flag the full voice transport as out-of-constraint for now.
- **Novelty 4 / Impact 3 / Effort L**

---

### F12. Realtime async function calling with placeholders + mid-session image input

- **Source:** Realtime conversations guide; Introducing gpt-realtime. https://developers.openai.com/api/docs/guides/realtime-conversations , https://openai.com/index/introducing-gpt-realtime/
- **What it is:** During a live voice session, the model can **call functions asynchronously** — the conversation keeps flowing while a tool runs, and the API inserts **automatic placeholders** so the model doesn't hallucinate a result before the tool returns. The GA model also accepts **image input mid-session** (`input_image` on a conversation item — a voice agent can "look at" a screenshot while talking) and supports **remote MCP servers** in-session. Highest-scoring model on ComplexFuncBench for multi-step function calling (first-party).
- **Frontier evidence:** Async function calling + image-in-session are GA-only features added at the Aug 2025 launch (absent from the 2024 beta). GA.
- **AstralDeep gap:** Beyond the (out-of-scope) audio aspect, the **async-tool-with-placeholder** pattern is directly relevant to AstralDeep's long-running jobs: AstralDeep already auto-posts long-running job progress to chat (recent commits), but the model's *turn* blocks on tool completion. A placeholder-while-running contract (the model continues the conversation, the result streams in) would improve perceived latency for slow agents.
- **Priority:** UX (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Generalize the existing job-auto-post mechanism into a **non-blocking tool-call contract**: when an agent tool is known-slow, the orchestrator returns a placeholder component immediately (component identity reserved via the workspace upsert), lets the chat turn continue, and updates the component in place via `ui_upsert` when the result lands — exactly the F2 in-place-update path, applied to async tools. Pairs with 014 progress notifications + the recent job-progress-autopost work. No new dependency.
- **Novelty 3 / Impact 3 / Effort M**

---

### F13. AgentKit / Agents SDK: handoffs, sessions, and tripwire guardrails as a composable orchestration contract

- **Source:** OpenAI Agents SDK docs. https://openai.github.io/openai-agents-python/handoffs/ , https://openai.github.io/openai-agents-python/sessions/ , https://openai.github.io/openai-agents-python/guardrails/ ; AgentKit announcement. https://openai.com/index/introducing-agentkit/
- **What it is:** Code-first multi-agent framework. **Handoffs**: one agent delegates to another *represented as a tool* (auto-named `transfer_to_<agent>`), via `handoff()` with `input_type` (structured handoff payload), `input_filter` (control what history the receiver sees), `on_handoff` callback. **Sessions**: auto-manage history across runs via a 4-method protocol (`get_items`/`add_items`/`pop_item`/`clear_session`) with pluggable backends incl. `EncryptedSession`. **Guardrail tripwires**: `@input_guardrail`/`@output_guardrail` return `GuardrailFunctionOutput(tripwire_triggered=bool)`; a trip **halts the run** (parallel vs blocking mode = latency/cost trade-off); plus tool-level `@tool_input_guardrail`/`@tool_output_guardrail` with `.allow()`/`.reject_content()`. **Agent Builder** is a visual canvas over the same primitives with node types incl. **User Approval** (human-in-the-loop pause) and **Guardrails**.
- **Frontier evidence:** OpenAI's sanctioned successor to Swarm; core primitives GA-grade (no beta markers). Agent Builder beta (Oct 2025). Ramp built a months-long workflow "in a couple of hours" (vendor metric).
- **AstralDeep gap:** AstralDeep's orchestrator routes user→agent but has a **flatter delegation model** — it doesn't expose *agent-to-agent handoffs as first-class tools with input-filtering* (controlling exactly what context a downstream agent sees), nor a formal *tripwire that halts a turn* on an output-guardrail (the closest is fail-closed gates + audit). The **`input_filter` on handoff** is the most novel idea: deliberately attenuating the *conversational context* passed to a downstream agent (not just the *token scope*) — a context-minimization analog to AstralDeep's RFC 8693 scope attenuation.
- **Priority:** Security (primary), Novelty (secondary).
- **How to implement in AstralDeep:** (1) Add **agent-handoff-as-tool**: let an agent's MCP tool list include a `handoff_to(agent_id, structured_payload)` that the orchestrator dispatches with an explicit `context_filter` controlling which transcript/workspace slices the receiver sees — extending the existing delegated-token attenuation with *context* attenuation. (2) Add a formal **output-tripwire** hook on tool results (a guardrail fn that can `halt`/`reject_content`), wired into `execute_single_tool` and audited — generalizing the PHI gate into a pluggable tripwire registry. Both are Python + existing delegation/audit; no new dependency.
- **Novelty 3 / Impact 4 / Effort M**

---

### F14. ChatGPT Pulse: proactive, asynchronous, card-grid generative surface (non-conversational)

- **Source:** Introducing ChatGPT Pulse. https://openai.com/index/introducing-chatgpt-pulse/ ; Pulse help. https://help.openai.com/en/articles/12293630-chatgpt-pulse
- **What it is:** A surface where ChatGPT does **asynchronous research overnight (once/day)** drawing on **past chats, memory, feedback, and connected apps (Gmail, Google Calendar — opt-in, off by default)**, then delivers results the next morning as **a series of visual summary cards you can scan, expand, save, or ask follow-ups against** — a non-conversational, card-grid *generative layout* distinct from the chat stream. A curation loop (mark useful/not) steers future research. Requires memory ON.
- **Frontier evidence:** Launched Sept 2025, **Pro-tier preview first** (web/iOS/Android). Anticipatory-personalization framing is partly marketing, but the overnight-research → morning-card-grid delivery is concrete. Preview.
- **AstralDeep gap:** AstralDeep has the *substrate* for this — cross-session memory items, short-term signals, personalization, scheduled jobs, consolidation sweeps ("dreaming"), and per-turn workspace snapshots — but **no proactive non-conversational card surface**: there's no "here's a grid of cards we generated for you overnight from your memory + jobs" view. AstralDeep's outputs are all *in-chat*. A Pulse-like surface would turn its memory/dreaming machinery into a visible daily product.
- **Priority:** UX (primary), Novelty (secondary).
- **How to implement in AstralDeep:** Add a **proactive digest chrome surface** (a new `webrender/chrome/surfaces/` module, server-rendered like the workspace timeline) that renders a grid of astralprims Cards/Hero/MetricCard produced by a scheduled "dreaming" sweep over memory + recent jobs + short-term signals. Reuse: 030's consolidation/dreaming jobs to *generate* the cards (write them as components into a dedicated daily snapshot), the scheduler to run it overnight, and the existing card primitives + ROTE to render/adapt. Curation feedback rides the 004 feedback infra. Entirely within constraints — it's composition of existing subsystems.
- **Novelty 4 / Impact 4 / Effort M**

---

### F15. Tasks: model-scheduled recurring automations created conversationally, with push/email delivery

- **Source:** Scheduled tasks in ChatGPT. https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
- **What it is:** ChatGPT can **create tasks that run automated prompts on a schedule (one-off or recurring) and proactively reach out**, executing whether or not the user is online. Tasks are created **conversationally** — the user states intent + timing ("every weekday at 9am, summarize the top 3 headlines with source links") and **confirms the schedule ChatGPT proposes**. Completion is delivered via **push notification or email**; a hard limit of **10 active tasks**; management is web-only.
- **Frontier evidence:** Beta (launched Jan 2025), broadly available on paid tiers. Concrete: conversational creation + proposed-schedule confirmation + push/email fan-out.
- **AstralDeep gap:** AstralDeep has `scheduled_job`/`job_run` and recently added long-running-job auto-post-to-chat — so the *scheduling substrate* exists — but two gaps: (1) **conversational task creation with a model-proposed schedule + explicit user confirmation** isn't a first-class flow (jobs appear to be configured more directly), and (2) **no native push/email delivery channel** — results land in chat, not as an OS push. The confirmation-of-proposed-schedule UX is the novel, low-cost piece.
- **Priority:** UX (primary), Novelty (secondary).
- **How to implement in AstralDeep:** (1) Add an orchestrator meta-flow (like 027's `create_capability`) `schedule_task` that, from a NL request, has the model *propose* a cron + prompt, renders a confirmation card (reuse approval-card surface), and on accept writes a `scheduled_job`. (2) For delivery, since "no new runtime libraries," use **email via the existing egress-gated `shared.external_http`** (SMTP-over-HTTP API or an existing mail relay) rather than adding a push SDK; reserve true web-push as a thin-client `Notification`/service-worker addition (no backend dependency). Both reuse the scheduler + chrome surfaces. PushNotification is also available as a harness tool for dev/testing.
- **Novelty 3 / Impact 3 / Effort M**

---

### F16. ChatGPT Projects: grouped chats with shared files, instructions, and *scoped* memory boundary

- **Source:** Projects in ChatGPT. https://help.openai.com/en/articles/10169521-projects-in-chatgpt ; more ways to work with your team. https://openai.com/index/more-ways-to-work-with-your-team/
- **What it is:** A workspace grouping chats + uploaded reference files + custom instructions, with **project-scoped memory**: ChatGPT draws context **only from conversations within that project**, not from the user's other projects or global account memory — a self-contained context boundary. Shared/collaborative Projects let multiple members work from the same files/instructions/history with real-time updates.
- **Frontier evidence:** GA; shared/team Projects rolled out broadly 2025 (Free/Plus/Pro/Go, web/iOS/Android). The explicit **memory-scoping boundary** ("delete or move a chat out to exclude it from project memory") is a concrete primitive.
- **AstralDeep gap:** AstralDeep's memory ("soul") appears **global per user** (cross-session memory items, personalization) with per-*chat* workspace persistence, but there's no **project/workspace-scoped memory boundary** — no way to say "this group of chats shares files + instructions + a *memory namespace* isolated from my other work." For a multi-context user (e.g., separate research areas), global memory bleeds context across domains. This is a memory-architecture gap, not a UI one.
- **Priority:** Novelty (primary), UX (secondary).
- **How to implement in AstralDeep:** Introduce a `project_id` scoping dimension on memory items / short-term signals / personalization (idempotent `_init_db` column add per the migration constraint) and a chrome surface to group chats into a project with shared instruction text + attached files. Memory reads/consolidation ("dreaming") filter by the active project namespace; global memory remains the default namespace. Reuses 028 workspace + 030 memory subsystems; the new piece is the namespace key. No new dependency.
- **Novelty 3 / Impact 4 / Effort M**

---

### F17. Native in-chat interactive data UI (model-emitted tables + manipulable charts) — first-party, not via Apps SDK

- **Source:** Improvements to data analysis in ChatGPT. https://openai.com/index/improvements-to-data-analysis-in-chatgpt/ ; Data analysis help. https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt
- **What it is:** Beyond canvas/Apps, ChatGPT's first-party data path **emits interactive UI directly**: an uploaded file auto-creates an **interactive table** (scroll, expand fullscreen, live-updates as analysis runs) and answers can become **interactive bar/line/pie/scatter charts rendered in-conversation** — hover for values, ask follow-ups against the chart, recolor (palettes or hex), toggle interactivity. The model decides when a visualization is useful and emits it.
- **Frontier evidence:** GA (2024–2025, web + mobile). Broad chart vocabulary (line, bar, pie, histogram, scatter, box, heatmap, area, radar, treemap, bubble, waterfall). This is a native precedent for **model-emitted adaptive widgets** — close to AstralDeep's astralprims model.
- **AstralDeep gap:** This is the area where **AstralDeep is closest to parity or ahead** — it already has Chart/Table/MetricCard primitives, model-driven emission, and an adaptive designer. The borrowable specifics: (1) **manipulable charts** (hover/recolor/ask-against-the-chart) — AstralDeep's charts are likely static renders; (2) the **breadth of chart types** (heatmap/treemap/radar/waterfall/box) — a checklist for astralprims coverage; (3) **chart-as-conversational-referent** (ask a follow-up scoped to a chart) — which ties to F6 (component→model context). Mostly a *polish/coverage* gap, not architectural.
- **Priority:** UX (primary), Device (secondary).
- **How to implement in AstralDeep:** Audit astralprims Chart coverage against OpenAI's vocabulary and add missing types (heatmap/treemap/radar/waterfall/box) as renderer-registry entries (the 029 pattern: class in astralprims, renderer in `webrender/renderer.py`, styles in `astral.css`, voice extraction in `rote/adapter.py`). Add lightweight client-side chart interactivity (hover tooltips, recolor) in the no-build client, and wire "ask about this chart" through the F6 component-context channel. No new dependency.
- **Novelty 2 / Impact 3 / Effort M**

---

## Sources

**OpenAI — Apps SDK (fetched cleanly; highest-confidence mechanism detail):**
- https://developers.openai.com/apps-sdk/build/chatgpt-ui
- https://developers.openai.com/apps-sdk/build/mcp-server
- https://developers.openai.com/apps-sdk/build/state-management
- https://developers.openai.com/apps-sdk/concepts/design-guidelines
- https://developers.openai.com/apps-sdk/reference
- https://developers.openai.com/apps-sdk/plan/components
- https://developers.openai.com/apps-sdk/deploy/troubleshooting
- https://developers.openai.com/apps-sdk/app-submission-guidelines
- https://openai.com/index/introducing-apps-in-chatgpt/
- https://openai.com/index/developers-can-now-submit-apps-to-chatgpt/

**OpenAI — Platform APIs (Responses, Structured Outputs, Realtime, multimodal):**
- https://developers.openai.com/blog/responses-api
- https://developers.openai.com/api/docs/guides/migrate-to-responses
- https://developers.openai.com/api/docs/guides/conversation-state
- https://developers.openai.com/api/docs/guides/tools
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://openai.com/index/introducing-structured-outputs-in-the-api/
- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://developers.openai.com/api/docs/guides/realtime-webrtc
- https://developers.openai.com/blog/realtime-api
- https://openai.com/index/introducing-gpt-realtime/
- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/reference/resources/images/generation-streaming-events
- https://openai.com/index/new-tools-and-features-in-the-responses-api/

**OpenAI — Agents / AgentKit / Guardrails / computer-use:**
- https://openai.com/index/introducing-agentkit/
- https://openai.github.io/openai-agents-python/handoffs/
- https://openai.github.io/openai-agents-python/sessions/
- https://openai.github.io/openai-agents-python/guardrails/
- https://openai.github.io/openai-agents-python/tools/
- https://github.com/openai/openai-guardrails-python
- https://guardrails.openai.com/
- https://platform.openai.com/docs/guides/agent-builder
- https://openai.com/index/computer-using-agent/
- https://developers.openai.com/api/docs/guides/tools-computer-use
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- https://github.com/openai/openai-cua-sample-app

**OpenAI — ChatGPT product surfaces (Canvas, GPTs, Pulse, Tasks, Projects, data UI, memory, voice):**
- https://openai.com/index/introducing-canvas/
- https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it
- https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt
- https://help.openai.com/en/articles/8554397-creating-and-editing-gpts
- https://help.openai.com/en/articles/8908924-what-is-the-mentions-feature-for-gpts
- https://openai.com/index/introducing-chatgpt-pulse/
- https://help.openai.com/en/articles/12293630-chatgpt-pulse
- https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
- https://help.openai.com/en/articles/10169521-projects-in-chatgpt
- https://openai.com/index/more-ways-to-work-with-your-team/
- https://openai.com/index/improvements-to-data-analysis-in-chatgpt/
- https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt
- https://openai.com/index/memory-and-new-controls-for-chatgpt/
- https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work
- https://help.openai.com/en/articles/8400625-voice-mode-faq

**OpenAI — system cards / governance PDFs (read directly on cdn.openai.com):**
- https://cdn.openai.com/operator_system_card.pdf
- https://cdn.openai.com/pdf/839e66fc-602c-48bf-81d3-b21eacc3459d/chatgpt_agent_system_card.pdf
- https://cdn.openai.com/pdf/18a02b5d-6b67-4cec-ab64-68cdfbddebcd/preparedness-framework-v2.pdf
- https://openai.com/index/updating-our-preparedness-framework/
- https://openai.com/index/hardening-atlas-against-prompt-injection/

**Corroborating / contract-mirror secondary (used where official pages 403'd; flagged in-text):**
- https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/computer-use
- https://deepwiki.com/openai/openai-apps-sdk-examples/4.2-window.openai-api-reference
- https://community.openai.com/t/apps-sdk-state-management-flaws/1371808
- https://github.com/openai/openai-apps-sdk-examples/issues/221
