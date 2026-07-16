# US4 Windows Release Verification

**Feature**: 060 Runtime Reliability and Release Readiness
**Branch**: `060-runtime-reliability-hardening`
**Recorded**: 2026-07-16 (America/New_York)
**Status**: T058–T068 implementation/source gates complete; T069 fresh-Windows
artifact proof **not run**

This record contains no authority URL, service endpoint, access token, API key,
or other credential value.

## Release identities prepared by T058–T068

| Identity | Value |
|---|---|
| Client version | `0.4.0` |
| Release ID | `windows-0.4.0` |
| Canonical deployment-profile SHA-256 | `771bd01cacaff4db5ef9e8bda6991b8502942da9630719720a475b05b9594bec` |
| Raw profile-file SHA-256 | `d19674307582d1a0ea0e98b99fb591348b530c9e5377eeaf573fcb032f16d5f4` |
| Direct-requirements SHA-256 | `8c14423afc61a216ec6ea49f891f1f45e60095f0616835aa377a9037a8f6a155` |
| Final Windows/Python 3.11 lock SHA-256 | `6041036906881c59868b9e53e16d1e22d8371b68af2f36701022a5a239dd43ba` |
| Runtime-manifest file SHA-256 | `38a681c191b5cce1dd46b815e9d1c8053b375d1ef018616c05bb67d251e8ee09` |
| Runtime contract | `2` |
| Frozen worker entry point | `AstralDeep.exe --byo-worker` |

The final lock identity is equal in the release runtime manifest, Windows UI
registration, packaged BYO host, backend generator, and tracked compatibility
fixture. The PyInstaller spec performs the same strict profile/runtime/lock
preflight before constructing `Analysis` or an EXE.

## Local source and contract evidence

The full Windows client source suite ran headlessly on the macOS development
host:

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q windows-client/tests
```

Result: **546 passed, 6 skipped in 35.98s**. Five skips are deliberately owned
by `test_packaged_release.py`: the actual Windows EXE, frozen GUI, and HWND
checks require `ASTRAL_WINDOWS_EXE` on the fresh Windows candidate job. The
remaining skip is another platform-specific client check. No skipped artifact
test is counted as T069 evidence.

The packaged-release module's host-side collection gate separately produced
**1 passed, 5 skipped in 0.02s**. Its Windows-only cases now require all of the
following from the actual frozen artifact:

- noninteractive bundled profile/runtime/final-lock validation;
- frozen `--byo-worker` benign agent round trip;
- ordinary connected chat with a committed transcript and rendered canvas;
- equal immutable profile/endpoint identity across the window transport,
  authenticated BYO host, and built-in tools-agent metadata;
- a real connection failure followed by transport retry while retaining the
  selected whole profile;
- fresh-HKCU launch with no Configure AstralDeep window and process teardown.

Additional gates completed:

```text
ruff check <changed Windows release Python files and focused tests>
# All checks passed.

python -m py_compile windows-client/AstralDeep.spec windows-client/main.py \
  windows-client/astral_client/deployment.py windows-client/astral_client/app.py \
  windows-client/astral_client/integrity.py windows-client/win_agent/agent.py \
  windows-client/win_agent/byo_host.py scripts/windows_release_candidate.py
# passed

git diff --check -- windows-client \
  .github/workflows/build-windows-candidate.yml \
  scripts/windows_release_candidate.py
# passed
```

Ruby's YAML parser accepted `.github/workflows/build-windows-candidate.yml`.
The three third-party action pins were also resolved against their official
immutable tags: checkout `v5.0.1`, setup-python `v6.3.0`, and upload-artifact
`v4.6.2`.

The complete lock resolved successfully in pip's hash-enforcing Windows target
mode:

```text
python -m pip install --dry-run --ignore-installed --require-hashes \
  --only-binary=:all: --platform win_amd64 --python-version 3.11 \
  --implementation cp --abi cp311 \
  -r windows-client/requirements-release.lock.txt
```

The source entry point's noninteractive deployment check returned status
`valid`, source `bundled_release`, version `0.4.0`, target `win_amd64`, runtime
contract `2`, and the profile/input/lock identities recorded above. Its report
contained dispositions and digests but no authority, endpoint, or credential.

The runtime integration closeout additionally ran the backend final-lock gates:
`test_byo_runtime_fencing_060.py` (**26 passed**),
`test_byo_revision_recovery_060.py` (**26 passed**), and
`test_byo_runtime_compatibility_060.py` (**3 passed**). Total: **55 passed in
2.38s**. The focused Windows host/supervision gate passed **37 tests in
27.01s**.

## Build-once candidate producer

`.github/workflows/build-windows-candidate.yml` is a read-only reusable/manual
unsigned candidate producer. For one exact 40-character candidate SHA it:

1. checks out that exact commit without retaining credentials;
2. installs the complete hash lock into two clean Python 3.11 environments and
   compares their exact installed manifests;
3. builds `AstralDeep.exe` exactly once from the first clean environment;
4. clears the native Windows QSettings key and runs frozen validation, worker,
   connected chat, offline retry, no-dialog/HWND, and termination tests;
5. runs the full Windows Python suite with XML coverage;
6. binds the one EXE to source/profile/runtime/input/lock/run identities; and
7. archives that exact EXE and provenance, exposing the immutable Actions
   artifact ID, archive digest, and executable digest.

Because the app uses PyInstaller windowed mode, the pre-Qt entry point also
duplicates and wraps only the inherited Windows pipe handles for frozen CLI and
worker modes. Ordinary GUI launches still have no console, while the packaged
`--byo-worker` process retains its required stdin/stdout/stderr protocol.

The short-lived staging token is scoped only to input validation and packaged
smoke steps. It is absent from dependency installation, PyInstaller, source
coverage, candidate manifests, and uploaded artifacts. The workflow has no
signing, tag, release, publication, or other public mutation authority.

## T069 fresh-Windows proof — blocked / not run

T069 is intentionally still unchecked. This checkout is on macOS and no frozen
Windows candidate artifact has been built from the current uncommitted working
tree. Consequently there is currently **no** legitimate value for:

- `AstralDeep.exe` SHA-256;
- GitHub Actions run/attempt;
- immutable artifact ID and archive digest;
- fresh-HKCU no-dialog result;
- actual frozen worker/chat/offline-retry/HWND results; or
- Windows coverage artifact identity.

T069 requires a named, pushed candidate commit and a fresh `windows-latest`
execution of `build-windows-candidate.yml` with the configured short-lived
staging credential. The run must finish with zero skips in the five packaged
artifact cases, and this section must then be replaced with the exact
candidate/run/artifact/profile/version digests from the archived manifests.
Until that happens, US4 is implemented and locally source-verified, but it is
not fresh-runner, live-artifact, signed, published, deployed, or released.
