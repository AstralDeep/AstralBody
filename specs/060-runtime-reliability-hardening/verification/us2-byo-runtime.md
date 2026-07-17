# US2 Personal-Agent Runtime Verification

**Feature**: 060 Runtime Reliability and Release Readiness
**Branch**: `060-runtime-reliability-hardening`
**Recorded**: 2026-07-16 (America/New_York)
**Environment**: Python 3.11, isolated PostgreSQL databases, and the Windows
host's platform-neutral frozen-runtime seams. No credentials or user-authored
source are included here.

## Durable runtime and adapter gates

The focused backend repository/generator/lifecycle gate completed with **55
passed in 2.38 seconds**:

| Surface | Passed |
|---|---:|
| Host, revision, runtime, process, request, operation, timeout, delete, and inventory fencing | 26 |
| Candidate activation, recovery, manifest, digest, and generated-child protocol | 26 |
| Host/bundle compatibility and final-lock pairing | 3 |

The production orchestration-adapter suite now passes **13 tests**. It proves
durable registration precedes host acknowledgement; inventory commits before
one complete action frame is sent; host loss commits before socket projections
are removed; database failure preserves those projections; result and
operation settlement precedes caller wake-up; long calls renew their selected
operation lease; watchdog transitions recheck PostgreSQL receipt-time startup
and liveness deadlines atomically; and deletion cleans the exact committed
tombstone before routes disappear or fenced stops are sent. The final adapter
tests also prove that host loss allocates a fresh recovery generation, re-opens
and re-hashes the exact immutable revision, sends it only to the durably
selected standby, makes a failed send retryable, and exposes one detached
immutable capability payload through both dashboard surfaces. The integrated
extensions also prove that lifecycle publication follows the committed
runtime/inventory authority boundary and that a generic operation still active
at two seconds records its phase durably before emitting the canonical status.

The final combined US2 backend regression gate passed **119 tests in 2.79
seconds**, including the repository, promotion, compatibility, immutable
artifact, protocol, and production-adapter suites. The two focused REST
dashboard capability checks passed separately.

The Windows BYO host and supervision gate passed **37 tests in 27.01 seconds**.
It exercises acknowledgement-before-inventory, complete v2 fences, immutable
installation, retained inventory, selected-only start, fresh process UUIDs,
heartbeat/exit propagation, packaged-worker boundaries, and the standalone
bounded supervisor without importing backend code.

The final packaged runtime lock is:

```text
6041036906881c59868b9e53e16d1e22d8371b68af2f36701022a5a239dd43ba
```

It is independently hashed and cross-asserted by the neutral fixture, backend
generator/manifest, Windows registration/host, and release package. A real
generated v2 child was also run as a subprocess; it registered with the exact
runtime fence and echoed only the valid full request/request-generation fence.

## Candidate-promotion fault matrix

The deterministic activation coordinator ran **108 trials**: nine boundaries,
12 trials per boundary. Every pre-commit failure retained the prior authority;
every post-commit failure retained the candidate authority. No trial exposed
two authorities or no durable authority.

| Boundary | Trials | Prior authority | Candidate authority | p95 ms | max ms |
|---|---:|---:|---:|---:|---:|
| `after_prepare` | 12 | 12 | 0 | 0.017 | 0.017 |
| `before_start` | 12 | 12 | 0 | 0.007 | 0.007 |
| `after_start` | 12 | 12 | 0 | 0.009 | 0.009 |
| `before_ready` | 12 | 12 | 0 | 0.007 | 0.007 |
| `after_ready` | 12 | 12 | 0 | 0.008 | 0.008 |
| `before_promote` | 12 | 12 | 0 | 0.008 | 0.008 |
| `after_promote_commit` | 12 | 0 | 12 | 0.014 | 0.014 |
| `before_prior_stop` | 12 | 0 | 12 | 0.010 | 0.010 |
| `after_prior_stop` | 12 | 0 | 12 | 0.010 | 0.010 |

The promotion transaction keeps `active_revision_id` and the old invocable
runtime unchanged until the exact candidate has registered, proved liveness,
reached ready, and committed promotion. Recovery follows the durable pointer;
preparation alone never retires the last-known-good runtime.

## Bounded-supervision fault matrix

The neutral corpus ran **700 trials**, 100 per condition. Every process tree
settled within five seconds and left zero residual children or captured-pipe
readers.

| Condition | Trials | p50 ms | p95 ms | max ms | Residuals |
|---|---:|---:|---:|---:|---:|
| crash | 100 | 0.038 | 0.066 | 0.074 | 0 |
| descendant quit | 100 | 10.656 | 20.673 | 22.813 | 0 |
| descendant stop | 100 | 1.615 | 1.652 | 1.661 | 0 |
| dual-stream high output | 100 | 0.150 | 0.179 | 0.214 | 0 |
| one-pipe EOF | 100 | 0.093 | 0.120 | 0.217 | 0 |
| oversized line | 100 | 0.058 | 0.073 | 0.084 | 0 |
| silent cancellation | 100 | 1.626 | 1.653 | 1.676 | 0 |

## Verdict

The repository, lifecycle, generator, host, and production adapter satisfy the
US2 fencing and failure invariants under the focused fault matrices: one
selected host/runtime authority, complete stale-frame rejection, prompt known
failure settlement, database-time hang detection, last-known-good promotion,
delete-first cleanup, retained-inventory reconciliation, exact runtime-contract
compatibility, and bounded process-tree cleanup. This is implementation and
local integration evidence, not a signed Windows artifact, public release, or
production deployment claim.
