# Release Trust Bootstrap Record (T120)

**Feature**: 060 Runtime Reliability and Release Readiness
**Branch**: `060-runtime-reliability-hardening`
**Recorded**: 2026-07-16 (America/New_York)
**Status**: pre-merge protections configured; checkpoint 1 (protected default-branch
landing) and checkpoint 2 (caller/required-check activation) remain open

This record contains no secret values, tokens, or credential material. All
identities below are public repository metadata.

## Trust model

Per the 2026-07-16 owner decision: no repository-scoped GitHub App,
installation token, or custom token broker exists or is planned. Every
mutating release-path job uses the built-in short-lived `GITHUB_TOKEN`
behind a protected environment with job-scoped permissions. Local evidence
preparation is diagnostic only (`protected_release_authorization: false`);
release authorization comes exclusively from the protected-CI decision job.

## Configured on 2026-07-16 (pre-merge layer)

### Protected environments

| Environment | ID | Required reviewer | Self-review |
|---|---|---|---|
| `release-publisher` | 18290265039 | `armstrongsam25` (user id 16158892) | permitted (solo-maintainer publish approval; the publisher has no requester/approver separation requirement) |
| `release-evidence-exception` | 18290265203 | `armstrongsam25` (user id 16158892) | **blocked** (`prevent_self_review: true`, layering the environment gate over the registrar job's own `requester_login != github.actor` refusal) |

Both environments were created with `can_admins_bypass: true` (GitHub default
for repository admins); the registrar and publisher jobs additionally verify
their own invariants in-job, so an admin bypass of the review gate cannot
bypass the requester/approver separation or the create-only ledger semantics.

### Protected debt ledger

- Ref: `refs/heads/release-evidence-debt`
- Root commit (orphan, README only): `7f6d609caa118c1cfceba2e6bba85dfec794b2a3`
- Ruleset `19078547` "protect release-evidence-debt ledger" (active): blocks
  deletion and non-fast-forward pushes. Appends remain possible only as
  fast-forward descendants; the registrar workflow adds exactly one previously
  absent `debts/<uuid>.json` or `resolutions/<uuid>.json` path per commit.

### Release tag protection

- Ruleset `19078549` "protect release tags" (active) on `refs/tags/v*`:
  blocks deletion, update, and non-fast-forward. Creation remains possible
  (the environment-approved publisher creates `v<release_version>` exactly
  once); no bypass actors.

### Pre-existing

- Ruleset `15015805` "stop push to main" (active) protects the default branch.

## Workflow identities (authored, awaiting protected landing)

The six workflows are tracked on the candidate branch and contract-tested by
`backend/tests/test_release_workflows_060.py`:

| File | `name:` | Authority |
|---|---|---|
| `.github/workflows/release-readiness.yml` | `release-readiness` | candidate jobs read-only; `protected-decision` job emits the decision |
| `.github/workflows/release-trusted-builder.yml` | `release-trusted-builder` | id-token/attestations write only (manifest attestation) |
| `.github/workflows/release-evidence-exception.yml` | `release-evidence-exception` | registrar job: environment-gated contents write (ledger append only) |
| `.github/workflows/release-windows.yml` | `Release Windows client` | bridge signer: contents/actions read + id-token write, no mutation |
| `.github/workflows/release-windows-publisher-controller.yml` | `release-windows-publisher-controller` | read-only verification; calls the publisher |
| `.github/workflows/release-windows-publisher.yml` | `release-windows-publisher` | `release-publisher` environment; the only contents-write release job |

## Remaining bootstrap steps

**Checkpoint 1 — protected default-branch landing.** Merge the reviewed
candidate (PR #143) to `main`, landing verifier
(`scripts/validate_release_evidence.py`), coverage policy
(`scripts/check_changed_coverage.py`), all three contract schemas, and the six
workflow files at one commit. Then record:

- `RELEASE_TRUSTED_BUILDER_SHA` (repo variable) = the main commit pinning
  `release-trusted-builder.yml`
- `RELEASE_TRUSTED_BUILDER_IDENTITY` (repo variable) = the builder's expected
  certificate identity
- `RELEASE_BRIDGE_WORKFLOW_SHA256` (repo variable) = SHA-256 of the
  `release-windows.yml` bridge bytes at that commit

**Checkpoint 2 — activation.** After the candidate branch rebases onto the
checkpoint-1 root: set repo variable `RELEASE_READINESS_ACTIVE=true` (enables
the vars-guarded `release-readiness` caller job in `ci.yml`), add the
`release-readiness / protected-decision` required check to the default-branch
ruleset, and add `release-readiness` to `ci.yml` `publish.needs` (tracked
comment marks the line).

**Staging prerequisites — DEFERRED ("won't set up", 2026-07-17):** the dedicated
persistent staging host will not be provisioned, so the qualifying readiness
matrix stays inactive and T111/T125/T128 are deferred. `stage-deploy` /
`stage-cleanup` were moved off the self-hosted runner to `ubuntu-latest`; they
target an external host at `ASTRAL_STAGING_ENDPOINT` that does not yet exist. To
activate later, provision that external host and supply:

- A persistent host with Docker and a non-loopback TLS ingress reachable from
  GitHub-hosted runners (a Cloudflare quick tunnel on that host provides the
  cert). A self-hosted runner is no longer required.
- Repository secrets for the staging gate
  (`ASTRAL_STAGING_ENDPOINT`, `ASTRAL_STAGING_PROBE_TOKEN`, digest-pinned
  `STAGING_POSTGRES_IMAGE`/`STAGING_KEYCLOAK_IMAGE`/
  `STAGING_SCHEMA_BASELINE_IMAGE`, `STAGING_RUNTIME_ENV_FILE`, DB/Keycloak
  credentials, `STAGING_BIND_PORT`) plus `ASTRAL_WINDOWS_SMOKE_TOKEN`,
  `ASTRAL_RELEASE_USERNAME`/`ASTRAL_RELEASE_PASSWORD`, and
  `ASTRAL_STAGING_ACCESS_TOKEN`

Local and candidate jobs cannot authorize an exception or publication: the
exception registrar and publisher run only behind the environments above, the
decision job's output is accepted only under the checkpoint-2 required-check
identity, and `scripts/validate_release_evidence.py` refuses `--decision-output`
outside the `protected-decision` job context.
