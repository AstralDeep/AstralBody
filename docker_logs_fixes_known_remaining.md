# Pre-existing test failures NOT fixed in this round

This branch's `docker_logs.txt` triage was scoped to three issues:

1. Forecaster/classify retry-loop on tool-caught errors → fixed
2. Classify `start_training_job` Python `TypeError` on missing args → fixed
3. Keycloak token-exchange `invalid_scope` warning → fixed

While running the existing test suite to verify those fixes, I found additional failures that **already failed on the stashed working tree (no changes)**. They are unrelated to the three issues above and are out of scope here. Documenting them so they don't get lost.

## How "pre-existing" was verified

For each failure below: `git stash` → run the failing test → observe the same failure on a clean checkout of `015-external-ai-agents` at commit `bae690a` → `git stash pop`. None of these change behavior depending on my edits.

---

## 1. `tests/test_delegation.py::TestMockDelegationToken::test_creates_token`

```
AssertionError: assert 'DPoP' == 'Bearer'
  - Bearer
  + DPoP
tests\test_delegation.py:42
```

**What's happening**: the mock delegation token now returns `token_type="DPoP"` but the test asserts `"Bearer"`. The test was written before DPoP-binding was added to `_create_mock_delegation_token` in [backend/orchestrator/delegation.py:274](backend/orchestrator/delegation.py#L274).

**Why I left it**: a one-line fix to the assertion, but it touches the mock-mode contract, which is outside this branch's scope. Should be addressed by whoever owns feature 015's mock-auth path.

---

## 2. `tests/test_nefarious_delegation.py::TestPermissionToggle::*` (3–5 failures, run-dependent)

Sample failure:
```
AssertionError: assert False is True
 +  where False = is_tool_allowed('user-001', 'nefarious-1', 'write_user_notes')
 +    where is_tool_allowed = ToolPermissionManager.is_tool_allowed
tests/test_nefarious_delegation.py:311
```

Other variants in the same class:
- `test_toggle_off_blocks`
- `test_toggle_on_allows`
- `test_default_permissions_allow_none`
- `test_all_scopes_enabled_allows_all`
- `test_selective_revoke_only_affects_target`

**What's happening**: `ToolPermissionManager.is_tool_allowed` doesn't behave the way the test expects after `set_agent_scopes(...)`. The test sets scopes like `{"tools:read": True, "tools:write": True, "tools:search": False, "tools:system": False}` and then expects `is_tool_allowed(..., "write_user_notes")` to be `True` — but the manager returns `False`. Likely either:
- The tool→scope map for `nefarious-1` isn't registered in the test fixture (`register_tool_scopes` isn't called in this test file), so `get_tool_scope` returns the default `"tools:read"` and write tools get rejected. Or,
- The scope-to-tool mapping in [backend/orchestrator/tool_permissions.py](backend/orchestrator/tool_permissions.py) has drifted from what the test assumes.

The number of failures varies between runs (3 vs 5), which also hints at test-ordering / shared-state pollution between fixtures.

**Why I left it**: this is a permission-manager test-fixture issue, unrelated to the delegation-scopes / retry / required-arg fixes in this round. Needs a focused look at the fixture setup in `test_nefarious_delegation.py` — likely a missing `perm_manager.register_tool_scopes("nefarious-1", {...})` call before the assertions.

---

## What was actually verified in this round

- `pytest backend/agents/forecaster/tests/test_credentials_check.py backend/agents/classify/tests/test_credentials_check.py` → **82 passed** (no regressions).
- `pytest backend/tests/test_delegation.py backend/tests/test_nefarious_delegation.py --deselect TestMockDelegationToken::test_creates_token` → same set of TestPermissionToggle failures as on main, 25 other tests pass.

## Recommendation

File a separate ticket for each cluster. Both are quick fixes once someone scopes them, but bundling them into the docker-logs triage PR would blur the diff. Keeping this round narrowly focused on the three issues called out in `docker_logs.txt`.
