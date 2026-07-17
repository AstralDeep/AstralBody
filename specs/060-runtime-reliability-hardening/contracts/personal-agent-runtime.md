# Contract: Personal-Agent Host, Revision, and Runtime Fencing

**Scope**: FR-009–FR-018, FR-032, FR-058; SC-003, SC-004, SC-020–SC-022
**Supersedes for 060 behavior**: the unfenced lifecycle portions of feature 057/058 contracts.
Their owner-bound authenticated UI tunnel and existing authorization path remain unchanged.

## 1. Runtime contract version

Feature 060 defines `BYO_RUNTIME_CONTRACT_VERSION = 2`. A bundle manifest declares one integer
`runtime_contract_version`; a host advertises a non-empty array `supported_runtime_contract_versions`
and its 64-lowercase-hex `runtime_lock_sha256`. Version 2 hosts and bundles also carry every identity
in the fence below. An implicit/legacy version is version 1 and is not silently treated as version 2.

Compatibility is evaluated before delivery and again at registration. The bundle version must be
in the host's supported set and its `required_runtime_lock_sha256` must match the installed packaged
runtime lock. The server returns within **2 seconds**:

- `runtime_contract_unsupported` with required/supported version numbers; or
- `runtime_lock_mismatch` with only expected/actual digest prefixes (12 hex characters), never
  package paths, source, or credentials.

Supported old/new combinations are enumerated in release tests. An incompatible combination is a
passing compatibility result only when it produces the declared prompt refusal; timeout is never a
compatibility result.

The exact v2 refusal envelope is `agent_host_registration_refused`. It never contains a session ID
and therefore never makes the connection eligible:

```json
{
  "type": "agent_host_registration_refused",
  "code": "runtime_contract_unsupported",
  "retryable": false,
  "details": {
    "required_runtime_contract_version": 2,
    "supported_runtime_contract_versions": [1]
  },
  "refused_at": "2026-07-15T18:41:00Z"
}
```

For `runtime_lock_mismatch`, `details` is exactly
`{"expected_sha256_prefix":"0123456789ab","actual_sha256_prefix":"fedcba987654"}`.
For a syntactically invalid structured registration, `code` is
`invalid_host_registration`, `retryable` is false, and `details` is exactly
`{"field":"<safe canonical field name>"}`; it never echoes the invalid value. No other detail keys
are permitted. Authentication failure continues through the existing non-disclosing authentication
path and is not converted into a host compatibility refusal.

## 2. Stable identities and complete fence

`host_id` is a random UUID allocated and persisted by one desktop installation. After validating an
authenticated host registration, the server allocates `host_session_id` for that accepted UI
connection. The server also allocates `delivery_id`, `revision_id`, `runtime_instance_id`,
`request_id`, UUID `request_generation`, and monotonic `lifecycle_generation`. The host alone
allocates logical UUID `process_id` immediately before each concrete child launch. None of these
identities is inferred from an operating-system PID or reused after its owning generation ends.

The authoritative fence is:

```json
{
  "agent_id": "owner-scoped-agent-id",
  "host_id": "d373d586-c430-4668-90e7-3652ca86b88a",
  "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f",
  "delivery_id": "9081134a-5fbf-4464-b685-925734fbf260",
  "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad",
  "runtime_instance_id": "5036fe64-65e4-4e79-99cb-942b7ca5e58f",
  "process_id": "b51280a7-e558-46f4-9dd9-866ab09758c2",
  "lifecycle_generation": 14
}
```

`process_id` is a host-allocated logical launch UUID, not an operating-system PID. Pre-launch
delivery/install acknowledgements carry the server-issued fence through `runtime_instance_id` and
`lifecycle_generation` because no process exists yet. The first host `starting` transition binds the
fresh `process_id` exactly once to that still-current runtime instance; the child registration then
proves that same identity. Every later candidate state, heartbeat, exit, stop acknowledgement,
tunnel request, progress, result, and error carries the complete fence. Request-bearing frames
additionally carry the server-issued UUID4 `request_id` and UUID4 `request_generation`. The server
derives the owner from the authenticated socket and never trusts an owner field in a tunneled frame.

The server creates the durable runtime-instance row with `process_id = NULL` before delivery. A
pre-launch failure may terminalize with null; any state reached after concrete launch retains the
bound value. The server never preallocates, guesses, replaces, or rebinds the host's process ID.

Before changing state or accepting a result, the server compares every fence field to the current
durable `agent_runtime_instance` row and the socket's bound host session. The sole bootstrap case is
the one-time `starting` compare-and-set that requires the process field to be unbound and stores the
host's fresh logical `process_id`; it is not a wildcard for later frames. Any mismatch returns or
logs `stale_runtime_generation`, settles no current request, and changes no lifecycle state. A stale
frame is safe to repeat and is never promoted by arrival order.

## 3. Host registration, selection, and inventory

Host-capable registration includes:

```json
{
  "agent_host": {
    "host_id": "d373d586-c430-4668-90e7-3652ca86b88a",
    "supported_runtime_contract_versions": [2],
    "runtime_lock_sha256": "<64 lowercase hex>",
    "platform": "windows",
    "client_version": "0.4.0"
  }
}
```

`platform` may also be `macos` once feature 059's host is integrated. The host never proposes or
restores `host_session_id`. The server first authenticates the socket, validates the `host_id`
syntax, platform/client contract fields, runtime versions, and lock digest, binds the authenticated
owner and current connection scope, and only then allocates the session. Acceptance returns:

```json
{
  "type": "agent_host_registered",
  "host_id": "d373d586-c430-4668-90e7-3652ca86b88a",
  "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f",
  "inventory_required": true,
  "accepted_at": "2026-07-15T18:41:00Z"
}
```

An incompatible registration receives the stable refusal within two seconds and no eligible host
session. Until `agent_host_registered` arrives, the client sends no inventory, accepts no bundle,
and starts no retained child. Every subsequent host frame on that socket must echo the returned
session; a missing, client-invented, prior-connection, or wrong-socket session is
`stale_runtime_generation`.

Hosting applicability is not inferred from that live registration. One immutable candidate-owned
capability map is returned identically by authenticated `GET /api/dashboard` and
`system_config.config`:

```json
{
  "capabilities": {
    "personal_agent_host": {
      "macos": {
        "supported": false,
        "runtime_contract_versions": [],
        "source_feature": null
      }
    }
  }
}
```

Feature 060 owns the false value; feature 059 alone changes it to `supported: true`, versions
containing `2`, and `source_feature: "059"` when its direct-download host implementation lands.
Missing or malformed capability data is unknown/blocking, not false. When false, only the distinct
macOS-hosting release check is not applicable. When true, the exercised macOS artifact must also send
the structured registration above and receive `agent_host_registered`; any refusal or missing
acknowledgement is a host failure, not evidence that the feature is absent. Branch/spec-directory
presence, live connection count, and the legacy client-declared boolean are never applicability
sources.

Registration makes the host eligible, not authoritative. Selection is deterministic:

1. retain the healthy selected host;
2. if that stable `host_id` reconnects, bind its newest server-accepted session and fence the old
   session without selecting a different machine;
3. after selected-host loss, choose the standby with the earliest durable `eligible_since`, breaking
   ties by lexical `host_id`;
4. bump `lifecycle_generation` and create a new delivery/runtime instance before routing to the
   replacement.

Only the selected host receives a bundle or request. Other eligible hosts receive a non-sensitive
standby status and cannot acknowledge or register that agent instance.

Before starting any retained bundle after launch/reconnect, the host sends `agent_host_inventory`
with revision IDs and local digests but starts no child. The server responds once with an action for
every entry: `keep_stopped`, `start`, or `delete`, plus any selected delivery. Unknown, deleted,
superseded, digest-mismatched, and unselected entries are deleted or kept stopped. Inventory must
complete before retained auto-start; timeout leaves all retained bundles stopped.

The exact v2 inventory request is:

```json
{
  "type": "agent_host_inventory",
  "host_id": "d373d586-c430-4668-90e7-3652ca86b88a",
  "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f",
  "inventory_id": "903301da-b73c-4d52-ae3a-e726b1f58900",
  "entries": [
    {
      "agent_id": "owner-scoped-agent-id",
      "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad",
      "bundle_sha256": "<64 lowercase hex>",
      "runtime_contract_version": 2,
      "required_runtime_lock_sha256": "<64 lowercase hex>"
    }
  ]
}
```

`inventory_id`, `(agent_id, revision_id)` pairs, and entries are unique; entries contain no owner,
credential, path, operating-system PID, process ID, or running-state assertion. The exact response
is:

```json
{
  "type": "agent_host_inventory_reconciled",
  "host_id": "d373d586-c430-4668-90e7-3652ca86b88a",
  "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f",
  "inventory_id": "903301da-b73c-4d52-ae3a-e726b1f58900",
  "actions": [
    {
      "agent_id": "owner-scoped-agent-id",
      "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad",
      "action": "start",
      "reason_code": null,
      "selected_delivery": {
        "delivery_id": "9081134a-5fbf-4464-b685-925734fbf260",
        "runtime_instance_id": "5036fe64-65e4-4e79-99cb-942b7ca5e58f",
        "lifecycle_generation": 14,
        "runtime_contract_version": 2,
        "required_runtime_lock_sha256": "<64 lowercase hex>",
        "bundle_sha256": "<64 lowercase hex>"
      }
    }
  ],
  "reconciled_at": "2026-07-15T18:41:00Z"
}
```

`selected_delivery` is non-null only for `start`; it is null for `keep_stopped` and `delete`.
The host validates the complete response first, applies every delete/keep-stopped decision, and only
then starts an entry carrying a selected delivery. A response missing an action, containing an
unknown/duplicate entry, or bound to a different inventory/session is invalid and starts nothing.

## 4. Delivery and launch frames

`agent_bundle_deliver` adds the complete server-issued delivery fence, `runtime_contract_version`,
`required_runtime_lock_sha256`, an immutable bundle digest, and the three feature-058 files. Its
pre-launch fence omits only `process_id`, which does not exist until step 4. The host:

1. validates compatibility, file allowlist, IDs, and bundle digest;
2. writes a UUID/revision-specific staging directory;
3. flushes files and directory metadata, then atomically renames it to an immutable revision path;
4. allocates a fresh logical UUID `process_id`, starts exactly one child with the complete fence, and
   emits `agent_runtime_state` with `state: starting`; the server accepts it only when the
   pre-launch fence is still current and `process_id` is unbound, then stores that value exactly
   once; and
5. accepts the child's first protocol frame only when it is the registration described below, then
   emits `ready` only after that registration and a valid liveness signal.

The child's first stdout protocol frame is `agent_runtime_register`. Its exact v2 envelope is:

```json
{
  "type": "agent_runtime_register",
  "fence": { "agent_id": "owner-scoped-agent-id", "host_id": "d373d586-c430-4668-90e7-3652ca86b88a", "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f", "delivery_id": "9081134a-5fbf-4464-b685-925734fbf260", "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad", "runtime_instance_id": "5036fe64-65e4-4e79-99cb-942b7ca5e58f", "process_id": "b51280a7-e558-46f4-9dd9-866ab09758c2", "lifecycle_generation": 14 },
  "runtime_contract_version": 2,
  "bundle_sha256": "<64 lowercase hex>",
  "agent_card": {
    "name": "Example Agent",
    "description": "A bounded description",
    "agent_id": "owner-scoped-agent-id",
    "version": "0.1.0",
    "skills": [],
    "metadata": {}
  }
}
```

`agent_card` uses the existing shared `AgentCard` shape and its `agent_id` must equal
`fence.agent_id`; it contains neither a transport URL nor an owner assertion. The envelope carries
no owner or credential. A heartbeat, result, or arbitrary output is not implicit registration. The
host validates the frame before forwarding it;
the server then compares the selected host session, delivery/revision/runtime generations,
host-allocated process ID, contract version, and digest to durable state. Repeating the exact valid
registration is idempotent. A mismatched or superseded registration is rejected and cannot become
ready; a missing registration ends with `child_registration_timeout` under the configured bounded
startup deadline. No tunneled request is assigned before the server accepts `ready` and durably
marks the selected/promoted runtime `online`.

Acknowledgements use:

```json
{
  "type": "agent_runtime_state",
  "fence": { "agent_id": "...", "host_id": "...", "host_session_id": "...", "delivery_id": "...", "revision_id": "...", "runtime_instance_id": "...", "process_id": "...", "lifecycle_generation": 14 },
  "state": "ready",
  "runtime_contract_version": 2,
  "bundle_sha256": "<64 lowercase hex>",
  "observed_at": "2026-07-15T18:41:00Z",
  "reason_code": null
}
```

State is exactly `starting`, `ready`, `failed`, or `offline` on this host-facing frame. `ready`
means the exact child fence is registered and live but does not itself make a candidate invocable.
`online` is a server-owned durable runtime state set only after selection/promotion commits; hosts do
not assert it. User-facing clients receive the canonical `agent_lifecycle` projection in
[operation-and-lifecycle-status.md](operation-and-lifecycle-status.md), where server-owned `online`
is the invocable state.

## 5. Liveness, invocation, and prompt terminal outcomes

After valid child registration, while the host-facing runtime is ready or the server-owned runtime
is online, the host emits a valid `agent_runtime_heartbeat` at least once per second. It carries the
complete fence and a monotonic per-process `heartbeat_sequence`; it does not carry stdout/stderr.
The server ignores a repeated/lower sequence. Before registration, the bounded child-registration
deadline—not a heartbeat—is the liveness authority.

The exact v2 heartbeat envelope is:

```json
{
  "type": "agent_runtime_heartbeat",
  "fence": { "agent_id": "owner-scoped-agent-id", "host_id": "d373d586-c430-4668-90e7-3652ca86b88a", "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f", "delivery_id": "9081134a-5fbf-4464-b685-925734fbf260", "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad", "runtime_instance_id": "5036fe64-65e4-4e79-99cb-942b7ca5e58f", "process_id": "b51280a7-e558-46f4-9dd9-866ab09758c2", "lifecycle_generation": 14 },
  "heartbeat_sequence": 9
}
```

The sequence is a positive integer reset only for a fresh `process_id`; server receipt time is the
liveness clock, so host wall-clock or monotonic timestamps are not accepted as authority.

When the host observes termination or protocol EOF, it sends exactly one best-effort exit frame:

```json
{
  "type": "agent_runtime_exit",
  "fence": { "agent_id": "owner-scoped-agent-id", "host_id": "d373d586-c430-4668-90e7-3652ca86b88a", "host_session_id": "58bc14f3-af9a-4cf8-beb2-a58e3092117f", "delivery_id": "9081134a-5fbf-4464-b685-925734fbf260", "revision_id": "d083f22c-7f71-47bd-b5e1-d71068b3fdad", "runtime_instance_id": "5036fe64-65e4-4e79-99cb-942b7ca5e58f", "process_id": "b51280a7-e558-46f4-9dd9-866ab09758c2", "lifecycle_generation": 14 },
  "exit_kind": "process_exit",
  "exit_code": 1
}
```

`exit_kind` is exactly `process_exit`, `protocol_eof`, or `explicit_stop`; `exit_code` is a signed
integer for `process_exit` and null otherwise. It contains no diagnostics. The server derives the
terminal code from the fenced durable state and socket event; a missing exit frame cannot delay
host-loss/EOF detection, and repeating it is idempotent.

- Child exit, host-socket loss, explicit stop, or EOF is detected immediately. The server marks that
  fenced instance offline and terminalizes its assigned requests within **2 seconds** of detection.
- Five seconds without a newer valid child heartbeat is `child_hung`. The server fences the instance,
  asks the host to kill its tree, and terminalizes assigned requests within **2 more seconds**
  (seven seconds maximum from the last valid heartbeat).
- A request may be delivered only to an `online` current fence. The server persists its
  `request_id`/`request_generation` against that instance before send.
- An instance failure settles each pending request exactly once as retryable `agent_offline`,
  `host_lost`, `child_exited`, or `child_hung`. A known failure never waits for the generic request
  timeout. A late result is stale and ignored.

Host restart is not automatic within the same failed runtime instance. Recovery creates new
server-issued delivery/runtime generations and requires a new host-issued process fence so old
frames cannot become current.

## 6. Two-phase revision activation

Revisions are immutable. `user_agent.active_revision_id` remains the authoritative working pointer;
`last_known_good_revision_id` is never advanced to an unconfirmed candidate.

1. Server creates candidate revision and delivery rows; active runtime remains routable.
2. Selected host durably installs and starts the candidate in parallel under a new fence.
3. Candidate must register and report host-facing `ready` with matching version/digest/fence; it is
   still non-invocable at this point.
4. One database transaction promotes `active_revision_id`, sets the last-known-good relationship,
   and marks the candidate active. Failure/rollback leaves the old pointer untouched.
5. After promotion commit, routing moves to the candidate and the host receives a fenced stop for the
   prior runtime. The prior immutable bundle is retained for recovery according to retention policy.

Preparation success alone never stops the old process. If install, start, registration, liveness, or
promotion fails, the candidate is terminalized/stopped and the old revision remains available.
After a crash, reconciliation reads the durable active pointer: it starts/keeps that revision and
stops any non-authoritative candidate. Fault injection must cover every filesystem and database
boundary, including loss of power between atomic rename and promotion.

## 7. Durable deletion and stale cleanup

Deletion first commits `deleted_at`, disabled state, and an incremented `lifecycle_generation`.
Only after that commit does the service remove routing, settle requests, and send fenced stop/delete
actions. No delete failure clears the tombstone.

A delayed delivery, registration, heartbeat, result, revision acknowledgement, or reconnect whose
generation predates the tombstone is rejected as `agent_deleted` or `stale_runtime_generation` and
cannot rewrite live status. Inventory reconciliation deletes retained tombstoned bundles before any
child starts, preventing resurrection on each desktop launch.

## 8. Process-supervision limits

The following limits are one conformance contract, not one cross-package import. Server-hosted
draft/test children use `backend/shared/process_supervision.py`; packaged Windows BYO children use
`windows-client/win_agent/process_supervision.py`. Both consume the same constants/test-vector
corpus and pass equivalent stress assertions, but neither product runtime imports the other
application tree. The frozen Windows artifact must contain and execute its local module.

Both implementations provide the same behavior:

- stdout and stderr are drained continuously in fixed-size binary reads from process start;
- maximum decoded line size is **64 KiB**; excess bytes are discarded until newline and one
  `output_line_too_long` diagnostic is recorded per line;
- each pipe retains only a **256 KiB** ring buffer per process; older diagnostic bytes are evicted;
- stdout protocol lines are parsed only after the size check; stderr is diagnostics only;
- the child starts in a distinct POSIX process group or Windows job/process-tree boundary;
- stop closes stdin, requests graceful tree termination, escalates to force kill by four seconds,
  joins drain/monitor workers, and closes every pipe by five seconds.

No raw diagnostic output is forwarded to other users, operation metrics, or release evidence.
Cancellation, quit, crash, and failure take the same cleanup path. A child closing one pipe does not
stop draining the other.

## 9. Stable error codes

Host/runtime errors use: `invalid_host_registration`, `runtime_contract_unsupported`, `runtime_lock_mismatch`,
`bundle_digest_mismatch`, `bundle_install_failed`, `child_start_failed`, `child_registration_timeout`,
`child_exited`, `child_hung`, `host_lost`, `agent_offline`, `agent_deleted`,
`stale_runtime_generation`, `revision_promotion_failed`, `inventory_required`, and
`process_cleanup_timeout`. Messages are actionable but contain no source, secret, raw output, or
user-controlled filesystem path.

## 10. Required contract tests

- 100 trials each of child exit, hang, host loss/reconnect/replacement, duplicate hosts, and stale
  registration/result/ack/heartbeat: timing bounds hold and zero stale results are accepted.
- 100 fault-injected revision promotions: prior working revision remains invocable unless the
  candidate is durably active.
- Delete/register/delivery/revision interleavings and offline inventory reconciliation never
  resurrect an agent.
- Every supported host/bundle version-and-lock pairing either completes a benign call or returns its
  declared incompatibility in two seconds.
- 100 high-output, oversized-line, descendant, one-pipe-EOF, cancellation, quit, and failure trials:
  buffers stay bounded and no descendant/thread/open pipe remains after five seconds.
- 20 full `starting → online → updating → failed/offline` sequences project consistently to
  every supported client within two seconds without reload.
- Host registration allocates a fresh server session only after validation; child registration
  binds a unique host-allocated logical process ID; `ready` never routes a request before the
  server-owned promotion/selection makes the runtime `online`.
