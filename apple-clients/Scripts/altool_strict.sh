#!/usr/bin/env bash
# Feature 053 — run `xcrun altool` and actually fail when it fails.
#
# altool is not trustworthy as a shell citizen: it will print
#
#     UPLOAD FAILED with 1 error
#     ERROR: [altool...] Validation failed (409) The product archive is invalid...
#
# and still exit 0. Under `bash -e` that turns a rejected upload into a green
# build. This wrapper fails on a non-zero exit, on any failure marker in the
# output, AND on the absence of a success marker — so a silent no-op cannot pass.
#
#     altool_strict.sh "<label>" --upload-app -f <file> -t <platform> --apiKey … --apiIssuer …
set -uo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <label> <altool args...>" >&2
    exit 2
fi

label="$1"
shift

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

xcrun altool "$@" 2>&1 | tee "$out"
rc="${PIPESTATUS[0]}"

if [ "$rc" -ne 0 ]; then
    echo "::error::${label}: altool exited ${rc}"
    exit 1
fi

if grep -qE '(UPLOAD|VERIFY) FAILED|ERROR: \[altool' "$out"; then
    echo "::error::${label}: altool reported a failure (and exited 0 anyway)"
    # Surface Apple's own explanation on the annotation line.
    detail="$(grep -m1 -oE 'Validation failed \([0-9-]+\) .*' "$out" || true)"
    [ -n "$detail" ] && echo "::error::${label}: ${detail}"
    exit 1
fi

if ! grep -qE '(UPLOAD|VERIFY) SUCCEEDED' "$out"; then
    echo "::error::${label}: altool printed no success line — refusing to treat this as done"
    exit 1
fi

echo "${label}: ok"
