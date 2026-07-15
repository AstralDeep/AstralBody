---
name: speckit-git-initialize
description: Initialize Git only when a Spec Kit project is not already in a repository. Use for the constitution workflow's initialization hook or an explicit initialization request.
---

# Initialize Git Repository

Check `git rev-parse --is-inside-work-tree` first. If already inside a repository, report that fact and do nothing.

Otherwise, run the platform script from the project root:

- Bash: `.specify/extensions/git/scripts/bash/initialize-repo.sh`
- PowerShell: `.specify/extensions/git/scripts/powershell/initialize-repo.ps1`

This is a mutating operation that can create an initial commit. Do not use a manual `git init && git add .` fallback without explicit user approval and a review of the files that would be staged. If Git is absent, warn and let non-Git Spec Kit work continue. Surface partial failures rather than claiming initialization succeeded.
