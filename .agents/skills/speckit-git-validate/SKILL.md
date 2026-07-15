---
name: speckit-git-validate
description: Validate a Spec Kit feature branch and its matching spec directory without mutation. Use before feature work or when branch/spec alignment is uncertain.
---

# Validate Feature Branch

Read the current branch with `git rev-parse --abbrev-ref HEAD`, falling back to `SPECIFY_FEATURE` only when Git is unavailable.

Accept either:

- Sequential: `^[0-9]{3,}-`
- Timestamp: `^[0-9]{8}-[0-9]{6}-`

For a valid feature branch, locate the matching `specs/<prefix>-*` directory and report both. For an invalid branch, report the current name and the expected patterns. This skill is read-only: do not create, rename, or switch branches.
