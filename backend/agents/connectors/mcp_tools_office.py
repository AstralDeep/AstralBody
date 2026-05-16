"""
Office tools for the Claude Connectors Agent — US-22.

Excel generation, PowerPoint outlines, Word documents, Outlook emails,
and pitch templates. All output as SDUI primitives.
"""
import csv
import io
import json
import logging
import os
from typing import Dict, Any, List

from shared.primitives import (
    Table, Alert, Collapsible, FileDownload, Text, Container, Divider, Button,
    create_ui_response,
)

logger = logging.getLogger("Connectors.Office")


# ---------------------------------------------------------------------------
# Excel / CSV Generator
# ---------------------------------------------------------------------------

_EXCEL_METADATA = {
    "name": "excel_generate",
    "description": "Generate a table with downloadable CSV export.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Title for the spreadsheet/table"},
            "columns": {"type": "array", "items": {"type": "string"}, "description": "Column headers"},
            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Data rows"},
            "description": {"type": "string", "description": "Optional description/caption"},
        },
        "required": ["title", "columns", "rows"],
    },
}


def handle_excel_generate(args: Dict[str, Any]) -> Dict[str, Any]:
    title = args.get("title", "Spreadsheet")
    columns = args.get("columns", [])
    rows = args.get("rows", [])
    description = args.get("description", "")

    # Build CSV for download
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)

    table = Table(
        headers=columns,
        rows=rows,
    )
    download = FileDownload(
        label=f"Download {title}.csv",
        url="",
        filename=f"{title}.csv",
    )

    return create_ui_response([
        Text(content=description or title, variant="h3"),
        table,
        download,
    ])


# ---------------------------------------------------------------------------
# PowerPoint / Presentation Outline
# ---------------------------------------------------------------------------

_PPT_METADATA = {
    "name": "powerpoint_outline",
    "description": "Generate a structured presentation outline with slides and bullet points.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Presentation title"},
            "slides": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
            }, "description": "List of slides with titles and bullet points"},
            "description": {"type": "string", "description": "Optional subtitle/description"},
        },
        "required": ["title", "slides"],
    },
}


def handle_ppt_outline(args: Dict[str, Any]) -> Dict[str, Any]:
    title = args.get("title", "Presentation")
    slides = args.get("slides", [])
    description = args.get("description", "")

    components = [
        Text(content=title, variant="h2"),
    ]
    if description:
        components.append(Text(content=description, variant="body"))

    for i, slide in enumerate(slides):
        slide_title = slide.get("title", f"Slide {i + 1}")
        bullets = slide.get("bullets", [])
        bullet_text = "\n".join(f"• {b}" for b in bullets)
        components.append(Collapsible(
            title=f"Slide {i + 1}: {slide_title}",
            content=[Text(content=bullet_text)],
        ))

    components.append(Text(content=f"Total: {len(slides)} slides", variant="caption"))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Word / Document Generator
# ---------------------------------------------------------------------------

_WORD_METADATA = {
    "name": "word_document",
    "description": "Generate a formatted document with sections, paragraphs, and downloadable markdown export.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Document title"},
            "sections": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "content": {"type": "string"},
                },
            }, "description": "Document sections"},
            "include_download": {"type": "boolean", "description": "Include a download button"},
        },
        "required": ["title", "sections"],
    },
}


def handle_word_document(args: Dict[str, Any]) -> Dict[str, Any]:
    title = args.get("title", "Document")
    sections = args.get("sections", [])
    include_download = args.get("include_download", True)

    components = [
        Text(content=title, variant="h2"),
    ]

    for section in sections:
        heading = section.get("heading", "")
        content = section.get("content", "")
        collapsible = Collapsible(
            title=heading,
            content=[Text(content=content)],
        )
        components.append(collapsible)

    if include_download:
        components.append(FileDownload(
            label=f"Download {title}.md",
            url="",
            filename=f"{title}.md",
        ))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Outlook / Email
# ---------------------------------------------------------------------------

_OUTLOOK_METADATA = {
    "name": "outlook_email",
    "description": "Compose a professional email with preview. Returns a formatted email draft ready for review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address or name"},
            "subject": {"type": "string", "description": "Email subject line"},
            "body": {"type": "string", "description": "Email body content"},
            "cc": {"type": "string", "description": "CC recipients"},
            "priority": {"type": "string", "enum": ["normal", "high", "low"]},
        },
        "required": ["to", "subject", "body"],
    },
}


def handle_outlook_email(args: Dict[str, Any]) -> Dict[str, Any]:
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    cc = args.get("cc", "")
    priority = args.get("priority", "normal")

    email_preview = Container(children=[
        Alert(
            variant="info",
            title=f"To: {to}",
            message=f"Subject: {subject}",
        ),
        Text(content=f"Priority: {priority}" + (f"  |  CC: {cc}" if cc else ""), variant="body"),
        Divider(),
        Text(content=body, variant="body"),
    ])

    return create_ui_response([email_preview])


# ---------------------------------------------------------------------------
# Pitch Templates
# ---------------------------------------------------------------------------

_PITCH_TEMPLATES = {
    "startup": {
        "title": "Startup Pitch Deck",
        "slides": [
            {"title": "Problem", "bullets": ["The problem your customers face", "Why it matters", "Current solutions fall short"]},
            {"title": "Solution", "bullets": ["Your product/service", "How it solves the problem", "Key differentiators"]},
            {"title": "Market", "bullets": ["TAM, SAM, SOM", "Target customers", "Market trends"]},
            {"title": "Business Model", "bullets": ["Revenue streams", "Pricing strategy", "Unit economics"]},
            {"title": "Traction", "bullets": ["Key metrics", "Customer testimonials", "Growth trajectory"]},
            {"title": "Team", "bullets": ["Founders & key hires", "Advisors", "Why this team"]},
            {"title": "Ask", "bullets": ["Funding amount", "Use of funds", "Milestones"]},
        ],
    },
    "sales": {
        "title": "Sales Proposal Deck",
        "slides": [
            {"title": "Executive Summary", "bullets": ["Client challenge", "Proposed solution", "Expected ROI"]},
            {"title": "Current Situation", "bullets": ["Client's current state", "Pain points", "Opportunity cost"]},
            {"title": "Proposed Solution", "bullets": ["Detailed approach", "Timeline", "Deliverables"]},
            {"title": "Pricing", "bullets": ["Package options", "Payment terms", "Value comparison"]},
            {"title": "Case Studies", "bullets": ["Similar clients", "Results achieved", "Testimonials"]},
            {"title": "Next Steps", "bullets": ["Action items", "Timeline", "Contact info"]},
        ],
    },
    "investor": {
        "title": "Investor Update Deck",
        "slides": [
            {"title": "Highlights", "bullets": ["Top wins this period", "Key metrics snapshot", "Headline news"]},
            {"title": "KPIs", "bullets": ["Revenue / ARR", "Customer growth", "Burn rate & runway"]},
            {"title": "Product Updates", "bullets": ["New features shipped", "Roadmap progress", "Customer feedback"]},
            {"title": "Team Updates", "bullets": ["Key hires", "Org changes", "Culture highlights"]},
            {"title": "Challenges & Risks", "bullets": ["What's not working", "Mitigation plans", "Help needed"]},
            {"title": "Looking Ahead", "bullets": ["Next quarter goals", "Key initiatives", "Fundraising plans"]},
        ],
    },
    "product": {
        "title": "Product Launch Deck",
        "slides": [
            {"title": "Vision", "bullets": ["Product vision statement", "Why now", "Market gap"]},
            {"title": "Product Overview", "bullets": ["Core features", "User experience", "Technical highlights"]},
            {"title": "Target Audience", "bullets": ["Primary personas", "Use cases", "Customer journey"]},
            {"title": "Competitive Landscape", "bullets": ["Competitor comparison", "Differentiation matrix", "Moats"]},
            {"title": "Go-to-Market", "bullets": ["Launch strategy", "Channels", "Success metrics"]},
            {"title": "Roadmap", "bullets": ["Phase 1 (MVP)", "Phase 2", "Long-term vision"]},
        ],
    },
    "project": {
        "title": "Project Proposal Deck",
        "slides": [
            {"title": "Project Overview", "bullets": ["Objective", "Scope", "Success criteria"]},
            {"title": "Approach", "bullets": ["Methodology", "Phases", "Dependencies"]},
            {"title": "Timeline", "bullets": ["Milestones", "Critical path", "Buffer"]},
            {"title": "Resources", "bullets": ["Team & roles", "Budget", "Tools & infrastructure"]},
            {"title": "Risks", "bullets": ["Key risks", "Probability/impact", "Mitigation"]},
            {"title": "Governance", "bullets": ["Reporting cadence", "Decision rights", "Escalation path"]},
        ],
    },
    "strategy": {
        "title": "Strategy Deck",
        "slides": [
            {"title": "Where We Are", "bullets": ["Current state assessment", "SWOT analysis", "Key metrics"]},
            {"title": "Where We're Going", "bullets": ["Vision 2026", "Strategic pillars", "BHAG"]},
            {"title": "How We Get There", "bullets": ["Initiative 1", "Initiative 2", "Initiative 3"]},
            {"title": "Resource Allocation", "bullets": ["Investment priorities", "Trade-offs", "Sequencing"]},
            {"title": "Success Metrics", "bullets": ["Leading indicators", "Lagging indicators", "Review cadence"]},
        ],
    },
}

_PITCH_METADATA = {
    "name": "pitch_template",
    "description": "Generate a pre-structured pitch/presentation template. Available types: startup, sales, investor, product, project, strategy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_type": {"type": "string", "enum": list(_PITCH_TEMPLATES.keys())},
            "custom_title": {"type": "string", "description": "Override the default title"},
        },
        "required": ["template_type"],
    },
}


def handle_pitch_template(args: Dict[str, Any]) -> Dict[str, Any]:
    template_type = args.get("template_type", "startup")
    custom_title = args.get("custom_title")

    template = _PITCH_TEMPLATES.get(template_type, _PITCH_TEMPLATES["startup"])
    title = custom_title or template["title"]

    components = [
        Text(content=title, variant="h2"),
        Text(content=f"Template type: {template_type}", variant="caption"),
    ]

    for slide in template["slides"]:
        bullets = "\n".join(f"• {b}" for b in slide["bullets"])
        components.append(Collapsible(
            title=slide["title"],
            content=[Text(content=bullets)],
        ))

    components.append(Text(content="Edit each slide to add your specifics.", variant="caption"))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

OFFICE_TOOL_REGISTRY = {
    "excel_generate": {"function": handle_excel_generate, **_EXCEL_METADATA},
    "powerpoint_outline": {"function": handle_ppt_outline, **_PPT_METADATA},
    "word_document": {"function": handle_word_document, **_WORD_METADATA},
    "outlook_email": {"function": handle_outlook_email, **_OUTLOOK_METADATA},
    "pitch_template": {"function": handle_pitch_template, **_PITCH_METADATA},
}