# Generative & adaptive UI literature — findings

*HCI + AI literature review for AstralDeep. Scope: recent (2023–2026) scholarly + lab work on generative UI, adaptive interfaces, and LLM-driven interface generation, mapped to AstralDeep's server-driven-UI (SDUI) + adaptive-UI-designer architecture. Compiled 2026-06-16.*

AstralDeep baseline assumed throughout: closed palette of ~31 `astralprims` primitive types (dict-defined → orchestrator-rendered HTML → ROTE per-device adaptation); a bounded multi-round single-LLM **self-critique** layout loop that arranges ≥2 rich components into a layout tree of existing primitives (leaves = component refs), keep-best, fail-open to flat append; ref-leaf-overlay persistence in `workspace_layout`; per-user personalization + memory. Constraints: Python-only backend, **no new third-party runtime libraries**, SDUI mandate is constitutional, idempotent migrations.

---

## Executive summary

- **The single biggest gap is structure, not styling.** Frontier systems (Cao/Jiang/Xia CHI'25; DuetUI UIST'25; Athena; PrototypeFlow TOCHI'25) generate a *task-driven data/intermediate model first* and derive the UI from it via deterministic render rules. AstralDeep's designer arranges *finished components*; it never models the underlying task object. Generating a typed task schema → annotating each field with `<function, render, editable>` → mapping to existing primitives is the highest-novelty, highest-impact move and fits the SDUI mandate exactly (F1, F2).
- **Make the designer a multi-objective optimizer, not a vibe loop.** Draco/DracoGPT (Heer, IEEE VIS'24) and the combinatorial-optimization-of-GUIs line (Oulasvirta) show layout quality is formalizable as weighted soft constraints minimized by search. A pure-Python constraint scorer that *grades* candidate arrangements (alignment, grouping, balance, device fit) turns AstralDeep's "keep-best" into a *measurable* best, and lets a weak/cheap LLM propose while deterministic code decides (F3, F8).
- **Adapt-or-not should be a planned decision with a disruption cost.** Todi et al. (CHI'21 model-based RL) prove that *predicting* the benefit of a change and charging an explicit **adaptation/relearning cost** beats greedy adaptation; a conservative policy changes only when net-positive. AstralDeep re-designs layouts freely turn-to-turn — a per-user "layout stability" cost would stop jarring re-arrangements (F9).
- **Intent grounding before generation beats refinement after.** Intent-clarification + RAG-from-exemplars (PrototypeFlow; Human-AI Synergy TOCHI'25) and FSM/reward-driven candidate refinement (Stanford *Generative Interfaces*, 72% pref. gain) outperform request→response. AstralDeep can add a cheap intent/affordance classifier that picks an *interaction pattern* (compare / monitor / explore / decide) up front and conditions the design (F4, F11).
- **Self-improvement can be automated and offline.** Apple UICoder (compiler + multimodal feedback → filter/score/dedup → finetune) and Apple's designer-feedback work (annotation-as-critique beats RLHF ranking, beats GPT-5) show how to *mine your own renders* into a quality dataset and a learned layout-quality scorer — zero new libs, runs as a Python batch job over `workspace_layout` history (F13, F14).
- **Trust + safety are first-class UX in generated UIs.** LLM-generated UIs measurably inject **dark patterns** unprompted (Deception at Scale, CHI'26: 1K e-commerce components) and mis-surface confidence. AstralDeep should add a deterministic **anti-dark-pattern lint** over the arrangement and an **uncertainty/provenance badge** primitive, plus mandatory fact-grounding when components assert entity facts (Google Generative UI) (F15, F16, F17).
- **Bidirectional / mixed-initiative beats one-shot.** DuetUI's "bidirectional context loop" (interaction with the rendered UI → re-infer intent → re-render) and Horvitz's mixed-initiative principles point at the next paradigm: AstralDeep already has `component_action` re-execution — promoting interaction signals into the design context makes the canvas co-generative (F11, F12).
- **Evolve the palette responsibly, don't open it.** Grammar-guided generation (UI-Grammar) and "gradual generation" (intermediate customization layers) show how to keep generation *inside a typed vocabulary* while still expanding it — AstralDeep can express its 31 primitives as a formal grammar the LLM must satisfy, and gate any *new* primitive behind the same draft→self-test→admin-approval pipeline it already uses for agents (F6, F18, F19).

---

## Findings

### F1. Task-driven data model as the generation substrate (generate the *model*, render the UI)
- **Source:** Yining Cao, Peiling Jiang, Haijun Xia, "Generative and Malleable User Interfaces with Generative and Evolving Task-Driven Data Model," CHI 2025. https://dl.acm.org/doi/10.1145/3706598.3713285 (preprint arXiv:2503.04084).
- **What it is:** Instead of generating UI directly, the LLM generates a typed **task-driven data model**: an object-relational schema (a root task object + entity objects + attributes typed as SVAL/DICT/PNTR/ARRY), a **dependency graph** of `{Source, Target, Mechanism (Validate|Update), Relationship}`, and instantiated data. The UI is then *derived deterministically* by annotating each attribute with `<function, render, editable>` and recursively mapping to widgets.
- **Frontier evidence:** Technical eval over 50 prompts: entities 94.1–94.7% and attributes 93.9–95.2% rated "necessary and expected"; dependencies 91.5% relationship / 96.9% mechanism accuracy. User study (8 ppl, 16 freeform tasks, 131 follow-up prompts): 8/8 agreed info was relevant, customization easy, layout intuitive.
- **AstralDeep gap:** AstralDeep's designer arranges *finished* components and has **no model of the underlying task**. It cannot reason about entities, relationships, validation, or auto-propagation; every turn re-derives layout from scratch with no semantic backbone.
- **Priority:** Novelty (highest).
- **How to implement in AstralDeep:** Add an orchestrator pre-pass that, for component-rich turns, asks the LLM for a small JSON **task schema** (entities + typed attributes + dependency edges) *before* agents render. Map attribute types → existing primitives with a deterministic Python rule table (SVAL→Text/MetricCard/Rating; DICT→KeyValue; PNTR→Card thumbnail+link; ARRY→Table or Tabs; temporal→Timeline). The schema becomes the layout tree's semantic spine and persists alongside the `workspace_layout` overlay. No new libs — pure prompt + dict rules within SDUI.
- **Novelty 5 / Impact 5 / Effort L**

### F2. Typed-attribute → widget mapping rules (`<function, render, editable>` annotation)
- **Source:** Cao, Jiang, Xia, CHI 2025 (as F1); reinforced by Athena's intermediate representations — Jazbo Beason, Ruijia Cheng, Eldon Schoop, Jeffrey Nichols, "Athena: Intermediate Representations for Iterative Scaffolded App Generation with an LLM," arXiv:2508.20263, 2025.
- **What it is:** Each data attribute is auto-annotated with a *function* (what it does), a *render* directive (which widget + expanded/summary form), and an *editable* flag; a fixed rule set maps annotations to concrete widgets. Renders recurse from the root object. This cleanly separates "what the data is" from "how it looks," giving stable, predictable UI from variable data.
- **Frontier evidence:** Same eval as F1 (94%+ attribute appropriateness; users successfully performed schema/data/representation edits). Athena shows IRs make iterative app generation more steerable and correct than direct code emission.
- **AstralDeep gap:** AstralDeep chooses a primitive per *tool output*, not per *semantic field*; there is no notion of expanded-vs-summary rendering of the same field, nor an editable flag driving interactivity.
- **Priority:** High (enables F1).
- **How to implement in AstralDeep:** Encode the annotation rule table in `ui_designer.py` as a pure function `attr_to_primitive(attr_type, cardinality, role) -> primitive_spec`. Add an `editable` bit that, when true, emits a primitive whose action routes through the existing `component_action` re-execution path. ROTE already collapses expanded↔summary per device — wire the render directive into ROTE's existing capability checks.
- **Novelty 4 / Impact 5 / Effort M**

### F3. Layout quality as weighted-soft-constraint optimization (Draco / combinatorial GUI optimization)
- **Source:** Junran Yang, Hilson Shrestha, Jeffrey Heer, "DracoGPT: Extracting Visualization Design Preferences from Large Language Models," IEEE VIS / TVCG 2024, arXiv:2408.06845. Foundations: Moritz et al., "Formalizing Visualization Design Knowledge as Constraints" (Draco, TVCG 2019); Oulasvirta et al., "Combinatorial Optimization of GUI Designs" (2020); Dayama et al., "GRIDS: Interactive Layout Design with Integer Programming," CHI 2020.
- **What it is:** Design knowledge is encoded as **hard constraints** (validity) + **weighted soft constraints** (preferences); recommendation = minimize total cost = sum of weights of *satisfied* soft constraints. DracoGPT shows LLM design preferences can be *extracted* (rank chart pairs → RankSVM learns weights) and compared against the constraint base.
- **Frontier evidence:** Draco recommends near-expert visualizations via cost minimization (Answer-Set-Programming solver in the original; the principle, not the solver, is what transfers). DracoGPT finding: LLM preferences *diverge* from human-subjects guidelines (e.g., spurious positional-encoding preference) — i.e., a deterministic constraint base is a needed corrective to an LLM's taste.
- **AstralDeep gap:** AstralDeep's "keep-best" has **no objective function** — "best" is whatever the same LLM says is best, with the LLM's documented biases unchecked. There's no measurable score, so two runs can't be compared and regressions are invisible.
- **Priority:** Highest.
- **How to implement in AstralDeep:** Write a pure-Python `score_arrangement(tree, device) -> float` summing weighted penalties: misaligned siblings, unrelated components grouped, >N components without sectioning, primitive type incompatible with device, overflow under ROTE, low information-density. The LLM *proposes* arrangements; the scorer *selects*. Weights live in a tweakable dict (later learnable, see F13/F14). This is the constitutional "orchestrator renders/decides" role done rigorously — no solver dependency needed (greedy/beam over the LLM's few candidates).
- **Novelty 4 / Impact 5 / Effort M**

### F4. Up-front interaction-pattern selection via structured representations + reward-guided refinement
- **Source:** Jiaqi Chen et al. (Stanford SALT), "Generative Interfaces for Language Models," arXiv:2508.19227, 2025. https://salt-nlp.github.io/generative_interfaces/
- **What it is:** LLM responds to a query by *proactively generating a UI*. It translates the query into a task-specific interface using **structured interface representations (directed graphs, finite-state machines)** and **iterative refinement against adaptive reward functions**, choosing an interaction pattern suited to the task (information-dense, exploratory, multi-turn).
- **Frontier evidence:** Multidimensional human eval (functional/interactive/emotional) across diverse tasks: generative interfaces beat chat by **up to 72% in human preference**; drivers were cognitive offloading in complex scenarios and higher perceived credibility from structured presentation.
- **AstralDeep gap:** AstralDeep only *arranges what agents already produced*; it never decides the *interaction pattern* the user needs (compare? monitor? decide? explore?). The designer is reactive, not intent-typed.
- **Priority:** High.
- **How to implement in AstralDeep:** Add a cheap pre-pass classifier (one LLM call or rules over the user message + tool set) that tags the turn with an **interaction archetype** {compare, monitor, explore, summarize, decide, form}. Each archetype maps to a *layout prior* (compare→side-by-side/Tabs; monitor→MetricCard grid+Timeline; decide→KeyValue+Rating+Hero CTA) that seeds the designer and the F3 scorer's weights. FSM/graph reward refinement maps onto AstralDeep's existing multi-round loop — just make the reward = F3 score.
- **Novelty 4 / Impact 5 / Effort M**

### F5. Adaptive reward functions over structured candidates (replace open-ended self-critique)
- **Source:** Chen et al., "Generative Interfaces for Language Models," arXiv:2508.19227, 2025 (as F4).
- **What it is:** Rather than "ask the model to critique its own UI" in free text, candidates are refined against **explicit, adaptive reward functions** computed over the structured representation (state coverage, transition validity, task-completion enablement). The loop is search-with-a-reward, not vibe-with-a-prompt.
- **Frontier evidence:** The 72% preference win is attributed to this structured-refinement-with-rewards pipeline rather than free-form generation.
- **AstralDeep gap:** AstralDeep's "critique-its-own-UI → improve/DONE" is *open-ended natural-language self-critique* — known to be unreliable and unmeasurable; "converged = identical refinement" is a weak stopping rule.
- **Priority:** High.
- **How to implement in AstralDeep:** Reframe each designer round as: propose k candidate arrangements → score each with F3 → keep argmax → stop when score plateaus or budget hits. Keep the LLM for *proposal diversity*; move *judgment* to the deterministic reward. This is a small refactor of the existing round loop and directly de-risks the documented "weak dev LLM prompting" problem in the project notes.
- **Novelty 3 / Impact 5 / Effort S**

### F6. Grammar-guided generation to keep the LLM inside the primitive vocabulary
- **Source:** Yuwen Lu et al., "UI Layout Generation with LLMs Guided by UI Grammar," arXiv:2310.15455 (ICML 2023 workshop on Structured Generation).
- **What it is:** A **context-free UI grammar** (production rules over element types + nesting constraints) is supplied to the LLM as an intermediary representation; the LLM emits grammar-conforming structure, raising validity and giving users controllability by *editing the grammar* itself.
- **Frontier evidence:** Grammar guidance improved structural validity and hierarchy quality of generated layouts vs. ungrammared prompting, and exposed controllability (swap/restrict productions to steer output).
- **AstralDeep gap:** AstralDeep's palette is *closed but informal* — the LLM is told the 31 types in prose. There's no formal grammar guaranteeing legal nesting (e.g., Tabs-of-Cards-of-Text), so invalid trees are caught only by post-hoc repair.
- **Priority:** High (predictability + safety).
- **How to implement in AstralDeep:** Express the 31 primitives as an explicit grammar: legal children per container type, arity, leaf-only types. Inject the grammar into the designer prompt AND validate every proposed tree against it before render (reject+regenerate on violation). Derive the grammar from the existing `webrender.allowed_primitive_types()` registry so it never drifts. Later: per-archetype grammar subsets (F4) further constrain output.
- **Novelty 3 / Impact 4 / Effort M**

### F7. AlignUI: preference-aspect taxonomy + RAG-from-preference-dataset (no training)
- **Source:** "AlignUI: A Method for Designing LLM-Generated UIs Aligned with User Preferences," arXiv:2601.17614, 2026.
- **What it is:** A three-layer preference representation — **task → preference aspect → UI control** — where the three aspects are **predictability, efficiency, explorability**. A crowdsourced dataset of preferred controls is used as **RAG context** (retrieve similar tasks' preferred widgets, inject into the prompt, sanity-check against an implementable candidate set). Entirely inference-time; no RLHF/DPO.
- **Frontier evidence:** Study with 72 participants over 6 tasks: UIs generated *with* the preference dataset were significantly preferred over without across all three aspects (χ², p<0.05); 30-user preference sets were most consistently aligned and generalized to unseen task types.
- **AstralDeep gap:** AstralDeep personalizes via memory but has **no structured preference vocabulary** for *UI* (does this user want fewer surprises? denser layouts? more exploration affordances?), and no retrieval of "what arrangement worked for similar past turns."
- **Priority:** High (personalization).
- **How to implement in AstralDeep:** Define an AstralDeep UI-preference triple per user {predictability, efficiency, explorability} as numeric dials in `user_personalization`. Build a tiny RAG over past `workspace_layout` rows keyed by interaction archetype (F4): retrieve the user's accepted arrangements for similar turns, inject as exemplars, and bias the F3 weights by the user's three dials. Pure prompt + existing tables.
- **Novelty 4 / Impact 4 / Effort M**

### F8. Combinatorial optimization of GUIs / integer-programming layout (foundations to mine)
- **Source:** Oulasvirta et al., "Combinatorial Optimization of Graphical User Interface Designs," Proc. IEEE 2020; Dayama, Todi, Saarelainen, Oulasvirta, "GRIDS: Interactive Layout Design with Integer Programming," CHI 2020. https://userinterfaces.aalto.fi/grids/
- **What it is:** Layout is posed as integer/linear programming: variables = element positions/sizes; constraints = no overlap, fit-to-canvas, alignment, grouping, preferred positions; objective = design-goal functions (grid regularity, balance). MILP guarantees valid packing.
- **Frontier evidence:** GRIDS produces grid-aligned, hole-free, non-overlapping layouts interactively; linear formulation keeps it fast enough for interactive use.
- **AstralDeep gap:** AstralDeep emits a *tree* the renderer flexbox-lays-out; it never reasons about 2-D balance, grouping, or grid regularity as an objective. ROTE adapts per device but doesn't *optimize* arrangement.
- **Priority:** Medium-High.
- **How to implement in AstralDeep:** No MILP solver (no new lib), but **borrow the objective terms** as the F3 scorer's penalty functions (alignment, grouping of related refs, balance across columns, preferred-position priors per archetype). For the common "grid of N cards" case, a tiny pure-Python heuristic packer (rows/cols by aspect ratio + device width) is enough and deterministic.
- **Novelty 3 / Impact 4 / Effort M**

### F9. Model-based RL adaptation with explicit disruption cost + conservative policy
- **Source:** Kashyap Todi, Gilles Bailly, Luis Leiva, Antti Oulasvirta, "Adapting User Interfaces with Model-based Reinforcement Learning," CHI 2021, arXiv:2103.06807. https://userinterfaces.aalto.fi/
- **What it is:** Adaptation framed as planning: it **predicts the effect** of candidate adaptations using HCI performance models, charges an explicit **cost of adaptation** (surprise/relearning), and plans *sequences* of adaptations (model-based, look-ahead) rather than greedy single steps. A **conservative policy** adapts only when net-beneficial, else leaves the UI alone.
- **Frontier evidence:** On adaptive menus, the planning approach outperformed both non-adaptive and frequency-based (greedy) policies; the core thesis — penalize change, predict before acting, avoid change when no benefit — is repeatedly validated (see also Langerak et al. comparative reward-model study, EMSE 2025).
- **AstralDeep gap:** AstralDeep re-designs the canvas **every component-rich turn** with no penalty for moving things the user just learned. There is no "is re-arranging worth the disruption?" gate; layouts can churn turn-to-turn.
- **Priority:** Highest (UX + predictability).
- **How to implement in AstralDeep:** Add a **layout-stability cost** to F3: penalize arrangements by edit-distance from the user's *current* persisted `workspace_layout` for that chat. Only commit a new arrangement if `score_new − stability_cost > score_current + margin`; otherwise keep the existing overlay (fail-stable). The margin is the user's `predictability` dial (F7). This turns the keep-best loop into a *conservative* one with zero new deps.
- **Novelty 4 / Impact 5 / Effort S**

### F10. Predictive HCI models as the reward (forecast cost-of-use, don't just eyeball)
- **Source:** Todi et al. CHI 2021 (as F9); broader computational-UI line (Oulasvirta lab). Pointing (Fitts' law), visual-search, and selection-time models forecast user cost of a given layout.
- **What it is:** Use closed-form HCI predictors (expected pointing time, visual-search time, number of steps to target) to score a layout's *predicted cost of use*, feeding the adaptation reward.
- **Frontier evidence:** Predictive-model-driven adaptation outperforms heuristic adaptation because it optimizes a *grounded* proxy for user effort, not surface aesthetics.
- **AstralDeep gap:** AstralDeep has no predicted-effort signal; "good layout" is purely the LLM's aesthetic judgment.
- **Priority:** Medium.
- **How to implement in AstralDeep:** Add lightweight effort proxies to the F3 scorer: estimated scroll depth (sum of component heights vs viewport per device from ROTE caps), number of taps to reach an actionable/editable element, density penalty for tiny screens (watch/mobile). These are deterministic Python given the tree + ROTE device profile; they make "fits the device well" a *number*, sharpening ROTE's existing adaptation.
- **Novelty 3 / Impact 4 / Effort M**

### F11. Bidirectional context loop — interaction with the rendered UI re-infers intent
- **Source:** "DuetUI: A Bidirectional Context Loop for Human-Agent Co-Generation of Task-Oriented Interfaces," arXiv:2509.13444 (UIST 2025 track).
- **What it is:** A shared **Context Layer** is the single source of truth between human and agent. User manipulations of the live UI are logged to a **Bidirectional Action History**; a **TaskAgent** re-infers implicit intent and updates a task decomposition (Task→Subtask→Data) that is *dually coupled* to interface structure (Navigation→Page→Component); an InterfaceAgent + RenderingAgent re-render. Either party can seize initiative.
- **Frontier evidence:** Technical eval (10 tasks): weighted-F1 0.277 (baseline) → 0.508 (full loop); subtask F1 0.518→0.798; component F1 0.116→0.325. Experts (n=20): overall 3.64→4.11, completeness 3.15→4.15 (p=0.002). 24-participant study: better efficiency, usability, satisfaction; users preferred iterative dialogue to one-shot.
- **AstralDeep gap:** AstralDeep's `component_action` re-executes a single component's source tool, but interaction signals **don't feed back into the designer or a task model** — the canvas isn't co-generative; the layout doesn't evolve from what the user touches.
- **Priority:** High (novelty + UX).
- **How to implement in AstralDeep:** Log `component_action` / `table_paginate` / edit events into a per-chat **action history**, and feed a compact summary ("user filtered Table X to B&B, expanded Card Y") into the next turn's designer + F1 task-schema pre-pass. Couple the task schema (F1) to the layout so updating one updates the other. Builds directly on existing `component_action` + `workspace` infra.
- **Novelty 5 / Impact 4 / Effort M**

### F12. Mixed-initiative principles as design contract for the designer loop
- **Source:** Eric Horvitz, "Principles of Mixed-Initiative User Interfaces," CHI 1999. https://dl.acm.org/doi/10.1145/302979.303030 (foundational; actively revived in 2024–25 agentic-UI work, e.g., IUI'25 group-conversation control).
- **What it is:** Twelve principles for human-agent initiative sharing: consider uncertainty about user goals; *expected value of action* (act only when benefit > cost); provide mechanisms for efficient invocation/dismissal of automation; maintain memory of recent interactions; allow graceful user override; minimize cost of poor guesses.
- **Frontier evidence:** Enduring; the explicit expected-value-of-automation criterion is the conceptual parent of F9's net-benefit gate and is being re-applied to LLM agent participation decisions in 2025 IUI/CHI work.
- **AstralDeep gap:** AstralDeep's designer acts *unconditionally* (always redesigns if ≥2 components) with no expected-value test, no easy user dismissal of an arrangement, and no "undo this layout" affordance.
- **Priority:** Medium-High (predictability).
- **How to implement in AstralDeep:** Encode the principles as guardrails: (a) act only when expected layout benefit clears the F9 threshold; (b) add a lightweight "reset to flat / pin this layout" chrome control so users can dismiss/override automation cheaply; (c) keep the recent-interaction memory (F11) so the designer doesn't fight the user. All chrome + orchestrator policy; no new libs.
- **Novelty 3 / Impact 4 / Effort S**

### F13. Self-improving generation from automated feedback (UICoder loop, offline)
- **Source:** Apple ML Research — "UICoder: Finetuning LLMs to Generate UI Code through Automated Feedback," arXiv:2406.07739, 2024. https://machinelearning.apple.com/research/uicoder
- **What it is:** The model self-generates a large synthetic UI dataset; **automated tools (compilers + multimodal/vision models) filter, score, and de-duplicate** it into a higher-quality subset; the model is finetuned on the refined set; repeat. Quality rises with no human labels.
- **Frontier evidence:** Iterated models outperform all downloadable baselines and approach larger proprietary models, judged by automated metrics *and* human preference — purely from compiler + multimodal feedback signals.
- **AstralDeep gap:** AstralDeep generates layouts but **never learns from them**; accepted vs. discarded arrangements, render-validity, and user reactions are not mined into anything.
- **Priority:** Medium-High (compounding novelty).
- **How to implement in AstralDeep:** AstralDeep can't finetune in-process, but it can run the *data half* of UICoder as a Python batch over `workspace_layout` history: for each past arrangement, compute automated signals (grammar-valid? F3 score? did the user reset it? did they interact?) and build a labeled corpus of {context → good/bad arrangement}. Use it now as **retrieval exemplars** (F7) and as the training set for the F14 scorer; later, optional external finetune. Zero runtime deps.
- **Novelty 4 / Impact 4 / Effort L**

### F14. Designer-feedback-as-critique learned scorer (beats RLHF ranking)
- **Source:** Apple ML Research — "Improving User Interface Generation Models from Designer Feedback," arXiv:2509.16779, 2025. https://machinelearning.apple.com/research/designer-feedback
- **What it is:** 21 designers gave ~1,500 **rich annotations** (comments, sketches, direct manipulation — not just ratings) on generated UIs; finetuning on this *annotation-as-rationale* signal beats rating/ranking RLHF because it matches how designers actually critique.
- **Frontier evidence:** Designer-annotation-tuned models outperformed ranking-feedback models and *all* baselines including GPT-5 on UI generation quality.
- **AstralDeep gap:** AstralDeep has no learned quality model at all, and no channel for rich (vs binary) feedback on arrangements. The existing component-feedback loop is thumbs-style, not rationale-rich.
- **Priority:** Medium.
- **How to implement in AstralDeep:** Extend the existing `feedback/` module to capture *structured* layout critique (which region is wrong + why, via the existing FeedbackControl) and use it to *fit the F3 weight vector* (a tiny logistic/linear model over penalty features — pure Python, no ML lib needed; closed-form least squares or hand-rolled gradient). This makes the deterministic scorer *learn* the right weights per the project's own designers/admins.
- **Novelty 3 / Impact 4 / Effort M**

### F15. Deterministic anti-dark-pattern lint over generated arrangements
- **Source:** "Deception at Scale: Deceptive Designs in 1K LLM-Generated Ecommerce Components," CHI 2026, arXiv:2502.13499; "Emergent Dark Patterns in AI-Generated User Interfaces," arXiv:2602.18445, 2026 (proposes DarkPatternDetector: UI heuristics + NLP + temporal signals).
- **What it is:** Empirical demonstration that LLMs inject **unsolicited deceptive patterns** (false urgency/countdowns, preselected opt-ins, confirmshaming, visual interference, hidden costs) into generated UIs *without being asked*, plus heuristic detectors to catch them.
- **Frontier evidence:** Across 1,000 generated e-commerce components, deceptive designs appear unprompted at scale; ChatGPT-generated sites implement dark patterns with no warning — i.e., generation *introduces* manipulation risk by default.
- **AstralDeep gap:** AstralDeep's designer can add **garnish components** (`dg_*`/`hero` CTAs, badges) and arrange emphasis — with **no check** that the arrangement isn't manipulative (e.g., a fabricated-urgency Badge, a pre-emphasized destructive CTA). The constitution covers code security, not *persuasion* safety.
- **Priority:** High (agentic security + UX trust).
- **How to implement in AstralDeep:** Add a pure-Python `lint_arrangement(tree)` that flags/strips dark-pattern signals in *designer-added* garnish: urgency language in Badge/Hero text not grounded in data, preselected/destructive CTAs given primary emphasis, confirmshaming copy, asymmetric visual weight on opt-in vs opt-out. Runs after the designer, before render; violations downgrade emphasis or drop the garnish. Audit as a new `workspace.dark_pattern_blocked` event. Deterministic, no new libs.
- **Novelty 4 / Impact 4 / Effort M**

### F16. Uncertainty / confidence surfacing as a UI primitive
- **Source:** "Addressing Uncertainty in LLM Outputs for Trust Calibration Through Visualization and User Interface Design," Visible Language, 2025 (proposes a Multiple-Agent-Validation-System with eight uncertainty-visualization options within text). Context: IEEE VIS 2025 workshop "Uncertainty Visualization: Unraveling Relationships of Uncertainty, AI, and Decision-Making."
- **What it is:** Systematic options for *visualizing confidence/uncertainty inline* in AI-generated content (e.g., highlight by confidence, source-validation badges, hedging markers), with guidance that surfacing uncertainty aids trust calibration but must be selective to avoid overload.
- **Frontier evidence:** Trust calibration improves when limitations of the model's data/results are *communicated*, and when users can interactively verify — but eight distinct encodings imply the *right* encoding is context-dependent.
- **AstralDeep gap:** AstralDeep renders agent outputs as confident, finished components with **no provenance or confidence signal** — a hallucinated MetricCard looks identical to a verified one.
- **Priority:** High (trust UX + safety).
- **How to implement in AstralDeep:** Add an optional `confidence`/`provenance` attribute to primitives (defaulting off) that the renderer turns into a subtle badge/border (verified-by-search vs model-asserted vs estimated), reusing the existing dashboard `Badge` primitive — no new primitive type needed initially. Agents/orchestrator set it when a value is grounded (e.g., from a tool result) vs. free-generated. ROTE can drop it on watch/voice. Surfaces uncertainty selectively per the source's "don't overload" caution.
- **Novelty 4 / Impact 4 / Effort M**

### F17. Mandatory fact-grounding gate for entity claims in components
- **Source:** Yaniv Leviathan, Dani Valevski et al. (Google), "Generative UI: LLMs are Effective UI Generators," 2026, arXiv:2604.09577 / https://generativeui.github.io.
- **What it is:** A production-grade Generative-UI pipeline whose system instructions make **fact verification via search MANDATORY for entities** — "all factual claims presented in the UI MUST be directly supported by search results" — plus a **post-processor stage** that fixes errors, escapes HTML, and resolves hallucinated assets after generation.
- **Frontier evidence:** Generative UI beats markdown by a wide margin (ELO 1736 vs 1438; preferred 82.8%, and 90.5% on information-seeking) and is comparable to human experts in ~50% of cases — *with* the mandatory grounding + post-processing discipline; quality is otherwise highly model-dependent (Gemini 2.0-Flash-Lite hit 60% error vs 0% for newer models).
- **AstralDeep gap:** AstralDeep has no rule that *entity facts surfaced in a component must trace to a tool/search result*; an agent (or the designer's garnish text) can assert unverified facts in a Hero/Card. No post-render asset/format sanity stage beyond escaping.
- **Priority:** High (safety + trust).
- **How to implement in AstralDeep:** (a) Policy: designer-/orchestrator-generated *text* in garnish components may not introduce new entity facts — only restate agent-provided data (lint as part of F15). (b) Encourage agents to populate the F16 provenance attribute from tool results so ungrounded facts are visibly flagged. (c) Add a small post-arrangement sanitizer pass (assets resolve, no fabricated links) alongside existing `esc()`. Pure policy + Python; aligns with the constitutional render layer.
- **Novelty 3 / Impact 5 / Effort M**

### F18. Gradual generation — intermediate customization layers (malleability via staged IRs)
- **Source:** "Gradual Generation of User Interfaces as a Design Method for Malleable Software," arXiv:2601.17975, 2026.
- **What it is:** Instead of one-shot generation, the UI is built through **ordered intermediate stages**, each exposing one customization *dimension* in its natural representation: Categories (natural language) → Layout (JSON schema) → Content (code) → Style (CSS variables). Users **rewind** to any stage to discover and tweak options, then proceed.
- **Frontier evidence:** Conceptual + 3 prototypes (no empirical study yet); the contribution is the *design method* — making customization **discoverable** by staging it, vs. a monolithic menu users can't navigate.
- **AstralDeep gap:** AstralDeep's malleability is "send another chat message"; there's **no staged, dimensional control surface** over an arrangement, so users can't discover *what* they're allowed to change (categories vs layout vs content vs style).
- **Priority:** Medium (malleability/novelty).
- **How to implement in AstralDeep:** Add a chrome surface that exposes the *layers* of the current arrangement as rewindable stages mapped to AstralDeep's stack: data/entities (F1 schema) → layout tree → component content → ROTE/style. Each stage edits at its own representation and re-renders downstream only (cheap, like PrototypeFlow's selective regen). Reuses chrome + `workspace_layout`; no new libs.
- **Novelty 4 / Impact 3 / Effort M**

### F19. Conceptual blending for novel arrangements (controlled exploration of the design space)
- **Source:** Apple ML Research — "Misty: UI Prototyping Through Interactive Conceptual Blending," UIST 2024, arXiv:2409.13900. https://machinelearning.apple.com/research/interactive-prototyping
- **What it is:** Applies cognitive-science **conceptual blending** to UI: rapidly combine aspects from multiple reference UIs/examples into a work-in-progress design, letting users specify intent at different prototyping stages and producing *serendipitous* blends that kickstart exploration.
- **Frontier evidence:** Study found blending helps developers start creative explorations and surfaces non-obvious combinations they wouldn't have prompted for.
- **AstralDeep gap:** AstralDeep's designer converges on *one* arrangement; it offers no *exploratory* mode that blends layout motifs from the user's history or from archetype templates to propose genuinely novel arrangements.
- **Priority:** Medium (novelty).
- **How to implement in AstralDeep:** Offer an opt-in "remix" action that blends the current arrangement with a retrieved past-accepted arrangement for a *different* archetype (F4/F7), generating 2–3 alternative canvases the user can pick from. This is multi-sample generation + the F3 scorer + the F7 retrieval store — all already proposed — repackaged as user-triggered exploration. No new deps.
- **Novelty 4 / Impact 3 / Effort M**

### F20. Ability-based runtime adaptation (accessibility as a first-class device profile)
- **Source:** Jacob O. Wobbrock et al., "Ability-Based Design," Communications of the ACM, 2018 (foundational); Ability-Based Design Mobile Toolkit (ABD-MT), 2024 (runtime ability-driven adaptation); SUPPLE (Gajos & Weld) decision-theoretic ability-adapted UI — 26% faster / 73% more accurate for motor-impaired users.
- **What it is:** Design *to the person's abilities* (vision, motor, attention), adapting the interface at runtime; SUPPLE proved decision-theoretic optimization can generate per-ability layouts with large measured gains.
- **Frontier evidence:** SUPPLE's ability-tailored UIs were 26% faster and 73% more accurate for users with motor impairments vs. default UIs — a landmark quantitative result.
- **AstralDeep gap:** ROTE adapts per **device**, not per **ability**. There is no low-vision / motor / reduced-motion / cognitive-load profile influencing primitive choice, density, target size, or garnish.
- **Priority:** Medium-High (UX inclusivity, differentiator).
- **How to implement in AstralDeep:** Add **ability profiles** to ROTE alongside device caps (larger tap targets + higher contrast + simplified density for motor/low-vision; reduced-motion drops animated garnish; cognitive-load-low caps components-per-canvas and prefers summary renders). Feed the profile into the F3 scorer weights and the F2 render directives. Persist per-user in `user_personalization`. This extends the constitutional ROTE layer — exactly where adaptation belongs — with no new libs.
- **Novelty 4 / Impact 4 / Effort M**

### F21. End-user-steerable personalization with interaction-data transparency
- **Source:** Diogo Alves, Carlos Duarte, Kyle Montague, Tiago Guerreiro, "Exploring the Role of Interaction Data to Empower End-User Decision-Making In UI Personalization," CHI 2026, DOI 10.1145/3772318.3791022 (keywords: Personalization, Agency, Democratization).
- **What it is:** Argues adaptive UIs should expose the **interaction data** that drives personalization to the end user, giving them **agency** over how the system adapts (review, approve, adjust) rather than opaque automatic adaptation.
- **Frontier evidence:** Positions interaction-data transparency + user decision-making as the corrective to autonomous-adaptation distrust (continues the long-standing "adaptive UIs erode predictability/control" critique).
- **AstralDeep gap:** AstralDeep's personalization/memory is **opaque** to the user — they can't see *why* a layout was chosen for them or steer the signal. No agency surface over adaptation.
- **Priority:** Medium (trust + control).
- **How to implement in AstralDeep:** A chrome surface showing the user the signals behind their current layout (interaction archetype detected, their three UI-preference dials from F7, the action-history summary from F11) with controls to adjust dials and prune signals. Pairs with the timeline chrome already present. Audit views as a `conversation`-class event. Pure chrome + existing tables.
- **Novelty 3 / Impact 3 / Effort M**

---

## Cross-cutting themes (for the synthesis)

1. **Generate a model, render the UI.** The frontier separates a typed task/data/intermediate representation from rendering (F1, F2, F4, F18, Athena/DuetUI). AstralDeep renders without modeling — closing this is the single highest-leverage change and is *constitutionally aligned* (it's "what to render," upstream of the render layer).
2. **Move judgment from the LLM to a deterministic, learnable scorer.** Draco/optimization + adaptive-reward + UICoder/designer-feedback all say: LLM *proposes*, code *scores/decides* (F3, F5, F8, F10, F13, F14). Fixes AstralDeep's documented weak-LLM/self-critique fragility and makes quality measurable.
3. **Conservative, planned adaptation with an explicit disruption cost.** F9/F10/F12 — stop redesigning unless net-beneficial vs the user's current learned layout. Cheapest high-impact UX/predictability win (Effort S).
4. **Safety & trust are UX, not afterthoughts.** Generated UIs leak dark patterns and false confidence by default (F15, F16, F17) — AstralDeep needs a persuasion-safety lint + provenance/uncertainty surfacing + entity-fact grounding.
5. **Evolve the closed palette inside a grammar + the existing approval pipeline.** F6/F18/F19 keep generation typed and discoverable; new primitives should ride AstralDeep's draft→self-test→admin-approval rails.

---

## Sources

- Cao, Jiang, Xia. "Generative and Malleable User Interfaces with Generative and Evolving Task-Driven Data Model." CHI 2025. https://dl.acm.org/doi/10.1145/3706598.3713285 · arXiv:2503.04084 https://arxiv.org/html/2503.04084
- Beason, Cheng, Schoop, Nichols. "Athena: Intermediate Representations for Iterative Scaffolded App Generation with an LLM." arXiv:2508.20263, 2025. https://arxiv.org/abs/2508.20263
- Chen et al. (Stanford SALT). "Generative Interfaces for Language Models." arXiv:2508.19227, 2025. https://arxiv.org/abs/2508.19227 · https://salt-nlp.github.io/generative_interfaces/
- Yang, Shrestha, Heer. "DracoGPT: Extracting Visualization Design Preferences from Large Language Models." IEEE VIS/TVCG 2024. arXiv:2408.06845 https://arxiv.org/abs/2408.06845
- Moritz et al. "Formalizing Visualization Design Knowledge as Constraints" (Draco). IEEE TVCG 2019. https://dl.acm.org/doi/abs/10.1109/TVCG.2018.2865240
- Oulasvirta et al. "Combinatorial Optimization of Graphical User Interface Designs." Proc. IEEE 2020.
- Dayama, Todi, Saarelainen, Oulasvirta. "GRIDS: Interactive Layout Design with Integer Programming." CHI 2020. https://userinterfaces.aalto.fi/grids/
- "AlignUI: A Method for Designing LLM-Generated UIs Aligned with User Preferences." arXiv:2601.17614, 2026. https://arxiv.org/abs/2601.17614
- Lu et al. "UI Layout Generation with LLMs Guided by UI Grammar." arXiv:2310.15455 (ICML 2023 SG workshop). https://arxiv.org/abs/2310.15455
- Todi, Bailly, Leiva, Oulasvirta. "Adapting User Interfaces with Model-based Reinforcement Learning." CHI 2021. arXiv:2103.06807 https://arxiv.org/abs/2103.06807 · https://dl.acm.org/doi/10.1145/3411764.3445497
- Langerak et al. "A comparative study on reward models for UI adaptation with reinforcement learning." Empirical Software Engineering, 2025. https://link.springer.com/article/10.1007/s10664-025-10659-5
- Horvitz. "Principles of Mixed-Initiative User Interfaces." CHI 1999. https://dl.acm.org/doi/10.1145/302979.303030
- "DuetUI: A Bidirectional Context Loop for Human-Agent Co-Generation of Task-Oriented Interfaces." arXiv:2509.13444, 2025 (UIST). https://arxiv.org/abs/2509.13444
- Apple ML Research. "UICoder: Finetuning LLMs to Generate UI Code through Automated Feedback." arXiv:2406.07739, 2024. https://machinelearning.apple.com/research/uicoder
- Apple ML Research. "Improving User Interface Generation Models from Designer Feedback." arXiv:2509.16779, 2025. https://machinelearning.apple.com/research/designer-feedback
- Apple ML Research. "Misty: UI Prototyping Through Interactive Conceptual Blending." UIST 2024. arXiv:2409.13900. https://machinelearning.apple.com/research/interactive-prototyping
- Leviathan, Valevski et al. (Google). "Generative UI: LLMs are Effective UI Generators." arXiv:2604.09577, 2026. https://generativeui.github.io
- "Deception at Scale: Deceptive Designs in 1K LLM-Generated Ecommerce Components." CHI 2026. arXiv:2502.13499 https://arxiv.org/abs/2502.13499
- "Emergent Dark Patterns in AI-Generated User Interfaces." arXiv:2602.18445, 2026. https://arxiv.org/abs/2602.18445
- "Addressing Uncertainty in LLM Outputs for Trust Calibration Through Visualization and User Interface Design." Visible Language, 2025. https://www.researchgate.net/publication/394515151
- "Gradual Generation of User Interfaces as a Design Method for Malleable Software." arXiv:2601.17975, 2026. https://arxiv.org/abs/2601.17975
- "Towards Human–AI Synergy in UI Design: Supporting Iterative Generation with LLMs" (PrototypeFlow). ACM TOCHI 2025. https://dl.acm.org/doi/10.1145/3773035 · arXiv:2412.20071 https://arxiv.org/html/2412.20071v3
- Wobbrock et al. "Ability-Based Design." Communications of the ACM, 2018. https://cacm.acm.org/research/ability-based-design/ · Ability-Based Design Mobile Toolkit (ABD-MT), 2024.
- Gajos, Weld et al. SUPPLE — decision-theoretic ability-adapted UI generation (CHI/IUI 2004–2010).
- Alves, Duarte, Montague, Guerreiro. "Exploring the Role of Interaction Data to Empower End-User Decision-Making In UI Personalization." CHI 2026. DOI 10.1145/3772318.3791022. arXiv:2603.19196
- Bandit context: contextual-bandit interface/layout personalization (Thompson sampling) — survey arXiv:2505.16918, 2025.
