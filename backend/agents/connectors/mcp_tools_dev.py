"""
Developer tools for the Claude Connectors Agent — US-22.

Code review and constitution critique for spec-driven development.
"""
import logging
from typing import Dict, Any

from shared.primitives import (
    Alert, Collapsible, Text, Container, Divider,
    create_ui_response,
)

logger = logging.getLogger("Connectors.Dev")


# ---------------------------------------------------------------------------
# Code Review
# ---------------------------------------------------------------------------

_CODE_REVIEW_METADATA = {
    "name": "code_review",
    "description": "Perform an automated code review with structured findings: issues, suggestions, and security notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code snippet to review"},
            "language": {"type": "string", "description": "Programming language"},
            "focus": {"type": "string", "enum": ["general", "security", "performance", "style"], "description": "Review focus area"},
        },
        "required": ["code"],
    },
}


def handle_code_review(args: Dict[str, Any]) -> Dict[str, Any]:
    code = args.get("code", "")
    language = args.get("language", "unknown")
    focus = args.get("focus", "general")

    issues = []
    suggestions = []
    security_notes = []

    lines = code.strip().split("\n")
    line_count = len(lines)

    if line_count > 200:
        issues.append(f"File is {line_count} lines. Consider splitting into modules.")
        suggestions.append("Break large files into focused modules (< 200 lines each).")

    if any(len(line) > 120 for line in lines):
        issues.append("Some lines exceed 120 characters. Consider wrapping.")
        suggestions.append("Wrap long lines at 100-120 characters for readability.")

    if "\t" in code:
        issues.append("Tab characters detected. Use spaces for indentation.")
        suggestions.append("Convert tabs to spaces (PEP 8 recommends 4 spaces).")

    if language.lower() in ("python", "py"):
        if "eval(" in code or "exec(" in code:
            security_notes.append("eval()/exec() usage detected — potential code injection risk.")
        if "password" in code.lower() or "secret" in code.lower() or "api_key" in code.lower():
            security_notes.append("Hardcoded credentials detected. Use environment variables or a secret manager.")
        if "subprocess" in code or "os.system" in code:
            security_notes.append("Shell command execution detected. Validate and sanitize all inputs.")
    elif language.lower() in ("javascript", "js", "typescript", "ts"):
        if "innerHTML" in code or "dangerouslySetInnerHTML" in code:
            security_notes.append("Unsafe HTML insertion detected. Use textContent or sanitize with DOMPurify.")
        if "localStorage" in code:
            security_notes.append("localStorage usage — never store sensitive tokens or credentials.")

    if focus == "performance":
        if "for " in code and ("list.append" in code or "push(" in code):
            suggestions.append("Consider list comprehensions or array methods for performance on large datasets.")

    components = [
        Text(content=f"Code Review — {language}" + (f" (focus: {focus})" if focus != "general" else ""), variant="h2"),
    ]

    if issues:
        for issue in issues:
            components.append(Alert(variant="warning", title="Issue", message=issue))
    else:
        components.append(Alert(variant="success", title="No issues found", message="No structural issues detected."))

    if suggestions:
        suggestion_content = Container(children=[
            Text(content=f"• {s}") for s in suggestions
        ])
        components.append(Collapsible(title="Suggestions", content=[suggestion_content]))

    if security_notes:
        security_content = Container(children=[
            Text(content=note) for note in security_notes
        ])
        components.append(Collapsible(title="Security Notes", content=[security_content]))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Constitution Critique
# ---------------------------------------------------------------------------

_CONSTITUTION_METADATA = {
    "name": "constitution_critique",
    "description": "Review a specification document against constitution principles for spec-driven development.",
    "input_schema": {
        "type": "object",
        "properties": {
            "spec": {"type": "string", "description": "The specification document content to review"},
            "spec_title": {"type": "string", "description": "Title of the specification"},
            "constitution_version": {"type": "string", "description": "Version of the constitution to check against"},
        },
        "required": ["spec", "spec_title"],
    },
}

CONSTITUTION_PRINCIPLES = [
    ("I - Patient Safety First", "All generated components must be safe and not cause harm."),
    ("II - Data Privacy by Default", "No PHI/PII in logs, URLs, or client-side storage."),
    ("III - Transparent AI", "AI-generated content must be clearly labeled as such."),
    ("IV - Audit Trail Integrity", "All system actions must be logged and immutable."),
    ("V - Dependency Minimization", "No new third-party libraries without explicit review."),
    ("VI - Secure by Default", "Security controls must be enabled by default, not opt-in."),
    ("VII - User Agency", "Users retain final control over AI-generated actions."),
    ("VIII - Accessibility First", "Components must be keyboard-navigable and screen-reader accessible."),
    ("IX - Database Integrity", "All schema changes must be migration-tracked and reversible."),
    ("X - Code Quality", "Code must be typed, tested, and documented."),
]


def handle_constitution_critique(args: Dict[str, Any]) -> Dict[str, Any]:
    spec = args.get("spec", "")
    spec_title = args.get("spec_title", "Untitled Spec")
    constitution_version = args.get("constitution_version", "1.1.0")

    spec_lower = spec.lower()
    findings = []

    if "test" not in spec_lower or "testing" not in spec_lower:
        findings.append(("X", "warn", "No test plan mentioned. Constitution X requires tests."))
    if "privacy" not in spec_lower and "pii" not in spec_lower and "phi" not in spec_lower:
        findings.append(("II", "warn", "No mention of data privacy/PII/PHI handling. Review Constitution II."))
    if "audit" not in spec_lower:
        findings.append(("IV", "info", "No audit trail considerations. Review Constitution IV."))
    if "library" in spec_lower or "package" in spec_lower or "dependency" in spec_lower:
        findings.append(("V", "info", "External dependencies mentioned. Ensure Constitution V compliance."))
    if "migration" not in spec_lower and "database" in spec_lower:
        findings.append(("IX", "warn", "Database changes planned but no migration strategy mentioned. Constitution IX."))

    components = [
        Text(content=f"Constitution Critique: {spec_title}", variant="h2"),
        Text(content=f"Constitution v{constitution_version} — {len(CONSTITUTION_PRINCIPLES)} principles checked", variant="caption"),
        Divider(),
    ]

    if findings:
        for principle, level, note in findings:
            variant = "warning" if level == "warn" else "info"
            components.append(Alert(variant=variant, title=f"Principle {principle}", message=note))
    else:
        components.append(Alert(variant="success", title="No issues found", message="Spec passes basic constitutional checks."))

    ref_content = Container(children=[
        Text(content=f"{name}: {desc}") for name, desc in CONSTITUTION_PRINCIPLES
    ])
    components.append(Collapsible(title="Constitution Reference", content=[ref_content]))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEV_TOOL_REGISTRY = {
    "code_review": {"function": handle_code_review, **_CODE_REVIEW_METADATA},
    "constitution_critique": {"function": handle_constitution_critique, **_CONSTITUTION_METADATA},
}