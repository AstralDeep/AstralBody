# Device adaptation & cross-surface UI literature — findings

> Literature review (2023–2026, with seminal SDUI/plasticity anchors as foundation)
> of **device adaptation, cross-surface UI distribution, multimodal/voice & screenless
> rendering, on-device/edge LLM inference & compute placement, AR/spatial & TV UI,
> context-aware adaptation, and server-driven UI at industry scale**, mapped to GAPS
> in **AstralBody's ROTE** middleware.
>
> AstralBody today: server-driven UI (astralprims defines → orchestrator renders →
> ROTE adapts) where **ROTE is a one-shot server-side transform keyed on a coarse
> device type** (BROWSER passthrough, TABLET, MOBILE, WATCH, TV, VOICE). The client
> sends device capabilities once in `register_ui`; VOICE = text extraction only; no
> live viewport/theme feedback, no compute-placement decisions, no true voice/AR/TV
> renderers. Adding a new target = add an orchestrator renderer (no primitive change).
>
> Constraints honored throughout: **Python backend only, NO new third-party runtime
> libraries**, the SDUI mandate is constitutional, new client target = new renderer.
> Priority lens (in order): **Novelty (paramount) > UX > device adaptation (this is
> the device-priority review) > agentic security.** Each finding carries
> Novelty 1–5 / Impact 1–5 / Effort S/M/L. Demonstrated vs speculative is flagged.

## Executive summary

- **ROTE's biggest structural gap is capability *negotiation*.** Industry SDUI at scale (Airbnb Ghost Platform, Lyft, Netflix MSL, Spotify Hub) is built on the client *declaring which component/section types it can render* and the server returning only those, with explicit *fallback/skip* for unknowns and *versioned* component contracts. AstralBody sends device caps once but ROTE never negotiates a per-client *renderer vocabulary* nor degrades gracefully on a missing renderer — it should publish a capability set and contract-version per target and filter the render to it (F1, F2, F3).
- **Adaptation should be a *declarative multi-objective optimization*, not a per-type code branch.** AUIT (UIST'22) shows adaptation expressed as weighted *objectives* solved at runtime, and SituationAdapt (UIST'24) extends it with an **LLM/VLM that scores placement suitability** (functionality/aesthetics/social/safety) feeding the cost function. This is the principled successor to ROTE's hard-coded transforms and reuses AstralBody's existing `_call_llm` seam — zero new deps (F4, F5).
- **VOICE today is text extraction; the frontier is *structured auditory rendering*.** Chart Reader (CHI'23), MAIDR & Spatial-Audio graph rendering (CHI'24) show data/tables/charts get *hierarchical navigable structure + non-speech audio (sonification/earcons) + tiered verbosity*, not flat narration. A real VOICE renderer should emit SSML + navigable structure + earcon cues from astralprims types — a new orchestrator renderer, exactly the SDUI-sanctioned extension point (F6, F7).
- **Compute placement (which model runs where) is missing entirely.** Edge-SLM↔cloud-LLM routing/cascade literature (HybridLLM, CITER, FrugalGPT, Tabi, FS-GEN) routes *per request* by a cheap quality/latency/energy predictor, escalating only on low confidence. ROTE knows the device but never uses it to pick a model tier — a device-capability-aware *model router* in front of `llm_config.client_factory` is a near-free latency/cost/privacy win (F8, F9).
- **Context beyond device type is unused.** IMWUT/UbiComp context-aware UI + interruptibility, and SituationAdapt's situation-awareness, show layout should react to *attention/interruptibility/environment* signals the client could send in `register_ui` (and update live). ROTE has no live viewport/theme/ambient feedback loop (F10, F11).
- **Cross-surface *distribution* (one session, many devices) is unexplored.** Vulture (INFOCOM'24, fine-grained GUI distribution) + CAMELEON/plasticity foundations show a workspace can span watch+phone+TV with components migrating. AstralBody's per-component `workspace_layout` overlay model is unusually well-positioned to distribute *components* across a user's simultaneous device sockets (F12, F13).
- **Accessibility should be a *generation/render constraint*, not an afterthought.** W4A'25 + AccessGuru show LLM-generated UI systematically violates WCAG (contrast, semantics, focus) unless constraints are injected and auto-validated. ROTE renders to HTML and runs LLM design loops — it can enforce WCAG at render time and gate the UI-designer's output (F14, F15).
- **Progressive disclosure / level-of-detail is the unifying device knob.** A tiered content model (index → summary → full) lets one component degrade from TV (large/sparse) to WATCH (glanceable) to VOICE (TL;DR) deterministically — generalizing the existing per-device transform into a principled LoD ladder (F16, F17).
- **TV/10-foot needs focus-graph metadata, not just bigger fonts.** A real TV renderer requires server-emitted spatial-navigation order (D-pad reachability + focus model), which astralprims components can carry as render hints without primitive changes (F18).

---

## Findings

### F1. Capability-negotiated component contracts (client declares its renderer vocabulary)
- **Source**: *A Deep Dive into Airbnb's Server-Driven UI System* — Ryan Brooks, **Airbnb Tech Blog**, 2021 (canonical; still the reference architecture). https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5 — plus *Server-Driven UI strategies*, **MobileNativeFoundation discussion #47**, 2023–24. https://github.com/MobileNativeFoundation/discussions/discussions/47
- **What it is**: Airbnb's "Ghost Platform" keys rendering on a `SectionComponentType` (a rendering instruction) carried in a `SectionContainer` with status/logging metadata; a single data model can render multiple ways via different component types. Across the broader industry pattern, **the client declares which section/component types it can render and the server returns only those**, so the server evolves without breaking older clients; unknown types are *skipped or replaced with a generic placeholder*.
- **Frontier evidence**: Ghost's shared GraphQL schema generates strongly-typed section models across Web/iOS/Android; Search composes ~50 section types with lazy-loaded server-driven rendering and nightly UI experiments — demonstrated at Airbnb scale.
- **AstralBody gap**: ROTE knows a device *type* but has no notion of a per-target *renderer vocabulary*. `webrender.allowed_primitive_types()` (31 types) is a single global palette, not negotiated per client. If a target (e.g. WATCH/VOICE) can't render `timeline` or `chart`, ROTE has no contract-level "skip/placeholder/substitute" rule — it ships whatever the global renderer emits.
- **Priority**: P1 (foundational; unlocks F2/F3/F6/F18).
- **How to implement in AstralBody**: Have each `webrender.register_target(...)` publish a **declared capability set** (the subset of `allowed_primitive_types()` it renders) and a **contract version**. Extend the existing `register_ui` device payload with a `supported_primitives`/`renderer_version` echo (additive; default = full palette for legacy). In ROTE, before adaptation, **filter/substitute** any component whose type isn't in the target's set: deterministic fallback ladder (e.g. `timeline`→`list`, `chart`→`table`→`text`). Pure Python; reuses the registry already in place. No primitive change.
- **Novelty 4 / Impact 5 / Effort M**

### F2. Versioned layout schemas + graceful degradation for safe rollouts
- **Source**: *Server-Driven UI in 2025: Versioned Layout Schemas, Capability Negotiation, Safe Mobile Rollouts* — **debugg.ai engineering**, 2025. https://debugg.ai/resources/server-driven-ui-2025-versioned-layout-schemas-capability-negotiation-safe-mobile-rollouts (article + corroborated by MobileNativeFoundation #47).
- **What it is**: Production SDUI in 2025 wraps the layout payload in a **schema version**; the server checks the client's version and emits only components that version supports; **unknown components trigger a defined fallback** (skip vs generic placeholder). Server-side flags drive A/B and staged rollout so a bad layout is contained without an app release.
- **Frontier evidence**: This is the converged industry pattern across Airbnb/Lyft/Netflix mobile teams — versioned contracts + capability negotiation are described as the prerequisite for safe rollouts; the alternative (un-versioned) is what makes SDUI brittle.
- **AstralBody gap**: `ui_render`/`ui_upsert` payloads carry no schema version. When astralprims adds primitives (the 0.2.0 dashboard set already created a 31-type registry mid-stream — agents emit them as plain dicts "until the wheel is in the image"), there is no contract negotiation: an older renderer target silently mis-handles a newer component.
- **Priority**: P1.
- **How to implement**: Add an additive `schema_version` to `ui_render`/`ui_upsert` and a per-target `min/max` it understands; ROTE down-renders or placeholders components above the target's max. Wire AstralBody's existing **`FF_*` flag** machinery to gate new-primitive emission per target (server-side A/B already implicit in the feature-flag system). Persist nothing new beyond a version constant. Constitution-clean (idempotent, additive).
- **Novelty 3 / Impact 4 / Effort S**

### F3. Component-as-contract with co-located fallback + server-owned actions (Lyft/Spotify/Netflix)
- **Source**: *spotify/HubFramework* (component-driven UI, README) — **Spotify**, 2016–2018 (deprecated, but the contract design is instructive). https://github.com/spotify/HubFramework — plus Lyft/Netflix MSL patterns summarized in MobileNativeFoundation #47 (2023–24) and the Netflix architecture reverse-engineering gist (search capability negotiation), 2024. https://gist.github.com/sshh12/dda3a89514f850c459380b18b1f7eb7b
- **What it is**: Hub models a screen as reorderable *components*, each a rectangle that renders from local code *or* backend JSON, aggregating multiple sources; Lyft's lesson is to **name components after the product meaning, not the layout**, and keep all business logic server-side (the client stays "dumb"). Netflix's MSL negotiates capability per client. Hub's deprecation is itself a finding: a component framework that over-abstracts without clear value gets cut.
- **Frontier evidence**: Hub shipped Browse/Running/Party/Genre in production Spotify iOS; Lyft/Netflix run the same server-owns-logic, client-renders pattern at scale. Demonstrated.
- **AstralBody gap**: astralprims components *are* server-owned (good), but there's no notion of a per-component **fallback contract** (what to render if a target can't handle me) co-located with the component, and component identity is fingerprint/`wc_*`-based rather than semantic. The "name after product not layout" lesson is relevant to how garnish/`dg_*` ids and component identities are assigned.
- **Priority**: P2.
- **How to implement**: Let each astralprims type (or its renderer entry) declare a **`fallback_type`** chain consumed by ROTE (F1's ladder, but authored once at the component/renderer level rather than hard-coded in ROTE). Keep AstralBody's existing identity model; add only the fallback metadata as a renderer-registry field. No primitive class change required (renderer-side).
- **Novelty 3 / Impact 4 / Effort M**

### F4. Declarative multi-objective UI adaptation (objectives + runtime solver, not code branches)
- **Source**: *AUIT — the Adaptive User Interfaces Toolkit for Designing XR Applications* — Belo, Lystbæk, Feit, Pfeuffer, Kán, Oulasvirta, Grønbæk. **UIST 2022**. https://dl.acm.org/doi/10.1145/3526113.3545651
- **What it is**: Instead of rules/scripts, the designer specifies **adaptation objectives** (reachability, visibility, consistency, distance, field-of-view, constant-size…), and a **multi-objective solver finds the adaptation in real time** as weighted cost terms `Q = ΣΣ w·c(x)`. Adaptation becomes a search over a configuration, not a branch per device.
- **Frontier evidence**: AUIT demonstrably lets non-expert XR creators compose adaptation policies and get real-time layouts; it is the toolkit SituationAdapt builds directly on (F5), evidencing reuse/generality.
- **AstralBody gap**: ROTE is exactly the rules/scripts approach AUIT argues against — a per-device-type transform branch. There is no objective model (e.g. "fit-to-width", "minimize taps", "glanceability", "speakability") nor a solver selecting among arrangement options; the adaptive **UI-designer** (`ui_designer.py`) optimizes *arrangement* but is device-blind (it never sees the target's constraints).
- **Priority**: P1 (highest-novelty restructuring of ROTE).
- **How to implement**: Recast per-device adaptation in `rote/adapter.py` as a tiny **weighted-objective scorer** over a small candidate set of arrangements/LoD levels per component (objectives: width-fit, interaction-cost, glanceability, speakability, info-density — each a pure-Python cost from device caps + component metadata). Pick the min-cost rendering. Crucially, **feed the connecting target's objective weights into the existing UI-designer loop** so its LLM arrangement pass is device-aware (e.g., WATCH weights glanceability high → fewer, larger refs). Pure Python; no solver lib needed (small discrete search). No primitive change.
- **Novelty 5 / Impact 5 / Effort L**

### F5. LLM/VLM-scored placement suitability feeding the adaptation cost (situation awareness)
- **Source**: *SituationAdapt: Contextual UI Optimization in Mixed Reality with Situation Awareness via LLM Reasoning* — Li, Zhipeng et al. **UIST 2024**. https://dl.acm.org/doi/10.1145/3654777.3676470 / https://arxiv.org/abs/2409.12836
- **What it is**: A perception→reasoning→optimization pipeline where a **VLM (GPT-4V, few-shot, human-rated exemplars in context) scores UI placement on four FASH factors — Functionality, Aesthetics, Social acceptability, Health & safety** — producing *overlay-suitability* and *interaction-suitability* scores that become **cost terms** in the AUIT optimizer (ray-cast penalties, interaction-frequency weighting). It chooses layouts that don't obstruct objects or violate social norms.
- **Frontier evidence**: VLM scores aligned with human raters with *lower variance* (SD 1.18 vs 1.72 overlay; p<0.04), and in a within-subjects study (N=12) SituationAdapt **significantly beat UserCentric and SurfaceAdapt** on overlay & interaction suitability (p<0.0001) and was ranked first by every participant. Demonstrated.
- **AstralBody gap**: ROTE never reasons about *whether* a given rendering is appropriate for the context — it transforms structurally and stops. AstralBody already has the `_call_llm` seam and an LLM design loop, but neither scores device/context-appropriateness of an arrangement.
- **Priority**: P1.
- **How to implement**: In the F4 scorer, optionally add an **LLM-judged suitability cost** for hard/ambiguous cases (mirrors how `ui_designer.py` already calls the LLM, gated by `FF_UI_DESIGNER`, with a per-pass timeout and fail-open): prompt the existing client with the device profile + a structural sketch of the candidate arrangement and a small rubric (readability, interaction-cost, speakability, info-overload) → numeric scores feed the cost. Cache by `(target, arrangement-fingerprint)`. Bounded, fail-open to the deterministic F4 cost. Zero new deps.
- **Novelty 5 / Impact 4 / Effort M**

### F6. Structured non-visual (auditory) rendering: navigable structure + tiered verbosity + sonification
- **Source**: *Chart Reader: Accessible Visualization Experiences Designed with Screen Reader Users* — **CHI 2023**. https://dl.acm.org/doi/full/10.1145/3544548.3581186 — and *MAIDR: Making Statistical Visualizations Accessible with Multimodal Data Representation*, **CHI 2024**.
- **What it is**: Chart Reader found screen-reader users split into **three comprehension strategies** — (a) rich *textual descriptions*, (b) *structural interrogation* of chart/data (navigate axes→series→points), and (c) perceiving trends via **non-speech audio**. Accessible rendering therefore needs a *navigable hierarchical structure* + *tiered text verbosity* + *sonification*, not a single flat caption. MAIDR generalizes this to a multimodal representation across chart types.
- **Frontier evidence**: Both are CHI full papers grounded in studies with blind/low-vision screen-reader users; they define concrete interaction models (hierarchical navigation, drill-down, audio mapping). Demonstrated.
- **AstralBody gap**: The **VOICE target is "spoken-friendly text extraction"** only — flat narration, no navigable structure, no audio cues, no per-component verbosity tiers. astralprims `table`/`chart`/`timeline`/`keyvalue` collapse to prose.
- **Priority**: P1 (the single most under-built target; pure-novelty for an agentic SDUI platform).
- **How to implement**: Build a real **VOICE renderer** (`webrender.register_target("VOICE", …)`) that maps each astralprims type to a *structured auditory tree*: SSML with headings/landmarks, a navigable outline (axis→series→point for charts, header→rows for tables), **three verbosity tiers** (TL;DR / key points / full — AstralBody already produces TL;DR/Key-points/Quotes tabs in the summarizer agent, reuse that LoD habit), and deterministic **earcon markers** (text tokens the device maps to non-speech cues, e.g. `[earcon:up]` for an upward trend computed server-side). All server-side string/markup generation in Python — no audio library, no new dep. New renderer = SDUI-sanctioned.
- **Novelty 5 / Impact 5 / Effort M**

### F7. Sonification / spatial-audio data trends + touch exploration for screenless data
- **Source**: *Spatial Audio-Enhanced Multimodal Graph Rendering for Efficient Data Trend Learning on Touchscreen Devices* — **CHI 2024**. https://dl.acm.org/doi/10.1145/3613904.3641959 — and *ChartA11y: Accessible Touch Experiences of Visualizations with Blind Smartphone Users* (2024). https://arxiv.org/html/2410.20545v1
- **What it is**: Encodes data **trends as audio** (pitch ↔ value, pan/spatialization ↔ position) combined with touch exploration, so a user perceives shape/trend without sight. Establishes concrete value→sound mappings and that *trend comprehension* improves with spatialized audio vs speech alone.
- **Frontier evidence**: CHI 2024 study shows efficiency gains for data-trend learning with spatial audio over speech-only on touchscreens. Demonstrated.
- **AstralBody gap**: No notion of conveying *trend/shape* of data on any non-visual or small target; numeric series in `chart`/`timeline` are lost on VOICE/WATCH.
- **Priority**: P2 (complements F6).
- **How to implement**: Extend the F6 VOICE renderer (and WATCH) to emit a **deterministic sonification descriptor** for numeric series — server computes the normalized value→pitch curve and emits a compact `audio-cue` token list (`[tone:0.2][tone:0.6][tone:0.9]`) the device plays; falls back to a spoken trend summary ("rising, then flat"). All math in Python; the device owns playback. No new dep.
- **Novelty 4 / Impact 3 / Effort M**

### F8. Device-capability-aware model routing (pick the model tier per request)
- **Source**: *Collaborative Inference and Learning between Edge SLMs and Cloud LLMs: A Survey* — Zhang et al., 2025. https://arxiv.org/html/2507.16731v1 — naming **HybridLLM** (quality-gap encoder→routing prob.), **CITER/MixLLM** (contextual bandits over cost+quality), **FrugalGPT** (cascaded routing), **Tabi/LLMCascades** (confidence-based escalation), **FS-GEN** (System-1 SLM / System-2 LLM dual routing).
- **What it is**: A **lightweight scorer/bandit/quality-gap predictor selects the execution path (small vs large model, edge vs cloud) before generation**, escalating to the expensive model only when local confidence is insufficient; cascades verify-then-escalate.
- **Frontier evidence**: Dynamic quality-latency routing cut average latency 5–15% and costly model invocations 10–20% with no quality loss; INT4 on-device gives ~0.75% battery / 25 conversations — concrete latency/energy wins. Demonstrated across the surveyed systems.
- **AstralBody gap**: AstralBody resolves *one* model via `llm_config.client_factory`; ROTE knows the device but **never uses device class to pick a model tier**. A watch/mobile turn pays the same heavy-model latency as a desktop turn; no escalation policy; no privacy-driven keep-on-device choice.
- **Priority**: P1.
- **How to implement**: Add an in-process **`model_router`** in front of `client_factory`: a cheap pure-Python scorer over `(device_caps, turn difficulty signals already computed for UI-designer "hard" detection, user privacy prefs)` selects a tier (operator-default small vs large; future on-device endpoint). Start as a **cascade**: cheap model first, escalate on a confidence/length heuristic (mirror `UI_DESIGNER_MAX_ROUNDS` bounding). Fail-open to current selection. No new dep — it's policy over the existing client seam.
- **Novelty 4 / Impact 5 / Effort M**

### F9. Speculative-decoding / draft-verify framing as a server-side latency lever
- **Source**: *Speculative Decoding Meets Quantization* (arXiv:2505.22179, 2025) and *Accelerating Mobile Language Model via Speculative Decoding and NPU-Coordinated Execution* (2025). https://arxiv.org/abs/2505.22179 / https://arxiv.org/html/2510.15312v3 — token-tree verify (LLMCad, OPT-Tree, Sequoia) per the F8 survey.
- **What it is**: A cheap **draft** model proposes tokens that the strong model **verifies in one pass**, cutting time-to-first-token; tree variants verify many branches at once. The edge-cloud variant runs the draft on-device and verification in cloud.
- **Frontier evidence**: Reported speedups (e.g. PipeSpec ~21% on robot platforms; broad TTFT reductions) without quality loss. Demonstrated.
- **AstralBody gap**: AstralBody can't implement custom decoding (it consumes an OpenAI-compatible endpoint), but it has **no draft→verify pattern at the agent/orchestration layer** — e.g. drafting a UI arrangement or narration with a cheap model and verifying/repairing with the strong one (which the UI-designer's multi-pass loop partially resembles but doesn't formalize as draft-verify).
- **Priority**: P3 (mostly aspirational at the API layer; concrete only as an orchestration analogue).
- **How to implement**: Formalize a **draft-verify orchestration pattern** reusing the router (F8): cheap model drafts the component arrangement / chat narration; strong model verifies-or-repairs only the parts flagged low-confidence. This is a policy on top of `client_factory`, fail-open. Note as *speculative* for true on-device decoding (would need an out-of-process endpoint AstralBody merely routes to). No new dep.
- **Novelty 3 / Impact 3 / Effort M**

### F10. Context-aware, situationally-adaptive UI (attention / interruptibility / environment signals)
- **Source**: *A conceptual framework for context-driven self-adaptive intelligent UI* (Cognition, Technology & Work, 2023) https://link.springer.com/article/10.1007/s10111-023-00749-z — plus the **IMWUT/UbiComp 2023–24** interruptibility & notification-management line (ubicomp.org/ubicomp-iswc-2024/imwut_papers) and SituationAdapt's situation-awareness (F5).
- **What it is**: UI adapts on **situational data — time, location, device status, connectivity, social context, and user attention/interruptibility** — modifying the interface on-the-fly and deciding *when/whether* to surface content (notification triage by inferred interruptibility).
- **Frontier evidence**: A standing IMWUT body shows interruptibility models reduce ill-timed interruptions; the 2023 framework formalizes context→adaptation for intelligent UIs. Demonstrated (in their domains).
- **AstralBody gap**: ROTE adapts only on **device type**, captured **once**. No use of connectivity, ambient/social context, or user interruptibility — and AstralBody has scheduled-job + notification machinery (feature 030) that pushes to chat with *no* situational gating.
- **Priority**: P2.
- **How to implement**: Extend the `register_ui` device payload with optional **context fields** (connectivity class, ambient/theme, "do-not-disturb"/focus) — additive, default neutral. ROTE consumes them as F4 objective weights (low connectivity → lighter renders/fewer images; DND → suppress non-critical pushes). Gate the 030 notification push on an interruptibility flag. Pure additive protocol + policy; no dep.
- **Novelty 3 / Impact 4 / Effort M**

### F11. Live viewport/theme feedback loop (continuous, not one-shot, adaptation)
- **Source**: Foundational responsive/plastic-UI principle (Thévenin & Coutaz, *Plasticity of User Interfaces*, INTERACT 1999, http://iihm.imag.fr/thevenin/papiers/Interact99/Plasticity.Interact99-WWW.pdf) operationalized in modern terms; CSS Container Queries / `prefers-color-scheme` as the web's current per-render feedback mechanism.
- **What it is**: Plasticity requires the *recognition→reaction→execution* loop to fire on **runtime context changes** (resize, rotate, theme switch), not just at session start. Modern web does this with container queries and media features the client reports continuously.
- **Frontier evidence**: Seminal definition of plasticity as withstanding *variations* in physical characteristics while preserving usability — i.e., continuous adaptation by definition. Foundational.
- **AstralBody gap**: ROTE adaptation is **one-shot at `register_ui`**; a browser resize, rotation, or light/dark toggle never re-triggers server adaptation (the per-chat `workspace_layout`/canvas re-render exists but isn't viewport-driven).
- **Priority**: P2.
- **How to implement**: Add a lightweight **`viewport_update`** WS message (additive; width/height/orientation/theme) that the client debounces and sends on change; ROTE re-runs adaptation for the *current canvas* and emits a `ui_render` (the full-canvas re-render path already exists for the designer). Server stays the source of truth (Constitution: never web-only). No dep.
- **Novelty 3 / Impact 4 / Effort M**

### F12. Cross-surface workspace *distribution* (components migrate across simultaneous devices)
- **Source**: *Vulture: Cross-Device Web Experience with Fine-Grained GUI Distribution* — Park, Lee, Choi, Cha (Yonsei). **IEEE INFOCOM 2024**. https://ieeexplore.ieee.org/document/10621433/ — foundations: **CAMELEON** reference framework / FLUID-XP (UIST 2021).
- **What it is**: Distributes **individual GUI elements** of one web app across multiple devices with no app/browser change, via an **in-browser virtual proxy** (virtual HTTP scheme) and a **two-tier DOM** that preserves a "single-browser illusion" while view-state and input sync across devices.
- **Frontier evidence**: Across 50 real web apps, the virtual proxy cut GUI-distribution time **38.47%** and view-change reproduction **20.46%**. Demonstrated.
- **AstralBody gap**: AstralBody fans `ui_upsert` to *all of a user's sockets on a chat* with per-socket ROTE — but every socket gets the *same* canvas. There's no model for **distributing different components to different devices** (controls on phone, big view on TV) in one session.
- **Priority**: P2 (high novelty for an SDUI agent platform; the infra is unusually ready).
- **How to implement**: Leverage the existing per-component `workspace_layout` overlay + multi-socket fan-out: add a **device-affinity tag** per component (or per layout region) so ROTE routes component X to the TV socket and the controls to the phone socket of the same user/chat. Components keep their identities (the overlay model already supports ref-leaf placement). Server-orchestrated, no client framework change beyond honoring "this socket renders subset S". No dep.
- **Novelty 5 / Impact 4 / Effort L**

### F13. Companion-screen / second-screen control pattern (watch/phone drives TV)
- **Source**: CAMELEON-derived distributed-UI literature + industry 10-foot practice (Pascal Potvin, *Designing a 10ft UI* / You.i TV, 2019) https://pascalpotvin.medium.com/designing-a-10ft-ui-ae2ca0da08b7 — and FLUID-XP cross-device input redirection (UIST 2021).
- **What it is**: A small device (phone/watch) acts as the **input surface/remote** for a large lean-back display (TV), because D-pad text entry and dense interaction are painful at 10 feet. Input is redirected from companion to host.
- **Frontier evidence**: Standard, validated pattern in TV UX practice and distributed-UI research (input redirection, companion screens). Demonstrated/foundational.
- **AstralBody gap**: TV is "passthrough-ish" with bigger fonts; no companion-input model — a TV user can't drive a chat turn from their phone within the same AstralBody session.
- **Priority**: P3.
- **How to implement**: Special case of F12 — when a user has both a TV socket and a phone socket on a chat, render the **input/controls only to the phone** and the **canvas only to the TV** (device-affinity routing). The orchestrator already correlates a user's sockets. No dep.
- **Novelty 3 / Impact 3 / Effort M**

### F14. WCAG-as-render/generation-constraint (enforce + auto-validate accessibility)
- **Source**: *When LLM-Generated Code Perpetuates UI Accessibility Barriers, How Can We Break the Cycle?* — **W4A 2025**. https://dl.acm.org/doi/10.1145/3744257.3744266 — and *AccessGuru: Leveraging LLMs to Detect and Correct Web Accessibility Violations in HTML* (2025). https://arxiv.org/pdf/2507.19549
- **What it is**: LLM-generated UI **systematically violates WCAG** — worst on resize-text, contrast, info-and-relationships, name/role/value — unless (1) WCAG criteria are **explicitly injected into the prompt**, (2) keyboard/focus is separately tested, and (3) the model self-reflects. AccessGuru detects *and corrects* violations in HTML.
- **Frontier evidence**: Empirical violation breakdown across criteria + measured improvement from accessibility-oriented prompting and automated correction. Demonstrated.
- **AstralBody gap**: ROTE renders astralprims to **HTML** and runs an **LLM UI-design loop** — both are exactly the surfaces W4A flags, yet there's no WCAG enforcement at render time or in the designer's validators (which currently only check the *primitive palette*, not accessibility).
- **Priority**: P2 (UX + the only accessibility coverage in the device review).
- **How to implement**: Two cheap moves, no dep: (a) make `webrender/renderer.py` emit **accessible HTML by construction** (semantic landmarks, `aria-*`, computed contrast checks on `css` colors via a small Python contrast function, alt text required) — `esc()`-by-default is already there; extend with a11y attributes. (b) Add a **WCAG checklist to the UI-designer's prompt** and a deterministic post-validator (contrast ratio, missing alt/labels) that rejects/repairs an arrangement before delivery — mirrors the existing palette validators. Fail-open.
- **Novelty 3 / Impact 4 / Effort M**

### F15. Live semantic accessibility tree (AOM-style) as a first-class render target
- **Source**: *Accessibility Object Model (AOM) explainer* — WICG, ongoing. https://wicg.github.io/aom/explainer.html — and *Screen Reader AI: Conversational Web-Accessibility Assistant* (builds a live DOM+AOM semantic scene graph), 2025. https://www.researchgate.net/publication/396362763
- **What it is**: Apps expose a **semantic accessibility tree** (roles, names, states, relationships) that assistive tech consumes to build an alternate (e.g. spoken) UI; AOM lets authors compute/augment that tree directly. Screen Reader AI fuses DOM+AOM into a live semantic graph for multimodal reasoning.
- **Frontier evidence**: AOM is the platform-standard semantic model; the 2025 system shows LLMs reasoning over a fused semantic tree to drive accessible interaction. Demonstrated/standardizing.
- **AstralBody gap**: astralprims already carry semantics (a `Table` *is* a table) — richer than HTML — but ROTE discards that to flat HTML/voice text instead of emitting a **machine-navigable semantic tree** that a VOICE/AT target could traverse.
- **Priority**: P2 (synergistic with F6).
- **How to implement**: Add a **`SEMANTIC`/AOM-style renderer** that serializes the astralprims component graph to a navigable role/name/state tree (JSON) — *not* HTML — which the VOICE renderer (F6) and any AT client consume. This is the cleanest expression of "astralprims defines → orchestrator renders → ROTE adapts": one more renderer, primitives unchanged. Pure Python serialization, no dep.
- **Novelty 4 / Impact 4 / Effort M**

### F16. Tiered level-of-detail (LoD) content model as the universal device knob
- **Source**: Progressive-disclosure-as-engineering line, 2024–25 — Anthropic, *Effective Context Engineering for AI Agents* (layered index→summary→full) https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — generalizing NN/g progressive disclosure to multi-form-factor rendering.
- **What it is**: Content is authored once as **tiers — Level 1 index/traffic-light, Level 2 summary metrics, Level 3 full detail** — and the consumer pulls the depth it needs. A single principled ladder replaces ad-hoc per-surface trimming.
- **Frontier evidence**: Widely adopted in agent/context engineering as the right density mechanism; NN/g establishes the UX validity of progressive disclosure. Demonstrated (UX) / emerging (as a render contract).
- **AstralBody gap**: ROTE trims per device type with bespoke logic; there's no **explicit LoD ladder** per component, so WATCH/VOICE degradation is lossy and inconsistent. (FR-027's short-vs-long narrative split is a 2-level hint of this but isn't generalized.)
- **Priority**: P2 (the connective tissue across F4/F6/F18).
- **How to implement**: Let each renderer request a **target LoD** (computed by ROTE from device caps): TV/desktop = L3, TABLET = L2–L3, MOBILE = L2, WATCH = L1, VOICE = tiered L1→L3 on demand. astralprims components expose a `summary`/`detail` projection (the summarizer agent already produces TL;DR/key-points — reuse the convention; for others derive deterministically: table→top-N rows + "N more"). Renderer-side projection; no primitive change. Feeds the F4 cost (info-density objective).
- **Novelty 3 / Impact 4 / Effort M**

### F17. Output-modality / "intelligence" routing across surfaces (right modality per device)
- **Source**: *CUI@CHI 2024: Building Trust in CUIs* (workshop report) https://arxiv.org/pdf/2401.13970 — combined with the multimodal+visual conversational-UI literature (voice+screen co-design).
- **What it is**: The *modality* of the answer (visual component vs spoken summary vs glanceable metric) should be chosen by context/device, and **trust/clarity in CUIs depends on matching modality to situation** (e.g., confirmations spoken, dense data visual). Conversational + visual surfaces are co-designed, not one substituted for the other.
- **Frontier evidence**: CHI 2024 workshop consolidating CUI trust/clarity guidance; modality-fit is a recurring finding. Foundational/guidance.
- **AstralBody gap**: AstralBody narrates *and* renders the same content regardless of surface; on VOICE the visual is dropped, on WATCH the prose is dropped — but there's no policy that **chooses the modality** (e.g., on VOICE, prefer a 1-sentence answer + offer "want details?"; on TV, prefer visual-first).
- **Priority**: P3.
- **How to implement**: A small **modality-policy** in ROTE keyed on device caps decides, per turn, the primary modality and suppresses the other (reuses F16 LoD + the existing `_chat_narrative` short/long split). Server-side policy; no dep.
- **Novelty 3 / Impact 3 / Effort S**

### F18. TV/10-foot renderer with server-emitted focus graph + D-pad navigation order
- **Source**: *Designing a 10ft UI* — Pascal Potvin (You.i TV), 2019 https://pascalpotvin.medium.com/designing-a-10ft-ui-ae2ca0da08b7 — Android TV focus-management guidance; *10-foot user interface* (Wikipedia overview). https://en.wikipedia.org/wiki/10-foot_user_interface
- **What it is**: 10-foot UIs require **explicit focus state and a predictable D-pad navigation order** — every element reachable via up/down/left/right with a clearly-defined "next" in each direction (usually grid layout), large hit/legibility targets, and lean-back simplicity. Focus is a *first-class data model*, not styling.
- **Frontier evidence**: Standard validated TV-UX practice (Android TV, You.i TV). Demonstrated/foundational.
- **AstralBody gap**: The TV target lacks a **focus/navigation model** — server emits no spatial order, so D-pad navigation isn't possible; "TV" is effectively a larger browser render.
- **Priority**: P3.
- **How to implement**: Build a **TV renderer** that emits, alongside HTML, a **focus-graph hint**: each focusable component gets a stable id + up/down/left/right neighbor ids computed server-side from the layout grid (astralprims components carry this as render attributes, like the existing `data-component-id` morph anchors — no primitive change). Apply 10-foot LoD (F16 L3-sparse, large type). New renderer = SDUI-clean. No dep.
- **Novelty 3 / Impact 3 / Effort M**

### F19. AR/spatial web-content extension as a new render target
- **Source**: *AiRWeb: Using AR to Extend Web Browsing Beyond Handheld Screens* (arXiv 2026) https://arxiv.org/pdf/2603.07586 — with SituationAdapt (F5) for the spatial-placement reasoning.
- **What it is**: Extends conventional web content into the **AR space around a handheld device**, placing components in 3D beyond the small screen — i.e., the same content, a spatial renderer. Spatial placement benefits from situation-aware optimization (F5).
- **Frontier evidence**: Demonstrates AR as an *extension* surface for existing web UI rather than a separate app. Emerging (recent).
- **AstralBody gap**: No spatial/AR target at all; the device enum tops out at TV.
- **Priority**: P3 (forward-looking; proves the renderer-extensibility thesis).
- **How to implement**: Define an **`AR`/spatial renderer** that serializes astralprims components to a placement spec (component + 3D anchor + LoD) consumed by a spatial client; reuse F4/F5 objectives for placement (occlusion, reachability, social). Validates that "add a target = add a renderer" scales to spatial. Spec spatial-client side; AstralBody side is pure Python serialization. No dep. (Mostly *speculative* until a spatial client exists.)
- **Novelty 4 / Impact 2 / Effort L**

### F20. Capability/feature-detection negotiation as a typed handshake (host-config style)
- **Source**: *Adaptive Cards — Host Config & responsive layout* — **Microsoft**, ongoing. https://adaptivecards.microsoft.com/?topic=responsive-layout / https://learn.microsoft.com/en-us/adaptive-cards/
- **What it is**: A **Host Config** is per-host data (spacing, colors, max-actions, supported elements) that drives how the *same* declarative card adapts to each host; interactivity is expressed **declaratively** to bound injection risk, and templating separates data from layout.
- **Frontier evidence**: Shipping standard across Teams/Outlook/bots — one JSON card adapts to many hosts purely via host-config data + declared element support. Demonstrated at scale.
- **AstralBody gap**: ROTE's per-target behavior is **code**, not **data**; there's no per-target "host config" (spacing/contrast/max-density/supported-types) that an operator can tune without editing `rote/adapter.py`.
- **Priority**: P2 (operationalizes F1/F4 cleanly; also an agentic-security angle — declarative bounds limit what a target renders).
- **How to implement**: Give each renderer target a **declarative host-config dict** (supported primitive types [F1], spacing/density caps, contrast floor [F14], max actions, LoD default [F16]) loaded as data and consumed by ROTE/the F4 scorer. New targets ship a config, not a code branch. The declarative bound also caps what a compromised agent's component can do per surface (security). Pure data + Python; no dep.
- **Novelty 3 / Impact 4 / Effort S**

---

## Sources

**Industry SDUI architecture (deep-dives)**
- Ryan Brooks — *A Deep Dive into Airbnb's Server-Driven UI System* — Airbnb Tech Blog, 2021. https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5
- MobileNativeFoundation — *Server-Driven UI (Backend-driven UI) strategies* — discussion #47, 2023–24. https://github.com/MobileNativeFoundation/discussions/discussions/47
- debugg.ai — *Server-Driven UI in 2025: Versioned Layout Schemas, Capability Negotiation, Safe Mobile Rollouts*, 2025. https://debugg.ai/resources/server-driven-ui-2025-versioned-layout-schemas-capability-negotiation-safe-mobile-rollouts
- Spotify — *HubFramework* (component-driven UI, README; deprecated), 2016–18. https://github.com/spotify/HubFramework
- sshh12 — *Netflix web architecture reverse-engineered* (MSL capability negotiation), 2024. https://gist.github.com/sshh12/dda3a89514f850c459380b18b1f7eb7b
- Microsoft — *Adaptive Cards: Host Config & responsive layout*, ongoing. https://adaptivecards.microsoft.com/?topic=responsive-layout · https://learn.microsoft.com/en-us/adaptive-cards/

**Cross-device / plastic / distributed UI**
- Park, Lee, Choi, Cha — *Vulture: Cross-Device Web Experience with Fine-Grained GUI Distribution* — IEEE INFOCOM 2024. https://ieeexplore.ieee.org/document/10621433/
- Thévenin & Coutaz — *Plasticity of User Interfaces: Framework and Research Agenda* — INTERACT 1999 (seminal). http://iihm.imag.fr/thevenin/papiers/Interact99/Plasticity.Interact99-WWW.pdf
- Pascal Potvin (You.i TV) — *Designing a 10ft UI*, 2019. https://pascalpotvin.medium.com/designing-a-10ft-ui-ae2ca0da08b7 · *10-foot user interface* (overview). https://en.wikipedia.org/wiki/10-foot_user_interface

**Adaptive-layout optimization / context / AR-spatial**
- Belo et al. — *AUIT — the Adaptive User Interfaces Toolkit for Designing XR Applications* — UIST 2022. https://dl.acm.org/doi/10.1145/3526113.3545651
- Li, Zhipeng et al. — *SituationAdapt: Contextual UI Optimization in Mixed Reality with Situation Awareness via LLM Reasoning* — UIST 2024. https://dl.acm.org/doi/10.1145/3654777.3676470 · https://arxiv.org/abs/2409.12836
- *A conceptual framework for context-driven self-adaptive intelligent UI* — Cognition, Technology & Work, 2023. https://link.springer.com/article/10.1007/s10111-023-00749-z
- UbiComp/ISWC (IMWUT) 2023–24 — interruptibility & notification-management papers. https://www.ubicomp.org/ubicomp-iswc-2024/imwut_papers/
- *AiRWeb: Using AR to Extend Web Browsing Beyond Handheld Screens* — arXiv 2026. https://arxiv.org/pdf/2603.07586

**Multimodal / voice / non-visual rendering & accessibility**
- *Chart Reader: Accessible Visualization Experiences Designed with Screen Reader Users* — CHI 2023. https://dl.acm.org/doi/full/10.1145/3544548.3581186
- *MAIDR: Making Statistical Visualizations Accessible with Multimodal Data Representation* — CHI 2024.
- *Spatial Audio-Enhanced Multimodal Graph Rendering for Efficient Data Trend Learning on Touchscreen Devices* — CHI 2024. https://dl.acm.org/doi/10.1145/3613904.3641959
- *ChartA11y: Accessible Touch Experiences of Visualizations with Blind Smartphone Users*, 2024. https://arxiv.org/html/2410.20545v1
- *When LLM-Generated Code Perpetuates UI Accessibility Barriers, How Can We Break the Cycle?* — W4A 2025. https://dl.acm.org/doi/10.1145/3744257.3744266
- *AccessGuru: Leveraging LLMs to Detect and Correct Web Accessibility Violations in HTML*, 2025. https://arxiv.org/pdf/2507.19549
- WICG — *Accessibility Object Model (AOM) explainer*, ongoing. https://wicg.github.io/aom/explainer.html
- *Screen Reader AI: A Conversational Web-Accessibility Assistant* (DOM+AOM semantic scene graph), 2025. https://www.researchgate.net/publication/396362763
- *CUI@CHI 2024: Building Trust in CUIs — From Design to Deployment* (workshop). https://arxiv.org/pdf/2401.13970

**On-device / edge LLM inference & compute placement**
- Zhang et al. — *Collaborative Inference and Learning between Edge SLMs and Cloud LLMs: A Survey* — 2025 (HybridLLM, CITER, MixLLM, FrugalGPT, Tabi, FS-GEN, token-tree verify). https://arxiv.org/html/2507.16731v1
- *Dynamic Quality-Latency Aware Routing for LLM Inference in Wireless Edge-Device Networks* — arXiv 2508.11291, 2025. https://arxiv.org/pdf/2508.11291
- *Speculative Decoding Meets Quantization: Compatibility Evaluation and Hierarchical Framework Design* — arXiv 2505.22179, 2025. https://arxiv.org/abs/2505.22179
- *Accelerating Mobile Language Model via Speculative Decoding and NPU-Coordinated Execution* — 2025. https://arxiv.org/html/2510.15312v3

**Progressive disclosure / content prioritization**
- Anthropic — *Effective Context Engineering for AI Agents* (layered index→summary→full), 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
