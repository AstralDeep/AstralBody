---
name: speckit-git-remote
description: Detect and classify the current repository's origin remote without mutation. Use when Spec Kit needs GitHub repository identity or the user asks to inspect the remote.
---

# Detect Git Remote URL

1. Verify the directory is a Git worktree.
2. Run `git config --get remote.origin.url`.
3. Parse HTTPS (`https://github.com/<owner>/<repo>.git`) and SSH (`git@github.com:<owner>/<repo>.git`) forms.
4. Report owner, repository, and whether the host is actually `github.com`.

Do not assume an arbitrary remote is GitHub. If Git or `origin` is absent, return an empty result with a warning; do not mutate configuration.
