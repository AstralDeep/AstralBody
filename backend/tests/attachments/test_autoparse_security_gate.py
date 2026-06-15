"""Feature 031 US2 — the security gate enforces the no-new-deps posture (T038).

Auto-created parser code is constrained to the standard library + already
installed packages (research.R7); the existing code-security gate blocks the
shell/install escape hatches a parser would need to smuggle a new dependency.
Also asserts the codegen prompt carries the explicit stdlib-only instruction.
"""

from __future__ import annotations

from orchestrator.code_security import CodeSecurityAnalyzer, Severity


def _analyze(code: str):
    return CodeSecurityAnalyzer().analyze(code, filename="parser/mcp_tools.py")


def test_subprocess_install_is_blocked():
    # The only way a generated parser could add a dependency is to shell out and
    # pip-install it — which the gate must reject as CRITICAL.
    code = (
        "import subprocess\n"
        "def parse_x(attachment_id, **kwargs):\n"
        "    subprocess.run(['pip', 'install', 'pyarrow'])\n"
        "    return {}\n"
    )
    report = _analyze(code)
    assert not report.passed
    assert report.max_severity == Severity.CRITICAL


def test_os_system_is_blocked():
    code = (
        "import os\n"
        "def parse_x(attachment_id, **kwargs):\n"
        "    os.system('pip install pyarrow')\n"
        "    return {}\n"
    )
    report = _analyze(code)
    assert not report.passed


def test_stdlib_only_parser_passes_gate():
    # A best-effort archive reader using only the standard library is clean.
    code = (
        "import zipfile, io\n"
        "def parse_zip(attachment_id, **kwargs):\n"
        "    return {'note': 'best-effort zip listing', 'entries': []}\n"
    )
    report = _analyze(code)
    assert report.passed


def test_codegen_prompt_carries_stdlib_only_constraint():
    import inspect

    from orchestrator import agent_generator
    # Normalize whitespace so the wrapped multi-line instruction matches.
    src = " ".join(inspect.getsource(agent_generator).split())
    assert "packages already installed in this image" in src
    assert "best-effort structural extraction" in src
    assert "Do NOT assume any" in src
