# Agentic-AI frameworks literature — findings

> Literature review (2024–2026, with a few seminal 2023 anchors) of agentic-AI
> frameworks, multi-agent orchestration, and self-improving/compound systems,
> mapped to GAPS in the **AstralBody** server-driven-UI agentic platform.
> Scope reminder — AstralBody already has: orchestrator→specialists routing, MCP
> tools, SDUI via astralprims→ROTE, a *single-agent* self-critique UI-design loop
> (the adaptive UI designer), and a *gap→auto-create draft agent* loop (codegen →
> self-test → security gate → admin approval). This survey targets what is
> **beyond** those three primitives. Constraints honored throughout: Python only,
> **no new third-party runtime libraries**, idempotent migrations, fail-closed.
>
> Priority lens (in order): **Novelty (paramount) > UX > device adaptation > agentic security.**
> Each finding carries Novelty 1–5 / Impact 1–5 / Effort S/M/L.

## Executive summary

- **Treat the agent fleet as an *optimizable graph*, not a fixed router.** GPTSwarm and DyLAN show the orchestrator→specialist topology can itself be *searched/learned* (edge optimization, agent-importance pruning) rather than hand-wired — the single biggest structural gap. (F1, F2)
- **The auto-create loop should *grow an archive and evolve*, not one-shot a draft.** ADAS/Meta-Agent-Search, AgentSquare (modular evolve+recombine + a *surrogate performance predictor* that skips bad designs before running them), and AFlow (MCTS over code-workflows with an operator library) turn AstralBody's gap→draft step into a cumulative, self-improving designer. The surrogate predictor is a near-free win: cut self-test cost by pre-scoring drafts. (F3, F4, F5)
- **Self-improvement can be made *empirically safe* by construction.** The Darwin-Gödel Machine pattern (propose self-modification → validate against a benchmark in a sandbox → keep an *archive* of stepping-stones, never a single line) is the principled version of AstralBody's "codegen→self-test→approve," and it maps cleanly onto the existing security gate. (F6)
- **Layered Mixture-of-Agents and Multi-Agent-Debate are cheap, drop-in quality multipliers** for hard chat turns — aggregate/critique across the *existing* specialists with zero new deps, gated by difficulty so cost stays bounded. (F7, F8)
- **Compound-system *optimization* (DSPy/MIPRO, TextGrad, MASS) is the rigorous successor to the ad-hoc UI-designer loop**: textual "backpropagation" of feedback and staged prompt+topology search give measurable, persisted improvement of any LLM step (UI design, narration, codegen prompts). (F9, F10, F11)
- **Evaluation must move from final-answer to *trajectory*.** Agent-as-a-Judge (judge that inspects intermediate steps/tool logs) plus τ-bench's `pass^k` reliability metric and a debiased LLM-judge protocol give AstralBody a real quality/regression harness for agents and self-tests. (F12, F13, F14)
- **Tool *creation + a retrieved, deduped tool library* (CRAFT / LATM / tool-makers) is the missing complement to per-gap agent creation** — abstract verified tool code into a reusable, multi-view-retrieved cache instead of regenerating per request. (F15, F16)
- **Procedural/episodic memory (CoALA) + experience-driven self-evolution turn "dreaming" from summarization into skill acquisition** — consolidate successful trajectories into reusable *procedures*, not just facts. (F17, F18)
- **Frontier-relevant security primitives exist now**: tool-dependency-graph defenses against indirect prompt injection, and explicit MAS attack taxonomies — directly hardening the auto-create + tool-dispatch surfaces AstralBody most exposes. (F19, F20)

---

## Findings

### F1. Agent fleet as an optimizable computational graph (node + edge optimization)
- **Source**: *GPTSwarm: Language Agents as Optimizable Graphs* — Zhuge, Wang, Kirsch, Faccio, Khizbullin, Schmidhuber. **ICML 2024 (Oral, top 1.5%)**. arXiv:2403.16713 / https://arxiv.org/abs/2403.16713
- **What it is**: Represents a whole multi-agent system as one computational graph: nodes = LLM/tool operations, edges = information flow; sub-graphs compose into agent hierarchies. Two automatic optimizers run: **node optimization** (refine each node's prompt) and **edge optimization** (change graph connectivity = who talks to whom), the latter learned via a policy over edge probabilities with task reward.
- **Frontier evidence**: Across MMLU, Mini-Crosswords, HumanEval, and GAIA, the optimizers "efficiently develop, integrate, and automatically improve" agents; edge optimization materially improves orchestration over hand-built graphs (per the Oral paper's ablations).
- **AstralBody gap**: The orchestrator hand-routes chat→specialist with static logic. Topology is fixed; there is no mechanism that *learns* which specialists should feed which, or prunes/adds edges per task class.
- **Priority**: P1 (structural, highest-novelty for routing).
- **How to implement in AstralBody**: Add an in-process `orchestrator/agent_graph.py` that models a turn as a small DAG over the ~10 existing specialists (nodes carry the MCP tool, edges carry passed context). Keep an **edge-weight table per task-fingerprint** (reuse the existing `gap_fingerprint`/chat-classification machinery) in a new idempotent `agent_graph_edge` table; update weights from turn outcomes (component-feedback signals + self-test pass/fail you already record). Start with a learned *selector* over a fixed candidate set (cheap, fail-open to current routing) before allowing edge add/remove. Pure Python; no new deps.
- **Novelty 5 / Impact 5 / Effort L**

### F2. Dynamic agent-team selection via an Agent Importance Score
- **Source**: *Dynamic LLM-Agent Network (DyLAN): An LLM-agent Collaboration Framework with Agent Team Optimization* — Liu, Zhang, Li, Yuan, Lee, Peng, et al. **COLM 2024**. arXiv:2310.02170 / https://arxiv.org/abs/2310.02170
- **What it is**: Instead of a fixed agent count/topology, DyLAN (a) runs an early "team optimization" pass that scores each candidate agent with an **unsupervised Agent Importance Score** (its marginal contribution to good answers), selects the top contributors, then (b) lets the chosen team collaborate in a feed-forward, dynamically-rewired network with early-stopping of unhelpful agents mid-task.
- **Frontier evidence**: On MMLU subjects, team optimization improves accuracy **up to +25.0%**; consistent gains on code generation, reasoning, and arithmetic vs. static multi-agent baselines.
- **AstralBody gap**: AstralBody always routes to *one* relevant specialist; there is no notion of dynamically *recruiting a small team* of specialists for a hard turn, nor of scoring which specialists actually helped.
- **Priority**: P1.
- **How to implement**: Reuse the F1 graph. For turns flagged "hard" (long, multi-tool, or low first-pass confidence), recruit the top-k specialists by an importance score computed from historical contribution (component-feedback + audit success rates), run a single feed-forward aggregation round, and early-stop specialists whose drafts the aggregator ignores. Bound k and rounds by config (mirror `UI_DESIGNER_MAX_ROUNDS`). Persist importance scores per task class.
- **Novelty 4 / Impact 4 / Effort M**

### F3. Automated Design of Agentic Systems (Meta-Agent Search over a growing archive)
- **Source**: *Automated Design of Agentic Systems* — Hu, Lu, Clune. arXiv:2408.08435 (2024) / https://arxiv.org/abs/2408.08435
- **What it is**: Defines agents *as code* and has a **meta agent** that iteratively *programs new agents* in a Turing-complete space, appending each discovery to an **ever-growing archive** it conditions on (open-ended, stepping-stone search). Invents novel building blocks, not just recombinations.
- **Frontier evidence**: Discovered agents "greatly outperform state-of-the-art hand-designed agents" across coding, science, and math, and the invented designs *transfer* across domains and across underlying models — evidence of robustness/generality.
- **AstralBody gap**: AstralBody's agentic-creation is *reactive and one-shot* (a gap triggers a single draft; success/failure isn't accumulated into a reusable design archive the creator learns from).
- **Priority**: P1 (directly upgrades the flagship auto-create loop; highest novelty).
- **How to implement**: Add a `draft_agent_archive` table (idempotent migration) recording every approved/rejected draft's *code + self-test score + gap fingerprint*. When `create_capability`/`extend_agent` fires, retrieve the top archived designs for similar gaps and pass them to the codegen LLM as in-context exemplars ("here are prior agents that worked/failed for similar gaps — improve on them"). This converts the existing flow into archive-conditioned open-ended search with zero new infra beyond a table and a retrieval query.
- **Novelty 5 / Impact 5 / Effort M**

### F4. Modular agent search with a surrogate performance predictor (skip bad drafts cheaply)
- **Source**: *AgentSquare: Automatic LLM Agent Search in Modular Design Space* — Shang, Li, Xu, et al. (Tsinghua FIB Lab). arXiv:2410.06153 (2024) / https://arxiv.org/abs/2410.06153
- **What it is**: Abstracts agents into four standardized-IO modules — **Planning, Reasoning, Tool-Use, Memory** — and searches the ~1050-combination space via **module evolution** (mutate a module) + **module recombination** (swap modules across designs). Critically, an **in-context surrogate "performance predictor"** scores a candidate design *before* full evaluation, so unpromising agents are skipped.
- **Frontier evidence**: **+17.2% average** over best-known human-designed agents across six benchmarks (web, embodied, tool-use, game); also yields interpretable design insights.
- **AstralBody gap**: (1) No modular abstraction of generated agents; (2) every draft is *fully run through self-test* (expensive VirtualWebSocket round) with no pre-screening.
- **Priority**: P1 — the surrogate predictor is a near-free efficiency win on the existing self-test pipeline.
- **How to implement**: Before kicking off the (costly) VirtualWebSocket self-test, call `_call_llm` with a cheap rubric prompt that scores the freshly generated draft code on a 0–1 "likely to pass self-test" scale given the gap + archived outcomes (F3); below a threshold, auto-refine *first* instead of running self-test, saving a full round. Optionally adopt the 4-module IO contract as the codegen template so drafts are recombinable. Reuses `_call_llm`; one config threshold.
- **Novelty 4 / Impact 5 / Effort S–M**

### F5. AFlow — MCTS over code-represented workflows with a reusable operator library
- **Source**: *AFlow: Automating Agentic Workflow Generation* — Zhang, Xiang, Yu, et al. **ICLR 2025**. arXiv:2410.10762 / https://arxiv.org/abs/2410.10762
- **What it is**: Reformulates workflow design as **Monte-Carlo Tree Search over code graphs** whose nodes are LLM calls connected by edges, using a small library of reusable **operators** (Generate, Format, Review/Revise, Ensemble, Test, Programmer) and tree-structured execution feedback to iteratively refine.
- **Frontier evidence**: **+5.7% average** over SOTA baselines across six datasets; enables *smaller* models to beat GPT-4o on specific tasks at **4.55% of the dollar inference cost**.
- **AstralBody gap**: The UI-designer loop is a *linear* multi-round critique; there is no search over alternative *workflow* structures, and no shared operator vocabulary for composing agent steps.
- **Priority**: P2.
- **How to implement**: Define a tiny Python operator set mirroring AFlow's (you already have Review/Revise = the designer's critique; Ensemble = MoA aggregation in F7; Test = self-test). For recurring complex chat task-classes, run a *bounded* MCTS (a few expansions, hard time budget like `UI_DESIGNER_TIMEOUT_SECONDS`) over operator compositions and cache the winning workflow per task-fingerprint. Fail-open to the current linear path.
- **Novelty 4 / Impact 4 / Effort L**

### F6. Darwin-Gödel Machine — empirically-validated self-modification with an archive (safety-by-construction)
- **Source**: *Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents* — Zhang, Hu, Lu, Lange, Clune (Sakana AI / UBC). arXiv:2505.22954 (May 2025) / https://arxiv.org/abs/2505.22954
- **What it is**: An agent that rewrites *its own code* (including its code-editing tools), then **empirically validates** each change against a benchmark instead of requiring a formal proof; keeps an **archive of stepping-stones** for open-ended exploration, all under **sandboxing + human oversight**.
- **Frontier evidence**: Self-improvement raised **SWE-bench 20.0%→50.0%** and **Polyglot 14.2%→30.7%**; demonstrates that empirical fitness + archive beats greedy single-line edits and avoids local optima.
- **AstralBody gap**: AstralBody *generates new agents* but does not let the orchestrator improve *its own* tools/prompts under an empirical-validation gate; and approval is single-shot, not archive-backed.
- **Priority**: P2 (high novelty; do strictly within the existing gate).
- **How to implement**: Apply the *pattern* to the agentic-creation subsystem (not to live orchestrator code): every self-modification proposal (new agent, or revised codegen/UI-designer prompt) must pass a **fixed empirical suite** (self-test + a held-out task set) inside the existing sandbox/security gate; only archive-improving deltas (F3) reach admin approval; humans remain the final approver (matches AstralBody's admin-only go-live). This is a governance/loop change, not new infra.
- **Novelty 5 / Impact 4 / Effort M**

### F7. Layered Mixture-of-Agents (cheap quality multiplier across existing specialists)
- **Source**: *Mixture-of-Agents Enhances Large Language Model Capabilities* — Wang, Wang, Athiwaratkun, Zhang, Zou. arXiv:2406.04692 (2024) / https://arxiv.org/abs/2406.04692
- **What it is**: Stacks LLM agents in **layers**: each layer's "proposer" agents independently answer, and the next layer's agents receive *all* prior-layer outputs as auxiliary context to synthesize an improved answer (final "aggregator" merges). Exploits the empirical finding that LLMs answer better when shown other models' answers ("collaborativeness of LLMs").
- **Frontier evidence**: **65.1% on AlpacaEval 2.0** with only open-source models, **beating GPT-4 Omni (57.5%)**; SOTA on MT-Bench/FLASK.
- **AstralBody gap**: A hard chat turn is answered by a single specialist/LLM call; no aggregation across the multiple capable models/specialists already present.
- **Priority**: P2 (very high impact-per-effort, zero new deps).
- **How to implement**: For difficulty-gated turns, fan a prompt to N proposers (could be the *same* model at varied temperatures, or different specialists), then a single aggregator `_call_llm` merges. Strictly bound N and layers (1 proposer-layer + 1 aggregator is enough) so latency/cost stay capped; reuse the existing client-factory. Surface as an internal step — output still flows through astralprims→ROTE unchanged.
- **Novelty 3 / Impact 5 / Effort S**

### F8. Multi-Agent Debate for factuality/reasoning (with sparse-topology cost control)
- **Source**: *Improving Factuality and Reasoning in Language Models through Multiagent Debate* — Du, Li, Torralba, Tenenbaum, Mordatch. **ICML 2024**. arXiv:2305.14325 / https://arxiv.org/abs/2305.14325. Cost control: *Improving Multi-Agent Debate with Sparse Communication Topology* — Li et al., **EMNLP 2024 Findings**. arXiv:2406.11776
- **What it is**: Multiple LLM instances independently answer, then **read each other's answers over several rounds and revise** toward a consensus; sparse-topology variants show most of the gains survive when each agent reads only a *subset* of peers, cutting tokens.
- **Frontier evidence**: Debate measurably improves factual accuracy and arithmetic/strategic reasoning over single-agent and self-consistency baselines; sparse topology preserves accuracy at lower cost.
- **AstralBody gap**: No mechanism for cross-checking a specialist's claim against an independent agent before it reaches the user — directly relevant to the medical/PHI and grant/factual specialists.
- **Priority**: P2 (UX trust + correctness).
- **How to implement**: A 2-agent, 1–2 round debate-then-judge wrapper, invoked only for *high-stakes/low-confidence* turns (e.g., medical agent), with a sparse (pairwise) topology to bound cost. The judge step can be the same Agent-as-a-Judge component (F12). Pure `_call_llm`.
- **Novelty 3 / Impact 4 / Effort S–M**

### F9. DSPy/MIPRO — compile-time optimization of LLM "programs" (prompts + demos)
- **Source**: *DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines* — Khattab, Singhvi, Maheshwari, et al. **ICLR 2024**. arXiv:2310.03714 / https://arxiv.org/abs/2310.03714 (optimizer: *MIPRO*, Opsahl-Ong et al., **EMNLP 2024**, arXiv:2406.11695)
- **What it is**: Express each LLM step as a declarative **signature/module**; a **compiler/optimizer** then bootstraps few-shot demonstrations and searches instructions to maximize a metric — replacing hand-tuned prompt strings with optimized, *measured* programs.
- **Frontier evidence**: Compiling in minutes let GPT-3.5/llama2-13b self-bootstrap pipelines beating expert few-shot prompting by **25–65%** and expert-written demos by **5–46%**.
- **AstralBody gap**: AstralBody's prompts (codegen security rules, UI-designer instructions, narration) are *hand-authored static strings* with no optimization or metric-driven improvement.
- **Priority**: P2.
- **How to implement**: You can't add the DSPy package (Constitution V), but you **port the technique**: a small in-house "prompt-program" registry where each critical prompt has (a) a metric (self-test pass rate, judge score, component-feedback), and (b) a periodic offline optimizer (a scheduled "dreaming"-style job) that proposes instruction/demonstration variants via `_call_llm`, A/B-scores them on a held-out task set, and persists the winner. Stays Python-only.
- **Novelty 4 / Impact 4 / Effort M–L**

### F10. TextGrad — "textual backpropagation" to optimize any compound-system component
- **Source**: *TextGrad: Automatic "Differentiation" via Text* — Yuksekgonul, Bianchi, Boen, Liu, Huang, Guestrin, Zou. **Nature (2025)** / arXiv:2406.07496 / https://arxiv.org/abs/2406.07496
- **What it is**: Treats natural-language LLM critiques as **gradients** and backpropagates them through a computation graph of LLM calls/tools, iteratively editing each "variable" (prompt, code, even molecules) to improve a downstream objective.
- **Frontier evidence**: Lifted GPT-4o GPQA zero-shot **51%→55%**, **+20% relative** on LeetCode-Hard; generalizes to code, QA, and even radiotherapy plans.
- **AstralBody gap**: The UI-designer's critique is *applied locally and discarded*; there's no general mechanism to turn LLM feedback into persisted edits across a multi-step chain (codegen→self-test→render).
- **Priority**: P2 (this is the rigorous generalization of the existing self-critique loop).
- **How to implement**: Implement a minimal `text_grad`-style helper: given a chain of LLM steps and a final critique, run one backward pass that asks the LLM to attribute the failure to specific upstream steps and emit targeted edits; apply, re-run, keep-if-better (mirrors the designer's keep-best convergence). Use it to auto-repair failed draft-agent codegen from self-test error text (you already feed errors back once — this makes it principled and multi-step). No new deps.
- **Novelty 4 / Impact 4 / Effort M**

### F11. MASS — staged search over prompts *and* topology (don't optimize them separately)
- **Source**: *Multi-Agent Design: Optimizing Agents with Better Prompts and Topologies* — Zhou, Hu, Mei, et al. (incl. Google authors). arXiv:2502.02533 (2025) / https://arxiv.org/abs/2502.02533
- **What it is**: **MASS** interleaves optimization stages — (1) block-level local prompt optimization, (2) workflow **topology** optimization over a pruned design space, (3) global workflow-level prompt optimization — finding that prompts and topology must be co-optimized; optimizing either alone underperforms.
- **Frontier evidence**: **78.8% (Gemini 1.5 Pro) / 74.3% (Flash)** average across reasoning/coding/long-context, beating a spectrum of prior MAS designs; consistent gains on Claude 3.5 Sonnet and Mistral Nemo.
- **AstralBody gap**: Even if AstralBody adds topology search (F1) and prompt optimization (F9) separately, the *joint* search and the "prune the topology space first" insight are missing.
- **Priority**: P3 (do after F1/F9 exist).
- **How to implement**: Sequence the optimizers you build for F9 (prompts) and F1 (edges): first optimize per-node prompts, then search edges over a *pruned* candidate set (only edges that helped historically), then a final global prompt pass. Run as an offline scheduled job; persist the best (prompts, topology) per task class.
- **Novelty 4 / Impact 4 / Effort L**

### F12. Agent-as-a-Judge — evaluate the *trajectory*, not just the final answer
- **Source**: *Agent-as-a-Judge: Evaluate Agents with Agents* — Zhuge, Zhao, Ashley, Wang, Khizbullin, et al. (Meta AI / KAUST). arXiv:2410.10934 (2024) / https://arxiv.org/abs/2410.10934
- **What it is**: An autonomous judge-agent with the *same* abilities as the agents it evaluates — it inspects **intermediate steps, tool-call logs, and reasoning**, pinpointing which requirements were met and which steps were efficient/correct, giving granular feedback instead of a single final-answer score.
- **Frontier evidence**: On the DevAI benchmark (55 dev tasks, 365 hierarchical requirements) it **dramatically outperforms LLM-as-a-Judge and matches human-evaluator reliability**, at a fraction of human cost/time.
- **AstralBody gap**: AstralBody's self-test checks *that an agent runs*, and component-feedback is user-facing; there is no automated judge that reads the **audit/tool-dispatch trajectory** to score correctness/quality of an agent run or a generated draft.
- **Priority**: P1 (gives the whole platform a quality + regression signal; feeds F1/F3/F9).
- **How to implement**: Build `orchestrator/agent_judge.py` that consumes the **hash-chained audit trail + correlation-id'd tool dispatch records you already persist** for a turn, and emits a structured rubric score (requirement coverage, tool-use correctness, safety adherence). Use it: (a) as the metric for F9/F10/F3, (b) as a richer self-test verdict, (c) for nightly regression over canned tasks. Pure Python over existing audit data.
- **Novelty 4 / Impact 5 / Effort M**

### F13. `pass^k` reliability metric + dual-control conversational eval (τ-bench / τ²-bench)
- **Source**: *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains* — Yao, Shinn, Razavi, Narasimhan (Sierra). arXiv:2406.12045 (2024) / https://arxiv.org/abs/2406.12045. Follow-up: *τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment* — Barres et al., arXiv:2506.07982 (2025).
- **What it is**: A methodology for evaluating tool-using *conversational* agents against **domain policy documents** with a simulated user, introducing **`pass^k`** — the probability an agent succeeds on *all k* independent trials — to measure **reliability/consistency**, not just average success. τ² adds *dual-control* (user can also act).
- **Frontier evidence**: SOTA function-calling agents (gpt-4o) succeed on **<50%** of tasks and are **inconsistent (`pass^8` < 25%** in retail) — exposing reliability as the real bottleneck.
- **AstralBody gap**: AstralBody has no reliability metric for its specialists/policy-adherence; self-tests are single-shot (pass^1), masking flakiness — exactly what τ-bench warns against.
- **Priority**: P2.
- **How to implement**: Add `pass^k` to the self-test harness: run each draft's self-test **k times** and require all-pass before go-live (cheap, directly raises deployed reliability). Build a small internal τ-style suite (simulated user + your domain "policy" = scope/permission rules) using the existing VirtualWebSocket; score policy adherence with F12's judge.
- **Novelty 3 / Impact 4 / Effort M**

### F14. Debiased LLM-as-a-Judge (position/verbosity/self-enhancement controls)
- **Source**: *Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge* — Shi, Sun, et al. arXiv:2406.07791 (2024) / https://arxiv.org/abs/2406.07791; plus the survey *From Generation to Judgment: A Survey on LLM-as-a-Judge* (arXiv:2411.15594, 2024).
- **What it is**: Catalogs and quantifies systematic judge biases — **position bias** (favoring first/last option), **verbosity/saliency bias**, **self-enhancement bias** (a model preferring its own outputs), bandwagon, etc. — and prescribes mitigations (swap-and-average positions, length normalization, judge ≠ candidate model).
- **Frontier evidence**: Position-bias study spans **15 judges and >150,000 evaluations** (MTBench/DevBench), showing rankings flip with option order — i.e., naive judging is unreliable.
- **AstralBody gap**: Any judge/self-critique AstralBody adds (UI-designer, F12, F8 debate-judge) will inherit these biases — especially **self-enhancement**, since the same LLM often generates *and* critiques.
- **Priority**: P2 (a correctness *guardrail* on every loop above).
- **How to implement**: Bake mitigations into the judge helper: for pairwise choices (e.g., keep-best in the UI designer, A/B prompt optimization), **average over both option orderings**; normalize for length; where feasible use a *different* configured model for judging than for generation. Trivial, deps-free, and protects every self-improving loop.
- **Novelty 3 / Impact 4 / Effort S**

### F15. CRAFT — create + retrieve from a deduped, multi-view tool library
- **Source**: *CRAFT: Customizing LLMs by Creating and Retrieving from Specialized Toolsets* — Yuan, Chen, Wang, Fung, Peng, Ji. **ICLR 2024**. arXiv:2309.17428 / https://arxiv.org/abs/2309.17428
- **What it is**: Builds a toolset of **diverse, reusable, validated code snippets** (abstracted from verified solutions, then deduplicated), and at inference uses **multi-view retrieval** (problem text + API name + docstring) to fetch the right tool — separating *tool creation* from *tool use* and making tools first-class, retrievable artifacts.
- **Frontier evidence**: Improves complex-reasoning task performance via reusable tools; the abstraction+dedup+multi-view-retrieval recipe is the reference design for a maintainable agent tool library.
- **AstralBody gap**: AstralBody creates whole *agents* on a gap, but has no notion of a **shared, retrievable library of verified tool functions** that agents draw from; capabilities aren't abstracted/deduped/reused across agents.
- **Priority**: P2.
- **How to implement**: Add a `tool_library` table storing verified MCP-tool code snippets keyed for **multi-view retrieval** (NL purpose, tool name, docstring) — populate it from *successful* generated agents (abstract their working tool code). On a new gap, *retrieve* before generating: if a library tool covers it, attenuate-scope and reuse it (cheaper than codegen, and it raises consistency). Fits the existing codegen+security-gate flow.
- **Novelty 4 / Impact 4 / Effort M**

### F16. LLMs as Tool-Makers (LATM) — a functional cache of generated tools
- **Source**: *Large Language Models as Tool Makers* — Cai, Wang, Ma, Chen, Zhou. arXiv:2305.17126 (2023) / https://arxiv.org/abs/2305.17126
- **What it is**: A closed loop where a strong "tool-maker" LLM writes a reusable Python utility for a *class* of requests once, caches it behind an API, and a cheaper "tool-user" LLM invokes the cached tool thereafter — a **functional cache** that stores *capability* rather than per-query text answers.
- **Frontier evidence**: GPT-4 maker + GPT-3.5 user matches GPT-4-for-both **at significantly lower cost**, by amortizing tool creation across many requests.
- **AstralBody gap**: Each capability gap triggers fresh codegen; there's no *functional cache* keyed by request-class so a once-made tool serves all future similar requests cheaply.
- **Priority**: P3 (complements F15/F3 — the caching discipline).
- **How to implement**: Key the F15 tool-library by **request-class fingerprint** (reuse `gap_fingerprint`); on a gap, check the functional cache first and only invoke the expensive maker path on a miss. Use a cheaper configured model as the "user" at runtime where appropriate. Idempotent table; no new deps.
- **Novelty 3 / Impact 4 / Effort M**

### F17. CoALA — modular memory (working/episodic/semantic/**procedural**) for agents
- **Source**: *Cognitive Architectures for Language Agents (CoALA)* — Sumers, Yao, Narasimhan, Griffiths. **TMLR 2024**. arXiv:2309.02427 / https://arxiv.org/abs/2309.02427
- **What it is**: A reference architecture giving agents distinct memory modules — **working** (context), **episodic** (past events/trajectories), **semantic** (facts), **procedural** (learned skills/code) — plus a structured internal/external action space and a propose→evaluate→select decision cycle.
- **Frontier evidence**: A widely-adopted organizing framework (TMLR) that frames why memory should be *typed*; the **procedural** memory type in particular formalizes storing reusable *skills*, not just facts.
- **AstralBody gap**: AstralBody's "soul"/memory consolidation centers on facts/preferences; it lacks an explicit **procedural memory** of *how to do tasks* (successful tool sequences/workflows) that future turns can replay.
- **Priority**: P2 (turns "dreaming" into capability growth — high UX leverage).
- **How to implement**: Extend the existing memory tables with a typed split; add **procedural memory** = canonicalized successful tool/workflow trajectories (you already have correlation-id'd dispatch logs). The orchestrator retrieves matching procedures for new turns ("last time this worked: tool A→B"), and the consolidation/"dreaming" job promotes high-reward trajectories into procedures. Reuses audit data + existing scheduler.
- **Novelty 4 / Impact 4 / Effort M**

### F18. Experience-driven self-evolution & the self-evolving-agents taxonomy (what/when/how/where to evolve)
- **Source**: *A Survey of Self-Evolving Agents: What, When, How, and Where to Evolve* — Gao, Jiang, et al. arXiv:2507.21046 (2025) / https://arxiv.org/abs/2507.21046; companion *A Comprehensive Survey of Self-Evolving AI Agents* arXiv:2508.07407 (2025). Primary instance: *EvolveR: Self-Evolving LLM Agents through an Experience-Driven Lifecycle*, arXiv:2510.16079 (2025).
- **What it is**: Frames lifelong agent improvement along four axes — **what** to evolve (prompts, memory, tools, topology), **when** (test-time vs offline), **how** (reflection, search, RL-free textual feedback), **where** (single-agent/multi-agent/domain). EvolveR instantiates a closed *distill-experience → store → retrieve → self-improve* lifecycle.
- **Frontier evidence**: The surveys map the field 2023→2025 and flag that *current systems optimize prompts/memory but stop short of safe autonomous evolution* — naming guardrails + evolution-success evaluation as open problems (which F6/F12/F14 address).
- **AstralBody gap**: AstralBody's consolidation evolves *user* memory but not the *agents/orchestrator* from accumulated task experience; there's no explicit experience-distillation lifecycle.
- **Priority**: P2 (the umbrella that organizes F3/F9/F10/F17 into one roadmap).
- **How to implement**: Add an offline "experience distillation" pass to the existing dreaming/consolidation scheduler: mine recent successful/failed turns (audit + judge scores), distill them into (a) procedural memories (F17), (b) archive exemplars (F3), (c) prompt-improvement candidates (F9) — each gated by F6/F12/F14. This is a *coordination* layer over features above; minimal new code.
- **Novelty 4 / Impact 4 / Effort M**

### F19. Tool-dependency-graph defense against indirect prompt injection (IPIGuard)
- **Source**: *IPIGuard: A Novel Tool Dependency Graph-Based Defense Against Indirect Prompt Injection in LLM Agents* — arXiv:2508.15310 (2025) / https://arxiv.org/abs/2508.15310 (context: survey *The Attack and Defense Landscape of Agentic AI*, arXiv:2603.11088).
- **What it is**: Plans a **Tool Dependency Graph** *before* execution — deciding which tool calls are legitimately needed and how data flows between them — so that injected instructions arriving in *tool/observation outputs* cannot spawn unплanned tool calls or redirect control flow. Separates *planning of tool use* from *consumption of tool data*.
- **Frontier evidence**: Substantially reduces attack success rate vs. reactive defenses while preserving task utility, by constraining the agent to a pre-authorized dependency graph rather than letting fetched content steer new actions.
- **AstralBody gap**: AstralBody's agents call MCP tools and ingest tool/web/attachment outputs; an indirect injection in fetched content (e.g., `web_research`/attachment parsers) could induce unintended tool calls. Defense today leans on RFC-8693 scope attenuation but not on a *pre-planned* tool-call graph.
- **Priority**: P2 (directly hardens AstralBody's most-exposed surfaces — security priority).
- **How to implement**: For multi-tool turns, have the orchestrator pre-plan the allowed tool-dependency graph (which tools, what data edges) *before* executing, then **refuse tool calls outside that pre-authorized graph** during execution — content fetched mid-turn can inform answers but cannot *add* tool calls. Layers naturally on top of the existing per-call scope gates and audit. Pure Python.
- **Novelty 4 / Impact 5 / Effort M**

### F20. Multi-agent-system attack taxonomy & red-teaming (threat model for the fleet)
- **Source**: *Agentic AI Security: Threats, Defenses, Evaluation, and Open Challenges* — arXiv:2510.23883 (2025) / https://arxiv.org/abs/2510.23883; *Red-teaming LLM Multi-Agent Systems via Communication Attacks* (**ACL 2025**); benchmark *TAMAS: Benchmarking Adversarial Risks in Multi-Agent LLM Systems*, arXiv:2511.05269 (2025).
- **What it is**: Systematizes MAS-specific attack surfaces absent from single-agent threat models — **inter-agent communication poisoning, agent impersonation, cascading/contagious prompt infection across agents, and tool-mediated privilege escalation** — with defenses (message provenance, capability scoping, monitoring) and adversarial benchmarks.
- **Frontier evidence**: These works demonstrate attacks that *only* exist once agents talk to each other (a single agent is safe; the *network* is exploitable) and provide benchmarks (TAMAS) to measure exposure — relevant the moment AstralBody adopts F1/F2/F7/F8 multi-agent flows.
- **AstralBody gap**: AstralBody's audit hash-chain and PHI gate are strong for *single*-agent dispatch, but as soon as specialists *collaborate* (F1/F2/F7/F8), inter-agent message integrity and contagion become unmodeled risks.
- **Priority**: P2 (must accompany any multi-agent adoption).
- **How to implement**: When enabling inter-agent flows, attach **provenance + integrity** to inter-agent messages (extend the existing audit chain to cover agent→agent edges), enforce per-edge capability scoping (RFC-8693 you already use), and add a small red-team suite (TAMAS-style canned attacks) to CI. Reuses audit + delegation infra.
- **Novelty 4 / Impact 5 / Effort M**

---

### Honorable mentions (verified, lower priority for AstralBody's current gaps)
- **LATS** (Zhou et al., **ICML 2024**, arXiv:2310.04406) — MCTS + reflection + LM value function unifying reasoning/acting/planning; 92.7% HumanEval pass@1. *Gap*: per-turn deliberate search; useful for the hardest single-agent turns but heavier than MoA/debate. (Novelty 3 / Impact 3 / Effort M)
- **Self-Discover** (Zhou et al., **NeurIPS 2024**, arXiv:2402.03620) — agent self-composes a task-specific reasoning structure from atomic modules; up to **+32% vs CoT at 10–40× less compute** than CoT-SC. Cheap drop-in for the planning step. (Novelty 3 / Impact 3 / Effort S)
- **ADaPT** (Prasad et al., **NAACL 2024 Findings**, arXiv:2311.05772) — recursive *as-needed* decomposition only when the executor fails; +28.3% ALFWorld. Maps to decomposing only hard chat turns. (Novelty 3 / Impact 3 / Effort M)
- **Reflexion** (Shinn et al., **NeurIPS 2023**, arXiv:2303.11366) — verbal self-reflection into episodic memory; 91% HumanEval. Foundational; AstralBody's single self-critique already approximates one Reflexion step — the gap is *persisting* reflections (covered by F17/F18). (Novelty 2 / Impact 3 / Effort S)
- **AgentVerse** (Chen et al., **ICLR 2024**, arXiv:2308.10848) — dynamic expert *recruitment* + emergent collaboration (volunteerism/conformity). Recruitment idea is subsumed by F2; emergent-behavior monitoring is a research curiosity for AstralBody. (Novelty 3 / Impact 3 / Effort M)
- **EvoMAC / Agentic Neural Networks** (arXiv:2410.16946, ICLR 2025; arXiv:2506.09046) — test-time **textual backpropagation** that spawns/retasks agents per task against compiler-verified feedback. A more aggressive cousin of F10 specialized to code; strong but higher-risk for a production gate. (Novelty 4 / Impact 3 / Effort L)
- **GTD / Guided Topology Diffusion** (arXiv:2510.07799, 2025) — graph **diffusion** generates task-adaptive, sparse, failure-robust topologies steered by a multi-objective proxy reward (accuracy/cost/sparsity). The frontier of F1, but diffusion-graph machinery is heavy for a no-new-deps Python codebase; track as future work. (Novelty 5 / Impact 4 / Effort L)
- **RouteLLM** (Ong et al., 2024, arXiv:2406.18665) — learned router between strong/weak LLMs from preference data; **>2× cost cut** at equal quality. AstralBody already has user-config LLM + model cascades partly; a *learned* difficulty router (reusing F2 difficulty signals) is the increment. (Novelty 3 / Impact 4 / Effort M)
- **Agent interoperability protocols survey** (Ehtesham et al., 2025, arXiv:2505.02279) — MCP/ACP/A2A/ANP comparison + phased adoption roadmap. AstralBody is MCP-native; **A2A capability "Agent Cards"** are the natural next step for *external* agent collaboration (feature 015 territory). (Novelty 2 / Impact 3 / Effort M)

---

## Sources

1. Zhuge, Wang, Kirsch, Faccio, Khizbullin, Schmidhuber. *GPTSwarm: Language Agents as Optimizable Graphs.* ICML 2024 (Oral). arXiv:2403.16713. https://arxiv.org/abs/2403.16713
2. Liu, Zhang, Li, Yuan, Lee, Peng, et al. *A Dynamic LLM-Powered Agent Network for Task-Oriented Agent Collaboration (DyLAN).* COLM 2024. arXiv:2310.02170. https://arxiv.org/abs/2310.02170
3. Hu, Lu, Clune. *Automated Design of Agentic Systems (ADAS / Meta-Agent Search).* arXiv:2408.08435 (2024). https://arxiv.org/abs/2408.08435
4. Shang, Li, Xu, et al. *AgentSquare: Automatic LLM Agent Search in Modular Design Space.* arXiv:2410.06153 (2024). https://arxiv.org/abs/2410.06153
5. Zhang, Xiang, Yu, et al. *AFlow: Automating Agentic Workflow Generation.* ICLR 2025. arXiv:2410.10762. https://arxiv.org/abs/2410.10762
6. Zhang, Hu, Lu, Lange, Clune. *Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents.* arXiv:2505.22954 (2025). https://arxiv.org/abs/2505.22954
7. Wang, Wang, Athiwaratkun, Zhang, Zou. *Mixture-of-Agents Enhances Large Language Model Capabilities.* arXiv:2406.04692 (2024). https://arxiv.org/abs/2406.04692
8. Du, Li, Torralba, Tenenbaum, Mordatch. *Improving Factuality and Reasoning in Language Models through Multiagent Debate.* ICML 2024. arXiv:2305.14325. https://arxiv.org/abs/2305.14325 — and Li et al. *Improving Multi-Agent Debate with Sparse Communication Topology.* EMNLP 2024 Findings. arXiv:2406.11776. https://arxiv.org/abs/2406.11776
9. Khattab, Singhvi, Maheshwari, et al. *DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines.* ICLR 2024. arXiv:2310.03714. https://arxiv.org/abs/2310.03714 — Opsahl-Ong et al. *Optimizing Instructions and Demonstrations for Multi-Stage LM Programs (MIPRO).* EMNLP 2024. arXiv:2406.11695. https://arxiv.org/abs/2406.11695
10. Yuksekgonul, Bianchi, Boen, Liu, Huang, Guestrin, Zou. *TextGrad: Automatic "Differentiation" via Text.* Nature 2025 / arXiv:2406.07496. https://arxiv.org/abs/2406.07496
11. Zhou, Hu, Mei, et al. *Multi-Agent Design: Optimizing Agents with Better Prompts and Topologies (MASS).* arXiv:2502.02533 (2025). https://arxiv.org/abs/2502.02533
12. Zhuge, Zhao, Ashley, Wang, Khizbullin, et al. *Agent-as-a-Judge: Evaluate Agents with Agents.* arXiv:2410.10934 (2024). https://arxiv.org/abs/2410.10934
13. Yao, Shinn, Razavi, Narasimhan. *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains.* arXiv:2406.12045 (2024). https://arxiv.org/abs/2406.12045 — Barres et al. *τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment.* arXiv:2506.07982 (2025). https://arxiv.org/abs/2506.07982
14. Shi, Sun, et al. *Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge.* arXiv:2406.07791 (2024). https://arxiv.org/abs/2406.07791 — Gu et al. *From Generation to Judgment: A Survey on LLM-as-a-Judge.* arXiv:2411.15594 (2024). https://arxiv.org/abs/2411.15594
15. Yuan, Chen, Wang, Fung, Peng, Ji. *CRAFT: Customizing LLMs by Creating and Retrieving from Specialized Toolsets.* ICLR 2024. arXiv:2309.17428. https://arxiv.org/abs/2309.17428
16. Cai, Wang, Ma, Chen, Zhou. *Large Language Models as Tool Makers (LATM).* arXiv:2305.17126 (2023). https://arxiv.org/abs/2305.17126
17. Sumers, Yao, Narasimhan, Griffiths. *Cognitive Architectures for Language Agents (CoALA).* TMLR 2024. arXiv:2309.02427. https://arxiv.org/abs/2309.02427
18. Gao, Jiang, et al. *A Survey of Self-Evolving Agents: What, When, How, and Where to Evolve.* arXiv:2507.21046 (2025). https://arxiv.org/abs/2507.21046 — *A Comprehensive Survey of Self-Evolving AI Agents.* arXiv:2508.07407 (2025). https://arxiv.org/abs/2508.07407 — *EvolveR: Self-Evolving LLM Agents through an Experience-Driven Lifecycle.* arXiv:2510.16079 (2025). https://arxiv.org/abs/2510.16079
19. *IPIGuard: A Tool Dependency Graph-Based Defense Against Indirect Prompt Injection in LLM Agents.* arXiv:2508.15310 (2025). https://arxiv.org/abs/2508.15310 — *The Attack and Defense Landscape of Agentic AI: A Comprehensive Survey.* arXiv:2603.11088. https://arxiv.org/abs/2603.11088
20. *Agentic AI Security: Threats, Defenses, Evaluation, and Open Challenges.* arXiv:2510.23883 (2025). https://arxiv.org/abs/2510.23883 — *Red-teaming LLM Multi-Agent Systems via Communication Attacks.* ACL 2025. — *TAMAS: Benchmarking Adversarial Risks in Multi-Agent LLM Systems.* arXiv:2511.05269 (2025). https://arxiv.org/abs/2511.05269
21. Zhou, Yan, Shlapentokh-Rothman, Wang, Wang. *Language Agent Tree Search (LATS).* ICML 2024. arXiv:2310.04406. https://arxiv.org/abs/2310.04406
22. Zhou et al. *Self-Discover: Large Language Models Self-Compose Reasoning Structures.* NeurIPS 2024. arXiv:2402.03620. https://arxiv.org/abs/2402.03620
23. Prasad, Koller, Hartmann, Clark, Sabharwal, Bansal, Khot. *ADaPT: As-Needed Decomposition and Planning with Language Models.* NAACL 2024 Findings. arXiv:2311.05772. https://arxiv.org/abs/2311.05772
24. Shinn, Cassano, Gopinath, Narasimhan, Yao. *Reflexion: Language Agents with Verbal Reinforcement Learning.* NeurIPS 2023. arXiv:2303.11366. https://arxiv.org/abs/2303.11366
25. Chen, Su, et al. *AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors.* ICLR 2024. arXiv:2308.10848. https://arxiv.org/abs/2308.10848
26. Hu et al. *Self-Evolving Multi-Agent Collaboration Networks for Software Development (EvoMAC).* ICLR 2025. arXiv:2410.16946. https://arxiv.org/abs/2410.16946 — *Agentic Neural Networks: Self-Evolving Multi-Agent Systems via Textual Backpropagation.* arXiv:2506.09046 (2025). https://arxiv.org/abs/2506.09046
27. *Dynamic Generation of Multi-LLM Agents Communication Topologies with Graph Diffusion Models (GTD).* arXiv:2510.07799 (2025). https://arxiv.org/abs/2510.07799
28. Ong, Almahairi, Wu, Chiang, Wu, Gonzalez, Kadous, Stoica. *RouteLLM: Learning to Route LLMs with Preference Data.* arXiv:2406.18665 (2024). https://arxiv.org/abs/2406.18665
29. Ehtesham, Singh, Gupta, Kumar. *A Survey of Agent Interoperability Protocols: MCP, ACP, A2A, ANP.* arXiv:2505.02279 (2025). https://arxiv.org/abs/2505.02279
