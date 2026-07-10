# Agent memory & personalization literature — findings

Survey of recent (2023–2026) scholarly work on LLM-agent memory, personalization, reflection, and self-improvement, mapped to gaps in AstralDeep's existing memory/"soul"/dreaming subsystem. Sources are primary scholarly venues (arXiv, NeurIPS, ICLR, ICML, AAAI, ACL/EMNLP). All implementation notes respect AstralDeep's constraints: **Python backend only, no new third-party runtime libraries (no new vector DB — reuse Postgres), embeddings only via the existing LLM client or computed simply, idempotent startup migrations.**

> Scope note: AstralDeep already has cross-session `memory_item`s, `short_term_signal`s, `user_personalization`, scheduled jobs, and a background "dreaming" `consolidation_sweep` that summarizes/condenses. This survey targets what is **beyond** a basic store + background summarizer: structured/linked memory, graph & multi-signal retrieval, conflict/temporal resolution, procedural skill memory, principled forgetting, sleep-time precompute, and evolving per-user personas.

---

## Executive summary

- **The frontier has moved from "store + summarize" to "store, link, reconcile, and self-organize."** Mem0 (Chhikara et al., 2025) and A-MEM (Xu et al., NeurIPS 2025) both replace passive append with an LLM-mediated *write path* that decides ADD/UPDATE/DELETE/NOOP and forms inter-memory links — AstralDeep's consolidation only condenses, it does not reconcile or interconnect. This is the single biggest gap and the highest-leverage upgrade.
- **Multi-signal retrieval (recency × importance × relevance) beats cosine-only**, and remains the influential Generative Agents (Park et al., 2023) recipe. AstralDeep almost certainly retrieves by similarity or recency alone; adding an importance score and a decay-weighted composite is a small, high-impact change implementable as Postgres columns + an `ORDER BY` expression.
- **Graph/associative retrieval (HippoRAG/HippoRAG2, Zep/Graphiti) wins multi-hop and "connect-the-dots" recall** — Personalized PageRank over an entity graph gives single-step multi-hop at 10–30× lower cost than iterative RAG. PageRank is ~40 lines of pure Python over Postgres-stored edges; no new dependency.
- **"Sleep-time compute" (Lin et al., 2025) is the academic formalization of AstralDeep's "dreaming," but with a sharper purpose**: precompute *anticipated* derived facts/answers during idle time, amortized across future queries, cutting test-time compute ~5× and raising accuracy 13–18%. AstralDeep's sweep condenses; it should *also* anticipate.
- **Procedural/skill memory is a near-total gap.** Voyager (Wang et al., 2023) skill libraries and Agent Workflow Memory (Wang et al., ICML 2025) induce reusable, self-verified routines from successful traces. AstralDeep has agentic creation (027/031) but no per-user library of validated *recipes* distilled from what actually worked — a natural extension of its existing draft-agent lifecycle.
- **Principled forgetting/decay is now a recognized quality + security lever, not just storage hygiene.** MemoryBank's Ebbinghaus curve (Zhong et al., AAAI 2024) and 2025–26 selective-forgetting frameworks tie decay to relevance/access/safety. For AstralDeep this doubles as PHI minimization and contradiction cleanup.
- **Contradiction resolution & temporal validity are first-class memory abilities** (LongMemEval ICLR 2025; Zep bi-temporal edges; Mem0 supersession). AstralDeep needs validity intervals and a "this fact superseded that one" mechanism to avoid serving stale user state.
- **Personalization is converging on an evolving, human-readable per-user persona that is itself optimized** (PersonaAgent NeurIPS 2025; PersonaMem-v2; T-POP 2025). AstralDeep has `user_personalization` rows but likely as static facts; the frontier treats the profile as a living artifact refined by simulating recent turns and lightweight thumbs-up/down feedback.
- **Demonstrated vs. speculative:** Mem0, A-MEM, Zep, HippoRAG/2, EM-LLM, MemoryOS, Voyager, AWM, Reflexion, MemGPT, Generative Agents are all *demonstrated* with public benchmarks. Sleep-time compute is demonstrated on stateful reasoning benchmarks but its application to conversational personalization is *promising/extrapolated*. Per-user RLHF and unlearning are *demonstrated in narrow settings*; their fit to AstralDeep is sound but unproven at this scale.

---

## Findings

### F1. LLM-mediated memory write path with ADD/UPDATE/DELETE/NOOP (Mem0)

- **Source:** Chhikara, Khant, Aryan, Singh, Yadav. *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory.* arXiv:2504.19413, 2025. https://arxiv.org/abs/2504.19413
- **What it is:** A two-phase memory pipeline. **Extraction:** feed a rolling conversation summary `S` + the last *m* messages to the LLM and extract salient candidate facts. **Update:** for each candidate, retrieve the top-*s* semantically similar existing memories and have the LLM issue one tool call per fact — `ADD` (new), `UPDATE` (augment), `DELETE` (contradicted/superseded), or `NOOP`. Contradiction handling is implicit: the LLM reasons over the semantic relationship and chooses DELETE+ADD to supersede. A graph variant (`Mem0^g`) stores entities as nodes and relations as labeled edges with explicit conflict detection.
- **Frontier evidence:** On LoCoMo, ~26% relative improvement in LLM-as-judge accuracy over OpenAI's memory product, **91% lower p95 latency** (1.44s vs 17.1s full-context), and **>90% token cost savings** (cited from paper).
- **AstralDeep gap:** `consolidation_sweep` condenses but does not *reconcile*. There is no mechanism that, on new information, decides to overwrite/delete a now-false `memory_item` ("user moved from Boston to Austin"). Memory grows monotonically and can serve stale facts.
- **Priority:** Highest.
- **How to implement in AstralDeep:** Add an LLM-driven write path invoked by the existing dreaming job (and/or per-turn for high-salience signals). For each candidate fact, retrieve top-*s* similar `memory_item`s (similarity via existing-LLM embeddings stored in a `BYTEA`/`float[]` column, or, if embeddings unavailable, a Postgres full-text/`pg_trgm` prefilter then LLM rerank), then a single constrained LLM call returns `{op, target_id, new_text}`. Apply as an `UPDATE`/soft-`DELETE` (set `superseded_by`, keep row for audit/provenance). All within the existing idempotent-migration + audit posture.
- **Novelty 4 / Impact 5 / Effort M**

### F2. Self-organizing linked memory notes with "memory evolution" (A-MEM)

- **Source:** Xu, Liang, et al. *A-MEM: Agentic Memory for LLM Agents.* arXiv:2502.12110, 2025 (NeurIPS 2025). https://arxiv.org/abs/2502.12110
- **What it is:** Each memory is a Zettelkasten-style *note* with structured attributes: original content `c`, timestamp `t`, LLM-generated **keywords** `K`, **tags** `G`, **contextual description** `X`, an embedding `e` (over `concat(c,K,G,X)`), and a set of **linked memory IDs** `L`. On insert: embed the note, retrieve top-*k* (≈10) neighbors by cosine, and prompt the LLM to decide which neighbors to **link** based on shared attributes. Crucially, "**memory evolution**": the new note can trigger the LLM to *rewrite the contextual description `X` and tags `G` of its neighbors* so older memories gain new meaning in light of the new one.
- **Frontier evidence:** On LoCoMo (GPT-4o-mini), A-MEM hits **45.85 multi-hop F1 vs 25.52 (MemGPT)** — ~2× — while using **~2,520 avg tokens vs ~17k** for baselines (~85% fewer). (Numbers from paper's Table.)
- **AstralDeep gap:** `memory_item`s are (almost certainly) flat and unlinked; there is no notion of an evolving knowledge network where new experience updates the interpretation of old experience. This is exactly the "smarter dreaming" AstralDeep wants.
- **Priority:** Highest.
- **How to implement in AstralDeep:** Extend `memory_item` with `keywords text[]`, `tags text[]`, `context text`, `embedding`, and a `memory_links` join table (`from_id, to_id, reason`). On consolidation, the dreaming job generates `K/G/X` via the existing LLM client, links to top-*k* neighbors, and runs a bounded "evolution" pass that may update neighbors' `context`/`tags` (write-through with audit, mirroring 028's supersede discipline). Graph links power F3 retrieval. No vector DB needed — store embeddings in Postgres and compute cosine in SQL or Python.
- **Novelty 5 / Impact 5 / Effort M**

### F3. Personalized-PageRank associative retrieval over an entity graph (HippoRAG / HippoRAG 2)

- **Source:** Gutiérrez, Shu, Gu, Yasunaga, Su. *HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs.* arXiv:2405.14831, 2024 (NeurIPS 2024). https://arxiv.org/abs/2405.14831 — and *From RAG to Memory: Non-Parametric Continual Learning for LLMs* (HippoRAG 2), arXiv:2502.14802, ICML 2025. https://arxiv.org/abs/2502.14802
- **What it is:** Build an open knowledge graph from OpenIE triples (LLM-extracted subject–relation–object) plus phrase nodes, passage nodes, and synonym edges. At query time, extract query phrases as **seed (reset) nodes** and run **Personalized PageRank** to propagate relevance through the graph; passages/memories are ranked by accumulated PageRank mass — giving *single-step multi-hop* retrieval. An LLM "recognition memory" filters spurious triples. HippoRAG 2 adds passage integration + recognition filtering and supports **non-parametric continual learning** (just insert new triples; no retrain).
- **Frontier evidence:** Up to **+20% over SOTA multi-hop QA** at **10–30× cheaper / 6–13× faster** than iterative retrieval (IRCoT); HippoRAG 2 adds **~7% over the best embedding model on associative memory** tasks (cited).
- **AstralDeep gap:** No graph memory and no associative ("connect facts the user never stated together") retrieval. Pure similarity misses multi-hop personal questions ("what gift would my partner like?" requiring partner→hobby→product hops).
- **Priority:** High.
- **How to implement in AstralDeep:** Reuse the F2 entity/link graph (or extract triples in the dreaming job). Store nodes/edges in two Postgres tables. Implement PageRank in pure Python (~40 lines: sparse adjacency from a query, power-iterate ~20 steps with restart toward seed nodes) — trivially within "no new deps." Seed nodes = entities the LLM extracts from the user's query; rank `memory_item`s by PageRank mass; feed top-k to the responding agent. Per-user graph isolation matches the existing tenancy model.
- **Novelty 4 / Impact 5 / Effort M**

### F4. Multi-signal retrieval score: recency × importance × relevance (Generative Agents)

- **Source:** Park, O'Brien, Cai, Morris, Liang, Bernstein. *Generative Agents: Interactive Simulacra of Human Behavior.* arXiv:2304.03442, 2023 (UIST 2023). https://arxiv.org/abs/2304.03442
- **What it is:** Retrieve memories by a weighted sum `score = α_recency·recency + α_importance·importance + α_relevance·relevance`, each min-max normalized to [0,1]. Recency = exponential decay since last access; importance = an LLM-rated **poignancy 1–10** stamped at write time; relevance = embedding cosine to the query. This beats cosine-only retrieval and is the canonical recipe still cited in 2025–26 work.
- **Frontier evidence:** Demonstrated as the core of believable long-horizon agents; ablations in the paper show all three signals matter; broadly replicated and extended (Mem0, A-MEM, MemoryBank all carry forward importance/recency ideas).
- **AstralDeep gap:** Likely single-signal retrieval (similarity or recency). No per-memory importance/poignancy score; no decay-weighted ranking; no "last accessed" bump.
- **Priority:** High (cheapest big win).
- **How to implement in AstralDeep:** Add `importance smallint` (LLM-rated 1–10 at write, one cheap call or batched in dreaming), `last_accessed_at`, and `access_count` to `memory_item`. Retrieval becomes an `ORDER BY` over a SQL expression combining `exp(-λ·age)`, normalized importance, and similarity. Tunable αs as config. Pure Postgres + one extra LLM rating per memory.
- **Novelty 2 / Impact 5 / Effort S**

### F5. Reflection trees: synthesize higher-order insights from raw memories (Generative Agents + Reflexion)

- **Source:** Park et al. 2023 (reflection), arXiv:2304.03442; and Shinn, Cassano, Berman, Gopinath, Narasimhan, Yao. *Reflexion: Language Agents with Verbal Reinforcement Learning.* NeurIPS 2023, arXiv:2303.11366. https://arxiv.org/abs/2303.11366
- **What it is:** When accumulated importance of recent events exceeds a threshold (150 in Generative Agents → ~2–3×/day), the agent (1) asks the LLM for the 3 most salient high-level questions over the last ~100 memories, (2) retrieves relevant memories per question, (3) asks the LLM to synthesize ~5 insights, **each citing the supporting memory IDs** (`insight (because of 1,5,3)`). Insights are stored as new memory nodes and can themselves be reflected upon → reflection trees. Reflexion generalizes the idea to *verbal* self-feedback stored in an episodic buffer to improve next-attempt behavior.
- **Frontier evidence:** Reflexion: **+22% AlfWorld, +20% HotPotQA, +11% HumanEval** over base agents via verbal self-reflection (no weight updates). Reflection is essential to Generative Agents' coherence (ablation).
- **AstralDeep gap:** Dreaming condenses/summarizes but does not generate *cited, queryable insight nodes* that abstract across memories, nor self-critiques of past agent behavior to improve future turns. Provenance-linked insights also strengthen the audit story.
- **Priority:** High.
- **How to implement in AstralDeep:** Add an `insight`-typed `memory_item` (or `kind` column) produced by a reflection step inside the dreaming job, triggered when summed `importance` of new `short_term_signal`s crosses a threshold. Store `cited_memory_ids int[]` for provenance (fits hash-chained audit). Insights are retrievable like any memory and can be re-reflected (recursion bounded by depth). Existing LLM client only.
- **Novelty 3 / Impact 4 / Effort M**

### F6. Sleep-time compute: anticipatory precompute during idle time (Letta)

- **Source:** Lin, Snell, et al. *Sleep-time Compute: Beyond Inference Scaling at Test-time.* arXiv:2504.13171, 2025. https://arxiv.org/abs/2504.13171
- **What it is:** Instead of doing all reasoning at query time, an offline process "thinks" about the user's context *before* queries arrive — anticipating likely questions and precomputing useful derived quantities, which are stored and reused. The precomputation amortizes across many related future queries. Distinct from speculative decoding: the generated tokens are kept regardless of the actual query.
- **Frontier evidence:** **~5× reduction in test-time compute** at equal accuracy on Stateful GSM-Symbolic / Stateful AIME; scaling sleep-time compute adds **+13% / +18% accuracy**; **2.5× lower avg cost per query** when amortized across related queries (Multi-Query GSM-Symbolic). Effectiveness correlates with query predictability.
- **AstralDeep gap:** Dreaming consolidates memory but doesn't *precompute anticipated answers/derived facts*. AstralDeep already has scheduled jobs and a background sweep — the infrastructure exists; the missing piece is the anticipatory objective.
- **Priority:** High (novelty + reuses existing scheduler).
- **How to implement in AstralDeep:** In the dreaming/scheduled-job path, after consolidation, run a bounded LLM pass that drafts "likely next questions for this user" + precomputed answers/derived facts, stored as a `precomputed_context` / cache table keyed by user + topic with TTL. At chat time, retrieve relevant precomputed items into context (cache-hit → faster, cheaper turn). Strictly additive, per-user isolated, idempotent. Mind PHI gate when persisting derived facts.
- **Novelty 5 / Impact 4 / Effort M**

### F7. Procedural skill library: store self-verified reusable routines (Voyager)

- **Source:** Wang, Xie, Jiang, Mandlekar, Xiao, Zhu, Fan, Anandkumar. *Voyager: An Open-Ended Embodied Agent with LLMs.* arXiv:2305.16291, 2023. https://arxiv.org/abs/2305.16291
- **What it is:** A skill library of **executable routines** keyed by an embedding of an LLM-generated description. A new skill is added only after a **self-verification** gate (the LLM-as-critic confirms the routine achieved the goal); failed attempts loop with environment/error feedback until success, then commit. Retrieval embeds the new task and pulls top-k skill code into context. Skills are **compositional** (skills call skills), compounding capability and resisting catastrophic forgetting.
- **Frontier evidence:** **3.3×** more unique items discovered vs AutoGPT; **15.3×/8.5×/6.4× faster** tech-tree milestones; only agent to reach diamond tools; strong zero-shot transfer to unseen tasks.
- **AstralDeep gap:** AstralDeep can *create agents* (027/031) but has no per-user/per-workspace library of distilled **recipes** ("the exact tool sequence + params that solved this kind of request before"), gated by a success check, retrieved for similar future requests. This is a different abstraction layer than draft-agent creation.
- **Priority:** High.
- **How to implement in AstralDeep:** New `skill_recipe` table: `description`, `embedding`, `tool_plan jsonb` (ordered tool/param template), `success_count`, `verified bool`, `parent_recipe_ids int[]`. The orchestrator, on a successful multi-tool turn, asks the LLM to abstract the trace into a parameterized recipe; gate behind a self-verification call before `verified=true`. On new requests, retrieve top-k recipes to prime the plan. Reuses the existing RFC-8693 attenuated-scope + audit gates on replay — security-aligned. No new deps.
- **Novelty 4 / Impact 4 / Effort L**

### F8. Workflow induction from successful trajectories (Agent Workflow Memory)

- **Source:** Wang, Mao, Fried, Neubig. *Agent Workflow Memory.* arXiv:2409.07429, 2024 (ICML 2025). https://arxiv.org/abs/2409.07429
- **What it is:** Induce **workflows** — common sub-routines abstracted from past *successful* trajectories with example-specific context removed — and selectively inject them to guide future generation. Works **offline** (induce from training traces) and **online** (induce from test queries on the fly), continually building more complex workflows atop earlier ones.
- **Frontier evidence:** Large success-rate gains on web agents (Mind2Web, WebArena) with substantially fewer steps; improves cross-task generalization. (AWM is the canonical "distill reusable procedure from traces" result.)
- **AstralDeep gap:** Same procedural gap as F7 but framed as *abstracted workflows from successful chat resolutions* rather than executable code — a cleaner fit for AstralDeep's tool-call traces (vs Minecraft code). No current mechanism turns "what worked" into reusable structure.
- **Priority:** Medium-High (pairs with F7; can ship as the online variant first).
- **How to implement in AstralDeep:** In the dreaming job (offline) and/or post-turn (online), summarize successful tool-call sequences into named workflow templates stored in Postgres; inject the top matching workflow's outline into the planner prompt for similar future requests. Dedup by a fingerprint like the 027 `gap_fingerprint`. Existing LLM + Postgres only.
- **Novelty 3 / Impact 4 / Effort M**

### F9. ExpeL-style cross-trajectory insight distillation (compare success vs failure)

- **Source:** Zhao, Wang, Lin, Wang, Zhang, Huang. *ExpeL: LLM Agents Are Experiential Learners.* AAAI 2024 (Oral), arXiv:2308.10144. https://arxiv.org/abs/2308.10144
- **What it is:** Gather success *and* failure trajectories into a pool, then extract natural-language **cross-task insights** (guidelines/constraints) by contrasting what differentiated wins from losses; also store successful trajectories for top-k recall at inference. Insights augment the agent's context — improvement without fine-tuning.
- **Frontier evidence:** Demonstrated gains on AlfWorld/WebShop/HotPotQA by adding distilled insights + retrieved exemplars; canonical "learn principles from experience" method cited across 2025–26 self-evolution surveys.
- **AstralDeep gap:** AstralDeep records audit trails of tool dispatches (success/failure) but never *mines* them for guidelines ("for this user, prefer agent X; this param value fails"). Failure signal is wasted.
- **Priority:** Medium.
- **How to implement in AstralDeep:** A periodic job reads recent audit/`job_run` outcomes (already structured: in_progress→success/failure with correlation_id) and asks the LLM to distill a small set of per-user or global insights into a `learned_insight` table, injected into planner/system context. Naturally leverages the existing audit substrate; per-user isolation preserved.
- **Novelty 3 / Impact 4 / Effort M**

### F10. Bi-temporal knowledge graph with validity intervals (Zep / Graphiti)

- **Source:** Rasmussen, Paliychuk, Beauvais, Ryan, Chalef. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* arXiv:2501.13956, 2025. https://arxiv.org/abs/2501.13956
- **What it is:** A temporally-aware memory graph (engine = Graphiti) where every edge carries **explicit validity intervals** and a **bi-temporal** model: when an event *occurred* vs when it was *ingested*. Fuses unstructured conversation + structured data; supports point-in-time queries and invalidation of edges that are superseded.
- **Frontier evidence:** Beats MemGPT on Deep Memory Retrieval (**94.8% vs 93.4%**); on **LongMemEval up to +18.5% accuracy with ~90% lower latency** vs full-context baselines (cited).
- **AstralDeep gap:** No temporal validity on memories. AstralDeep cannot answer "what did the user prefer *as of* March?" or correctly invalidate "user is vegetarian" when later they aren't. Stale facts leak.
- **Priority:** High.
- **How to implement in AstralDeep:** Add `valid_from`, `valid_to`, `ingested_at` to `memory_item` (and to F2/F3 edges). The F1 update path sets `valid_to` when a fact is superseded rather than hard-deleting. Retrieval filters to currently-valid (or as-of) facts in SQL. Pure schema + query change; strong synergy with F1/F11 and the audit/provenance requirement.
- **Novelty 3 / Impact 5 / Effort M**

### F11. Contradiction resolution & knowledge-update as a first-class ability (LongMemEval)

- **Source:** Wu, Zhu, Yang, Zhang, et al. *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory.* ICLR 2025, arXiv:2410.10813. https://arxiv.org/abs/2410.10813
- **What it is:** Defines five core long-term memory abilities to evaluate and engineer for: **information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention** (knowing when *not* to answer). Provides a unified indexing→retrieval→reading decomposition and shows commercial assistants drop ~30% accuracy across sustained interactions.
- **Frontier evidence:** Quantifies a **~30% accuracy cliff** on long-term memory for strong assistants; widely adopted as the evaluation target driving F1/F10-style designs.
- **AstralDeep gap:** No explicit handling of knowledge updates, temporal reasoning, or **abstention** (AstralDeep likely answers even when memory is insufficient/contradictory rather than saying "I'm not sure / which one?"). Abstention is also a safety/trust win.
- **Priority:** Medium-High.
- **How to implement in AstralDeep:** (a) Adopt LongMemEval categories as the internal test rubric for the memory subsystem. (b) Add an **abstention/clarify** branch: when retrieved memories conflict or are low-confidence, the responding agent asks a clarifying question (SDUI prompt) instead of guessing. (c) Resolve conflicts via the F1 supersede + F10 validity machinery. Evaluation harness aligns with feature 032's verification posture.
- **Novelty 2 / Impact 4 / Effort S–M**

### F12. Hierarchical tiered memory with heat-based promotion/eviction (MemoryOS / MemGPT)

- **Source:** Kang, Bai, et al. *Memory OS of AI Agent.* arXiv:2506.06326, 2025 (EMNLP 2025 Oral). https://arxiv.org/abs/2506.06326 — building on Packer, Fang, Patil, Lin, Wooders, Gonzalez. *MemGPT: Towards LLMs as Operating Systems.* arXiv:2310.08560, 2023. https://arxiv.org/abs/2310.08560
- **What it is:** OS-inspired three tiers — **short-term** (recent dialogue), **mid-term** (consolidated segments), **long-term personal** (durable persona/preferences). Short→mid promotion via a dialogue-chain FIFO; mid→long via a **segmented-page** organization with a **heat** signal (access frequency/recency/importance) deciding what gets promoted vs evicted. MemGPT supplies the paging/virtual-context metaphor (main vs external context, self-managed).
- **Frontier evidence:** MemoryOS: **+49.1% F1, +46.2% BLEU-1** over baselines on LoCoMo (GPT-4o-mini). MemGPT: demonstrated unbounded effective context for multi-session chat + doc analysis.
- **AstralDeep gap:** AstralDeep has `short_term_signal` + `memory_item` (≈2 tiers) but no explicit **heat-driven promotion** from short→long, and no clean separation of a durable *personal* tier from episodic facts. Promotion is implicit in the sweep, not principled.
- **Priority:** Medium.
- **How to implement in AstralDeep:** Add a `heat` score (access_count·recency·importance) to `short_term_signal`; the dreaming job promotes high-heat signals into durable `memory_item`s and lets low-heat ones decay (ties to F13). Designate a `user_personalization`-backed long-term *personal* tier separate from episodic memory. Pure scoring + scheduled movement in Postgres.
- **Novelty 2 / Impact 4 / Effort M**

### F13. Principled forgetting: Ebbinghaus/decay-based retention & pruning (MemoryBank + 2025–26 selective-forgetting)

- **Source:** Zhong, Guo, Gao, Ye, Wang, Li. *MemoryBank: Enhancing LLMs with Long-Term Memory.* AAAI 2024, arXiv:2305.10250. https://arxiv.org/abs/2305.10250 — plus selective-forgetting frameworks: e.g. *FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory*, arXiv:2601.18642, 2026; and Weibull-decay relevance modeling surveyed in *Governing Evolving Memory in LLM Agents (SSGM)*, arXiv:2603.11768, 2026.
- **What it is:** Apply the **Ebbinghaus retention curve `R = exp(-t/S)`** where memory strength `S` starts at 1 and **increments by 1 (reset `t=0`) each time the memory is recalled** — recalled memories persist; unused ones fade. Newer work (FadeMem) modulates decay by semantic relevance, access frequency, and recency, and adds **safety-triggered active forgetting**. Forgetting is reframed as an efficiency *and* quality *and* security lever.
- **Frontier evidence:** MemoryBank: demonstrated human-like recall/forgetting in the SiliconFriend companion. FadeMem: **~45% storage reduction** while retaining critical info (cited). 2026 frameworks tie active forgetting to GDPR-style data minimization.
- **AstralDeep gap:** Memory grows monotonically; no decay, no reinforcement-on-access, no principled pruning. For a **PHI-gated, fail-closed** system, *active forgetting of sensitive/stale data* is a security feature, not just hygiene.
- **Priority:** Medium-High (uniquely doubles as a security/compliance win).
- **How to implement in AstralDeep:** Add `strength real DEFAULT 1` and `last_accessed_at`; on each retrieval, `strength += 1, last_accessed_at = now()`. Compute `R = exp(-age/strength)`; the dreaming job soft-archives (or hard-deletes, audited) memories below an `R` threshold, with **safety-triggered** immediate forgetting for flagged PHI. Pure Postgres column updates + a sweep predicate. Integrates with audit + PHI gate.
- **Novelty 3 / Impact 4 / Effort S**

### F14. Human-inspired episodic segmentation by surprise (EM-LLM)

- **Source:** Fountas, Benfeghoul, Oomerjee, Christopoulou, Lampouras, Bou-Ammar, Wang. *Human-inspired Episodic Memory for Infinite Context LLMs.* ICLR 2025, arXiv:2407.09450. https://arxiv.org/abs/2407.09450
- **What it is:** Segment a token/interaction stream into coherent **episodic events** at points of high **Bayesian surprise** (large jump in model's predictive loss), then refine boundaries with graph-theoretic community detection. Retrieval is two-stage: k-NN over event representations **plus** a temporal-contiguity buffer (retrieve neighbors *and* what happened around them), mirroring human recall.
- **Frontier evidence:** Outperforms InfLLM across LongBench / ∞-Bench (e.g., **Retrieve.KV 90.2 vs 81.0** on InfiniteBench), scaling to **10M-token** retrieval; segmentation correlates with human-perceived event boundaries.
- **AstralDeep gap:** AstralDeep chunks memory by turn/session arbitrarily; no notion of *episodes* bounded by topic shifts, and retrieval ignores temporal contiguity (surrounding context of a recalled memory).
- **Priority:** Medium.
- **How to implement in AstralDeep:** Approximate surprise cheaply without logits: detect topic-shift boundaries via embedding distance between consecutive turns (threshold), grouping turns into `episode` rows. At retrieval, after the top-k semantic hits, also fetch each hit's adjacent memories in its episode (temporal-contiguity buffer) — a simple SQL window. Gives more coherent context with no new deps.
- **Novelty 3 / Impact 3 / Effort M**

### F15. Evolving, optimizable per-user persona prompt (PersonaAgent / PersonaMem-v2)

- **Source:** Zhang, et al. *PersonaAgent: Bridging Memory and Action for Personalized LLM Agents.* arXiv:2506.06254, 2025 (NeurIPS 2025). https://arxiv.org/abs/2506.06254 — and *PersonaMem-v2: Personalized Intelligence via Learning Implicit User Personas and Agentic Memory*, arXiv:2512.06688, 2025. https://arxiv.org/abs/2512.06688
- **What it is:** Treat a per-user **persona = a system prompt** as the mediator between memory and action: it draws on episodic + semantic personalized memory to steer tool choice, and action outcomes feed back to refine memory and persona. A **test-time alignment** loop *simulates the last n interactions*, compares simulated vs actual user responses, and optimizes the persona prompt via *textual* loss feedback (no weights). PersonaMem-v2 maintains a single **human-readable** memory that grows per user, capturing *implicitly revealed* preferences.
- **Frontier evidence:** PersonaAgent significantly outperforms personalization baselines across diverse tasks with test-time persona optimization (paper). PersonaMem-v2 benchmark: 1,000 users, 300+ scenarios, 20k+ preferences, 128k-token contexts, mostly implicit prefs.
- **AstralDeep gap:** `user_personalization` is (likely) a static fact store, not a *living, optimized persona prompt* injected to steer agent/tool selection, and AstralDeep probably captures only *explicit* preferences, missing implicit ones.
- **Priority:** High.
- **How to implement in AstralDeep:** Maintain `user_personalization.persona_prompt` (human-readable). In the dreaming job, run a bounded "persona refinement" pass: replay the last *n* turns, have the LLM critique where the current persona would have mispredicted, and emit an improved persona (textual loss, keep-best — mirrors the 029 UI-designer's converge/keep-best loop). Inject the persona into orchestrator/agent system context. Capture implicit prefs via F1's extraction. Existing LLM + Postgres; per-user isolated.
- **Novelty 4 / Impact 5 / Effort M**

### F16. Test-time personalization from lightweight preference feedback (T-POP)

- **Source:** *T-POP: Test-Time Personalization with Online Preference Feedback.* arXiv:2509.24696, 2025. https://arxiv.org/abs/2509.24696 (related: Poddar et al. VPL; PReF; *RLHF from Heterogeneous Feedback*, arXiv:2405.00254, 2024).
- **What it is:** Personalize at inference with **no retraining** by pairing *exploration* (sample diverse candidate responses) with *preference elicitation* (lightweight thumbs-up/down). Accumulated binary feedback builds an on-the-fly preference representation that steers subsequent generation. The broader line (VPL/PReF/meta-reward) models a user as a point in a low-dimensional latent preference space learnable from a handful of comparisons ("RLHF-of-one").
- **Frontier evidence:** T-POP shows preference-alignment gains over non-personalized baselines using only binary feedback, no annotation burden (paper). Meta/latent-preference methods demonstrate few-shot personalization without per-user overfitting.
- **AstralDeep gap:** AstralDeep has a component **feedback loop** (feature 004: thumbs/flags on components) but (likely) doesn't feed that signal back into *personalized generation/retrieval* — the feedback informs quality/quarantine, not per-user steering.
- **Priority:** Medium.
- **How to implement in AstralDeep:** Route the existing feature-004 feedback signals into a per-user preference summary (a few learned "this user prefers concise tables over prose" axes) stored in `user_personalization`, injected into the persona (F15). Optionally, for high-stakes turns, generate 2 candidates and let an implicit preference model pick — reusing existing feedback plumbing, no new deps.
- **Novelty 3 / Impact 3 / Effort M**

### F17. Memory provenance, editing & targeted unlearning (memory editing line)

- **Source:** Surveyed in *KnowledgeSmith: Uncovering Knowledge Updating in LLMs with Model Editing and Unlearning*, arXiv:2510.02392, 2025 (https://arxiv.org/abs/2510.02392); *Does Machine Unlearning Truly Remove Knowledge?*, arXiv:2505.23270, 2025; *Unlearning That Lasts*, arXiv:2509.02820, 2025. For *external* (non-parametric) memory, editing/unlearning reduces to record-level operations.
- **What it is:** The right to correct/forget specific facts. Critically, for **external memory** (AstralDeep's case) this is *tractable*: edit or delete the memory record, unlike costly parametric unlearning. The literature stresses verifying *true* removal (no residual leakage) and preserving unrelated utility.
- **Frontier evidence:** Parametric unlearning is shown to often *suppress rather than remove* knowledge (arXiv:2505.23270) — strong argument for keeping personal facts in editable external memory (where deletion is real) rather than fine-tuned weights.
- **AstralDeep gap:** No user-facing "forget this about me" / "that's wrong, fix it" operation over `memory_item`s; no provenance trail showing *why* a memory exists. Both are GDPR/PHI-relevant for a fail-closed, audited system.
- **Priority:** Medium-High (compliance + trust).
- **How to implement in AstralDeep:** Add a memory-management SDUI surface: list a user's memories with source provenance (which chat/turn — link to F5's `cited_memory_ids`), with edit/delete that writes through to Postgres and emits a hash-chained audit event (mirroring 028's `workspace.component_removed`). Because memory is external, deletion is genuine. Honor deletion in retrieval immediately. No new deps.
- **Novelty 3 / Impact 4 / Effort M**

### F18. A self-evolution roadmap frame: what/when/how to evolve, with Endure/Excel safety (survey)

- **Source:** Fang, Gao, et al. *A Survey of Self-Evolving Agents: What, When, How, and Where to Evolve on the Path to ASI.* arXiv:2507.21046, 2025. https://arxiv.org/abs/2507.21046 (companion list: *Awesome-Self-Evolving-Agents*).
- **What it is:** A taxonomy for agent self-improvement: **what** to evolve (model / **memory** / prompt / tools), **when** (intra-test-time online vs inter-test-time offline), **how** (reward-/feedback-/curriculum-driven optimizers), governed by safety principles — **Endure** (don't catastrophically forget / stay stable & safe) and **Excel** (improve without breaking alignment). Names Mem0/MemInsight (memory) and LearnAct/ExpeL (experience) as canonical components.
- **Frontier evidence:** Synthesizes the 2024–26 field; provides the conceptual scaffolding (encode → organize → retrieve → integrate → consolidate) used here to structure AstralDeep's upgrade path. Survey, not a single result.
- **AstralDeep gap:** AstralDeep evolves *memory* (dreaming) but not *prompts/tools/personas* systematically, and lacks explicit **Endure** guardrails on self-modification (a memory-poisoning / drift risk for an autonomous, fail-closed system — cf. SSGM, arXiv:2603.11768).
- **Priority:** Medium (organizing frame + a concrete safety control).
- **How to implement in AstralDeep:** Use the taxonomy to sequence F1–F17 (memory-evolution first, then persona/prompt evolution F15, then procedural/tool evolution F7/F8). Add an **Endure guardrail**: every self-modification (memory supersede, persona rewrite, recipe promotion) passes a validation/rollback gate + audit — directly reusing the 029 backup/rollback + security-gate pattern already in AstralDeep. Prevents memory poisoning and capability regression.
- **Novelty 2 / Impact 3 / Effort S (as policy) / M (full)**

---

## Sources

1. Park, O'Brien, Cai, Morris, Liang, Bernstein. *Generative Agents: Interactive Simulacra of Human Behavior.* UIST 2023. arXiv:2304.03442. https://arxiv.org/abs/2304.03442
2. Shinn, Cassano, Berman, Gopinath, Narasimhan, Yao. *Reflexion: Language Agents with Verbal Reinforcement Learning.* NeurIPS 2023. arXiv:2303.11366. https://arxiv.org/abs/2303.11366
3. Wang, Xie, Jiang, Mandlekar, Xiao, Zhu, Fan, Anandkumar. *Voyager: An Open-Ended Embodied Agent with LLMs.* 2023. arXiv:2305.16291. https://arxiv.org/abs/2305.16291
4. Packer, Fang, Patil, Lin, Wooders, Gonzalez. *MemGPT: Towards LLMs as Operating Systems.* 2023. arXiv:2310.08560. https://arxiv.org/abs/2310.08560
5. Zhong, Guo, Gao, Ye, Wang, Li. *MemoryBank: Enhancing LLMs with Long-Term Memory.* AAAI 2024. arXiv:2305.10250. https://arxiv.org/abs/2305.10250
6. Zhao, Wang, Lin, Wang, Zhang, Huang. *ExpeL: LLM Agents Are Experiential Learners.* AAAI 2024 (Oral). arXiv:2308.10144. https://arxiv.org/abs/2308.10144
7. Gutiérrez, Shu, Gu, Yasunaga, Su. *HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs.* NeurIPS 2024. arXiv:2405.14831. https://arxiv.org/abs/2405.14831
8. Gutiérrez, Shu, Qi, Zhao, Su. *From RAG to Memory: Non-Parametric Continual Learning for LLMs (HippoRAG 2).* ICML 2025. arXiv:2502.14802. https://arxiv.org/abs/2502.14802
9. Fountas, Benfeghoul, Oomerjee, Christopoulou, Lampouras, Bou-Ammar, Wang. *Human-inspired Episodic Memory for Infinite Context LLMs (EM-LLM).* ICLR 2025. arXiv:2407.09450. https://arxiv.org/abs/2407.09450
10. Wu, Zhu, Yang, Zhang, et al. *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory.* ICLR 2025. arXiv:2410.10813. https://arxiv.org/abs/2410.10813
11. Wang, Mao, Fried, Neubig. *Agent Workflow Memory.* ICML 2025. arXiv:2409.07429. https://arxiv.org/abs/2409.07429
12. Xu, Liang, et al. *A-MEM: Agentic Memory for LLM Agents.* NeurIPS 2025. arXiv:2502.12110. https://arxiv.org/abs/2502.12110
13. Chhikara, Khant, Aryan, Singh, Yadav. *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory.* 2025. arXiv:2504.19413. https://arxiv.org/abs/2504.19413
14. Rasmussen, Paliychuk, Beauvais, Ryan, Chalef. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* 2025. arXiv:2501.13956. https://arxiv.org/abs/2501.13956
15. Lin, Snell, et al. *Sleep-time Compute: Beyond Inference Scaling at Test-time.* 2025. arXiv:2504.13171. https://arxiv.org/abs/2504.13171
16. Kang, Bai, et al. *Memory OS of AI Agent.* EMNLP 2025 (Oral). arXiv:2506.06326. https://arxiv.org/abs/2506.06326
17. Zhang, et al. *PersonaAgent: Bridging Memory and Action for Personalized LLM Agents.* NeurIPS 2025. arXiv:2506.06254. https://arxiv.org/abs/2506.06254
18. *PersonaMem-v2: Towards Personalized Intelligence via Learning Implicit User Personas and Agentic Memory.* 2025. arXiv:2512.06688. https://arxiv.org/abs/2512.06688
19. *T-POP: Test-Time Personalization with Online Preference Feedback.* 2025. arXiv:2509.24696. https://arxiv.org/abs/2509.24696
20. *RLHF from Heterogeneous Feedback via Personalization and Preference Aggregation.* 2024. arXiv:2405.00254. https://arxiv.org/abs/2405.00254
21. Vishwakarma, Lee, Suresh, Sharma, Vishwakarma, Gupta, Chauhan. *Cognitive Weave: Synthesizing Abstracted Knowledge with a Spatio-Temporal Resonance Graph.* 2025. arXiv:2506.08098. https://arxiv.org/abs/2506.08098
22. Fang, Gao, et al. *A Survey of Self-Evolving Agents: What, When, How, and Where to Evolve.* 2025. arXiv:2507.21046. https://arxiv.org/abs/2507.21046
23. *KnowledgeSmith: Uncovering Knowledge Updating in LLMs with Model Editing and Unlearning.* 2025. arXiv:2510.02392. https://arxiv.org/abs/2510.02392
24. *Does Machine Unlearning Truly Remove Knowledge?* 2025. arXiv:2505.23270. https://arxiv.org/abs/2505.23270
25. *FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory.* 2026. arXiv:2601.18642. https://arxiv.org/abs/2601.18642
26. *Governing Evolving Memory in LLM Agents: Risks, Mechanisms, and the SSGM Framework.* 2026. arXiv:2603.11768. https://arxiv.org/abs/2603.11768

*Notes on evidence quality:* F1–F5, F7–F14 are demonstrated with public benchmarks (LoCoMo, LongMemEval, DMR, LongBench/∞-Bench, AlfWorld/WebArena/Mind2Web). F6 (sleep-time) is demonstrated on stateful reasoning benchmarks; its transfer to conversational personalization is a sound but unproven extrapolation. F15/F16 personalization results are demonstrated on personalization benchmarks but at smaller scale. F17 unlearning caveats are demonstrated for parametric models and *favor* AstralDeep's external-memory design. Numeric results are quoted from the cited papers' own abstracts/tables.
