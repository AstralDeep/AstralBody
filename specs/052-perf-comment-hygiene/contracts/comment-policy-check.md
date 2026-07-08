# Contract: Comment Policy Checker (`scripts/comment_policy.py`)

Stdlib-only (Python `tokenize` + `ast`; conservative string-aware line lexers for JS/CSS
and Kotlin). No runtime import from product code (CI/dev-side tool, Constitution XI
carve-out).

## CLI

```
python scripts/comment_policy.py --report [PATH...]   # full inventory, all categories
python scripts/comment_policy.py --check  [PATH...]   # mechanical rules only (CI gate)
python scripts/comment_policy.py --check --diff BASE  # adds directive-loss check vs git diff
```

- Default PATHs = the in-scope trees (backend py + static js/css, windows-client,
  android-client, scripts). Always excluded: `apple-clients/`,
  `backend/webrender/static/vendor/`, `backend/webrender/static/fonts/`, `.venv*`,
  generated artifacts, SQL seeds, Markdown.
- Exit codes: `0` clean; `1` violations (listed `path:line  RULE  excerpt`); `2` usage/
  internal error.

## `--check` rules (mechanical, CI-gating — decision D2)

| Rule | Definition |
|---|---|
| `missing-file-header` | file lacks a leading purpose docstring (py) / comment block (js/css/kt) |
| `banner` | comment matching `^[-=ـ_*#/ ]{8,}$` or `#/​/ ---- … ----` section-separator shapes |
| `dead-code` | ≥2 consecutive comment lines whose stripped content parses via `ast.parse` (py) / matches statement heuristics (js/kt) |
| `spec-marker` | `\b(T\d{3}|FR-\d{3}|US\d+)\b` inside any comment |
| `directive-loss` (diff mode) | a deleted line contained `noqa`, `type: ignore`, `pragma`, `fmt:`, isort/ruff/eslint directives, shebang, or encoding, and no adjacent added line preserves it |

Explicitly NOT gated: whether a surviving single-line comment qualifies as
"senior-dev rationale" — human review owns that judgment. `--report` lists all
`narration`-category comments to drive the sweep, but they never fail `--check`.

## Correctness requirements

- String literals containing `#`, `//`, or `/*` are not comments (tokenizer/lexer-based,
  never bare regex over raw lines).
- A line carrying both noise and a directive is treated as directive (protected).
- Shebang/encoding lines are never counted as missing-header violations or noise.
- Deterministic output ordering (path, line) for stable CI diffs.

## CI wiring (PR 2)

- New step in `.github/workflows/ci.yml` (lint job or sibling): `python
  scripts/comment_policy.py --check --diff origin/main`. Documented in the PR per
  Constitution XI tooling rules.
