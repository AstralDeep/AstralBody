#!/usr/bin/env python3
"""Render an ExportOptions template by substituting ${...} placeholders from env.

Feature 053. Used by .github/workflows/apple-release.yml so that no Apple Team ID
and no provisioning-profile name is ever committed. Stdlib only (Constitution V);
`envsubst` is part of gettext and is not guaranteed on a macOS runner.

    python3 render_export_options.py <template.plist> <output.plist>

Every placeholder present in the template must be set in the environment, or the
script exits non-zero — a half-substituted export-options plist would otherwise
fail deep inside `xcodebuild -exportArchive` with a much worse error.
"""

from __future__ import annotations

import os
import pathlib
import string
import sys

PLACEHOLDERS = (
    "APPLE_TEAM_ID",
    "APPLE_PROFILE_IOS",
    "APPLE_PROFILE_MACOS",
    "APPLE_PROFILE_WATCH",
)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, dst = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    template = string.Template(src.read_text())

    # Only the placeholders this template actually uses need a value.
    used = {n for n in PLACEHOLDERS if f"${{{n}}}" in template.template}
    missing = sorted(n for n in used if not os.environ.get(n))
    if missing:
        print(f"error: {src.name} needs these environment values: {', '.join(missing)}",
              file=sys.stderr)
        return 1

    dst.write_text(template.substitute({n: os.environ.get(n, "") for n in PLACEHOLDERS}))
    print(f"rendered {dst} ({len(used)} placeholder(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
