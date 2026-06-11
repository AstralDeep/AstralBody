# Contract: Agent Tool Registries (ml_services, web_research, summarizer)

All three agents follow the plug-and-play contract: `backend/agents/<name>/<name>_agent.py` (BaseA2AAgent subclass: agent_id, service_name, description, skill_tags, card_metadata), `mcp_server.py` (tools/list + tools/call), `mcp_tools.py` (`TOOL_REGISTRY: {name: {function, description, input_schema, scope}}`). Auto-discovered by `start.py`, registered under `AGENT_API_KEY` enforcement, scoped/audited/ROTE'd like every agent. UI built exclusively from astralprims primitives via `create_ui_response`.

## 1. ml_services (consolidates classify + forecaster + llm_factory)

- **agent_id**: `ml_services-1` · **service_name**: "ML Services" · **skill_tags**: machine-learning, classification, timeseries, embeddings, transcription (drops the routing-colliding bare "forecast" tag — weather keeps it).
- **card_metadata.required_credentials** (three optional bundles, existing key names): `CLASSIFY_URL`+`CLASSIFY_API_KEY`, `FORECASTER_URL`+`FORECASTER_API_KEY`, `LLM_FACTORY_URL`+`LLM_FACTORY_API_KEY`.
- **Shared foundation** `_wrapper.py`: credential probe, bounded retry shim (the formerly-duplicated mcp_server shim), `shared.external_http` egress-gated calls.

| Tool (final name) | Origin | Name change? |
|---|---|---|
| `classify_submit_dataset`, `classify_start_training_job`, `classify_get_job_status`, `classify_get_results`, `classify_delete_dataset` | classify | **prefixed** (collision set) |
| `set_column_types`, `get_ml_options`, `propose_training_config`, `get_output_log` | classify | unchanged |
| `forecaster_submit_dataset`, `forecaster_start_training_job`, `forecaster_get_job_status`, `forecaster_get_results`, `forecaster_delete_dataset` | forecaster | **prefixed** (collision set) |
| `set_column_roles` | forecaster | unchanged |
| `list_models`, `chat_with_model`, `create_embedding`, `transcribe_audio` | llm_factory | unchanged |
| `_credentials_check` | all three | unchanged name; dispatches per-bundle and reports three verdicts |

Input schemas, scopes, and output components are byte-compatible with the originals (modulo the tool-name field). `tool_overrides` rows for the five old shared names are remapped by the boot migration per their original agent (see data-model.md).

## 2. web_research (NEW)

- **agent_id**: `web_research-1` · **service_name**: "Web Research" · **skill_tags**: research, web, search, sources, brief.
- **card_metadata.required_credentials** (optional bundle): `SEARCH_API_URL`+`SEARCH_API_KEY` (operator/user-configured OpenAI-search-style or Tavily-compatible JSON endpoint). Absent ⇒ keyless DuckDuckGo HTML path.
- **Egress**: every fetch through `shared.external_http` (SSRF/private-host gating); response cap 1 MB; timeout 15 s; ≤ 5 fetches per `research_brief`.

| Tool | Input schema (required\*) | Output components |
|---|---|---|
| `web_search` | `query`\* (string), `max_results` (int, default 8, ≤ 20) | `Card(title=query)` + `List_(variant="detailed")` of {title, url, subtitle=snippet} |
| `fetch_page` | `url`\* (string) | `Card(title=page title)` + `Text(markdown)` extracted text (truncation notice when capped) |
| `research_brief` | `topic`\* (string), `depth` (enum shallow\|standard, default standard) | `Card` (brief w/ markdown synthesis citing [n] markers) + `Table(headers=[#, Source, Title, Retrieved])` of fetched sources + `Tabs` per sub-topic when ≥ 2 |

Failure contract: search backend unreachable/blocked ⇒ `Alert(variant="error")` naming the failed backend and the optional-credential remedy; the brief **never cites a URL it did not fetch** (no fabrication).

## 3. summarizer (NEW)

- **agent_id**: `summarizer-1` · **service_name**: "Summarizer" · **skill_tags**: summarize, digest, compare, tldr.
- **No credentials**; LLM via the per-session OpenAI-compatible client pattern (same resolution as `general`'s search-term extraction). Input cap ~24,000 chars with an explicit truncation `Alert(variant="info")` prepended when applied.

| Tool | Input schema (required\*) | Output components |
|---|---|---|
| `summarize_url` | `url`\* (string) | as `summarize_text` after an egress-gated fetch |
| `summarize_text` | `text`\* (string), `focus` (string, optional) | `Tabs`: TL;DR (Text markdown) / Key points (List_) / Notable quotes (List_) — first tab open |
| `compare_documents` | `text_a`\*, `text_b`\* (strings), `labels` (array[2], optional) | `Grid(columns=2)` of per-doc summary Cards + `Table` of key differences |

## Knowledge files (all three agents)

`backend/knowledge/capabilities/<agent>.md` + `backend/knowledge/techniques/<agent>.md` shipped in-repo (ml_services merges the three predecessors' files under per-service sections); `_index.md` rebuilt by the existing synthesis job.

## Removed-agent retirement guard (orchestrator-side contract)

`component_action` / pagination re-execution that resolves to an agent id absent from the registry AND present in the removed set returns `Alert(variant="warning", message="This capability was retired…")` to the requesting socket and records an `workspace.action_denied` audit event with `reason="agent_retired"` — never an unhandled dispatch failure.
