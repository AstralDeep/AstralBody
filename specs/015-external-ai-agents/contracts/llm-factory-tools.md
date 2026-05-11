# MCP Tool Contracts — LLM-Factory Agent

**Agent ID**: `llm-factory-1`
**Underlying service**: `llm-factory.ai.uky.edu` — an **LLM-Factory Router** deployment (OpenAI-compatible reverse proxy with usage analytics; see [LLM-Factory-Router-2](https://github.com/AstralDeep/LLM-Factory-Router-2)). URL is user-supplied.
**Auth**: `Authorization: Bearer <LLM_FACTORY_API_KEY>`
**Long-running tools**: *(none — all calls are synchronous)*

All tools below require `_credentials` carrying `LLM_FACTORY_URL` and `LLM_FACTORY_API_KEY`. Tools that touch user-uploaded files also require the orchestrator-injected `user_id` (the attachment resolver uses it to enforce per-user ownership).

---

## `list_models`

Synchronous. Returns the models served by the user's Router deployment (the Router discovers models dynamically from each backend's `/v1/models`).

**Input schema**: `{ "type": "object", "properties": {} }`

**Returns**:

```json
{
  "models": [
    {
      "id": "...",
      "object": "model",
      "owned_by": "vllm",
      "max_model_len": 8192,
      "permission": [...]
    }
  ]
}
```

The rendered card surfaces `id`, `owned_by`, and `max_model_len` per model when the upstream provides them.

---

## `chat_with_model`

Synchronous. Routes a chat completion through the user's chosen model via Router-2's `/v1/chat/completions` endpoint. The call uses `stream=false` so the Router returns a single JSON body with `choices[].message.content`.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "model_id": {"type": "string"},
    "messages": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "role": {"type": "string", "enum": ["system", "user", "assistant"]},
          "content": {"type": "string"}
        },
        "required": ["role", "content"]
      }
    },
    "options": {
      "type": "object",
      "description": "OpenAI-compatible options: temperature, max_tokens, stop, etc.",
      "additionalProperties": true
    }
  },
  "required": ["model_id", "messages"]
}
```

**Returns**:

```json
{ "content": "...", "model_id": "...", "usage": { "prompt_tokens": ..., "completion_tokens": ... } }
```

**Streaming** is a **documented future enhancement**, not current behavior. Router-2 supports SSE on this endpoint when called with `stream=true`, but the agent does not yet wire that through `ToolStreamData`. A follow-up may add it.

---

## `create_embedding`

Synchronous. Computes embedding vectors for a string or list of strings using a chosen embedding-capable model. Calls `POST /v1/embeddings` with the OpenAI-compatible body shape.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "model_id": {"type": "string"},
    "input": {
      "description": "A single string or a list of strings to embed.",
      "oneOf": [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}}
      ]
    }
  },
  "required": ["model_id", "input"]
}
```

**Returns**:

```json
{
  "embeddings": [[0.012, 0.034, ...], ...],
  "model_id": "...",
  "usage": { "prompt_tokens": ..., "total_tokens": ... },
  "dimension": <int>,
  "count": <int>
}
```

---

## `transcribe_audio`

Synchronous. Transcribes an uploaded audio file using a chosen transcription model (e.g. `whisper-1`). The agent resolves `file_handle` to an on-disk path via the AstralBody attachment helper (per-user ownership enforced) and POSTs the file as `multipart/form-data` to `/v1/audio/transcriptions`.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "model_id": {"type": "string"},
    "file_handle": {"type": "string", "description": "AstralBody attachment_id of the audio file."},
    "language": {"type": "string", "description": "Optional ISO-639-1 language hint, e.g. 'en' or 'fr'."}
  },
  "required": ["model_id", "file_handle"]
}
```

**Returns**: `{ "text": "...", "model_id": "...", "filename": "..." }`

---

## `_credentials_check` (internal)

Calls `GET /v1/models` against the user-supplied URL with the saved Bearer token. Router-2 always serves `/v1/models` when authentication succeeds, so there is no fallback path. Returns the standard verdict shape:

```json
{ "credential_test": "ok" }
{ "credential_test": "auth_failed", "detail": "<upstream message>" }
{ "credential_test": "unreachable", "detail": "<network error>" }
{ "credential_test": "unexpected", "detail": "<status code or parse failure>" }
```

---

## Error mapping

Identical mapping table as [classify-tools.md §Error mapping](classify-tools.md#error-mapping-all-tools), with "CLASSify" replaced by "LLM-Factory" in user-facing messages.

Note: because LLM-Factory has no long-running operations, there is no `status_unknown` terminal phase — the only retryable transport state is the per-call `service_unreachable`.
