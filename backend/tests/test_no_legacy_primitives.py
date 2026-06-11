"""Feature 026 — T014: assert the legacy ``shared.primitives`` module is no
longer *imported* anywhere in the product (drives SC-003 / FR-007).

Scans backend source for import statements (``from shared.primitives import`` /
``import shared.primitives``). Historical mentions in docstrings/comments and the
parity test's guarded transitional cross-check are not imports and don't count.
Before the cutover gate the legacy file may still exist; after T037 deletes it,
this test still passes (there are simply no importers).
"""
import ast
import os

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files allowed to mention the legacy module name (transitional / self-referential).
ALLOWLIST = {
    os.path.join(BACKEND, "shared", "primitives.py"),  # the legacy module itself (until cutover)
    os.path.join(BACKEND, "tests", "test_astralprims_parity.py"),  # guarded cross-check
    os.path.join(BACKEND, "tests", "test_no_legacy_primitives.py"),  # this file
}


def _iter_py_files():
    for root, dirs, files in os.walk(BACKEND):
        # skip virtualenvs / caches / vendored assets
        dirs[:] = [d for d in dirs if d not in (".venv", "venv", "__pycache__", "node_modules", "static", "vendor")]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def test_no_legacy_primitives_imports():
    offenders = []
    for path in _iter_py_files():
        if path in ALLOWLIST:
            continue
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "shared.primitives":
                offenders.append(f"{path}:{node.lineno} (from shared.primitives import ...)")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "shared.primitives":
                        offenders.append(f"{path}:{node.lineno} (import shared.primitives)")
    assert not offenders, "Legacy shared.primitives still imported:\n" + "\n".join(offenders)
