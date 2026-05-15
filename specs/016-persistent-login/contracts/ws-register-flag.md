# Contract: WebSocket `register_ui` Resumed Flag

This feature adds one optional field, `resumed: boolean`, to the existing client→server `register_ui` WebSocket message.

## 1. Message shape (before & after)

### Before this feature

```json
{
  "type": "register_ui",
  "token": "<JWT>",
  "device": { /* device capabilities — feature ROTE */ }
}
```

### After this feature

```json
{
  "type": "register_ui",
  "token": "<JWT>",
  "device": { /* unchanged */ },
  "resumed": true | false   // NEW — optional, defaults to false
}
```

## 2. Field semantics

| Field | Type | Required? | Default | Meaning |
|-------|------|-----------|---------|---------|
| `resumed` | boolean | No | `false` | `true` iff this WS connection was established as part of a *silent* session resume (the OIDC `onSigninCallback` did **not** fire on this page load and the user was already authenticated from a stored credential). `false` for fresh interactive logins, anonymous connects, and any client that pre-dates this feature. |

## 3. Backward compatibility

- Clients that omit the field MUST be treated identically to clients sending `resumed: false`. This guarantees that older Flutter wrapper builds continue to work without an app update.
- Servers that pre-date this feature would silently ignore the unknown field (the existing `RegisterUI` dataclass is parsed permissively via dict-spread); we don't expect any production server to be older than the client because both ship from the same repo.

## 4. Frontend computation

The flag is computed by `frontend/src/auth/persistentLogin.ts`:

```ts
/**
 * Returns true iff the current authenticated state was reached without an
 * interactive Keycloak round-trip on this page load.
 *
 * Sources of truth:
 *   - `react-oidc-context`'s `auth.isAuthenticated`
 *   - The window-scoped flag set by `onSigninCallback` (sessionStorage,
 *     cleared on first read)
 */
export function wasSilentResume(auth: AuthContextProps): boolean {
  if (!auth.isAuthenticated) return false;
  const justInteractive = sessionStorage.getItem("astralbody.justInteractive") === "1";
  if (justInteractive) {
    sessionStorage.removeItem("astralbody.justInteractive");
    return false;
  }
  return true;
}
```

`onSigninCallback` sets `astralbody.justInteractive = "1"` just before stripping the `?code=…` from the URL; the first call to `wasSilentResume()` after that read-and-clears the flag. The semantics are: any subsequent reconnects within the same page lifetime that re-call `wasSilentResume()` return `true` (the user did not re-authenticate; they're still on the silent-resumed session).

## 5. Server-side handling

`backend/shared/protocol.py` — extend the `RegisterUI` dataclass:

```python
@dataclass
class RegisterUI:
    type: str
    token: str
    device: dict | None = None
    llm_config: dict | None = None        # existing — feature 006
    resumed: bool = False                  # NEW
```

`backend/orchestrator/orchestrator.py` WS register handler — pass `resumed` through to the audit hook (see [audit-actions.md](audit-actions.md) §2).

## 6. Privacy / security implications

- `resumed` does not carry any user identity, token material, or PII. It is a single boolean.
- Lying about `resumed` (e.g., a malicious client sending `resumed: false` when the credential was actually silently resumed) only affects the audit row's `action_type`; the JWT validation path is unchanged. A determined attacker has no incentive to lie about this — the JWT itself is the security boundary.

## 7. Tests

Frontend tests at `frontend/src/auth/__tests__/persistentLogin.test.tsx`:

- `wasSilentResume_returns_false_after_onSigninCallback`
- `wasSilentResume_returns_true_when_isAuthenticated_without_recent_callback`
- `wasSilentResume_returns_false_when_unauthenticated`

Backend tests covered in [audit-actions.md](audit-actions.md) §6.
