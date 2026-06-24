# Contract: User-Typed Slash Commands

## Registry (orchestrator/slash_commands.py)

A curated, first-party registry. Each command:

```python
SlashCommand(
    name: str,                 # e.g. "summarize" (invoked as /summarize)
    kind: "prompt_expand" | "flow",
    description: str,          # shown in discovery/help
    usage: str,                # e.g. "/summarize <url|text>"
    required_scopes: list[str],# scopes the resulting action needs (informational; enforcement is via is_tool_allowed)
    handler,                   # prompt_expand: builds a prefilled prompt; flow: a callable that drives a defined sequence
)
```

Initial curated set (final list confirmed in tasks.md): `/help`, `/agents`, `/summarize`, `/research`, `/weather`.

## Parse + route (api.py / chat_steps.py ingress)

When `FF_SLASH_COMMANDS` is on and a chat message's first token starts with `/`:

1. Look up the command by name.
2. **Unknown / malformed** → return a friendly chrome message (list nearest/available commands); do NOT error, do NOT silently send as a tool call.
3. **`prompt_expand`** → rewrite into a normal prefilled model turn (the rest of the message becomes the argument); the turn then proceeds through the standard ReAct loop and all gates.
4. **`flow`** → invoke the defined sequence; every tool it calls passes through `is_tool_allowed` (scopes/overrides honored), audit (`ToolDispatchAudit`), and the PHI/taint/policy handling — no privileged bypass.
5. Command text and arguments are treated as **untrusted input** (same PHI/taint/policy/permission handling as any chat message).

A leading `/` that does not match a command and is not plausibly a command (e.g. ordinary text) is passed through as a normal message — fail-open. If parsing raises, the input is treated as a normal message.

## Discovery (server-driven UI)

- The chat input (`webrender/templates/shell.html` + `static/client.js`) shows a typeahead menu when the user types `/`, listing command names + usage. Server-rendered; ROTE-adapted; no new client framework.
- `/help` (and a commands chrome surface) lists available commands and usage.

## Invariants (MUST hold)

- Gated by `FF_SLASH_COMMANDS`. Off → `/`-prefixed messages are ordinary chat messages (today's behavior).
- No command grants a permission the user does not already have via scopes; the gate is `is_tool_allowed`, unchanged.
- Every command invocation is audited like any other turn.
- The surface is SDUI (Principle II); arguments are validated/untrusted (Principle VII).
