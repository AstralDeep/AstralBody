#!/usr/bin/env python3
"""
CAAI LinkedIn Content Strategy Knowledge Base.

Contains Melissa's content frames, brand voice guidelines, engagement
best practices, and industry benchmarks for the UKy Center for Applied AI
LinkedIn company page.

Organizational data (mission, expertise, personnel, projects) is imported
from the grants agent's knowledge base to avoid duplication.
"""
import os
import sys
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from agents.grants.caai_knowledge import (
    CAAI_MISSION, EXPERTISE_AREAS, KEY_PERSONNEL, PROJECT_HISTORY,
)


# ── LinkedIn Page Info ─────────────────────────────────────────────────

LINKEDIN_PAGE = {
    "url": "https://www.linkedin.com/company/uk-ibi-caai",
    "name": "UKy Center for Applied AI",
    "website": "https://caai.ai.uky.edu",
}


# ── Brand Voice ────────────────────────────────────────────────────────

CAAI_BRAND_VOICE = {
    "tone": "Authoritative yet approachable; academic but accessible",
    "personality_traits": [
        "Innovative",
        "Collaborative",
        "Impact-driven",
        "Kentucky-proud",
        "Translational",
    ],
    "avoid": [
        "Overly technical jargon without explanation",
        "Salesy or promotional language",
        "Self-congratulatory tone without substance",
        "Generic AI hype without CAAI context",
    ],
    "hashtags": [
        "#AppliedAI", "#ArtificialIntelligence", "#UKResearch",
        "#HealthcareAI", "#AIforGood", "#MachineLearning",
        "#UniversityOfKentucky", "#CAAI", "#DataScience",
        "#NLP", "#LLM", "#ComputerVision",
    ],
    "target_audience": [
        "Research faculty considering AI collaborations",
        "Graduate students interested in applied AI",
        "Industry partners in healthcare, agriculture, government",
        "Funding agencies (NSF, NIH, DOE, DARPA)",
        "Kentucky community stakeholders",
        "Peer AI research centers and institutes",
    ],
}


# ── Content Frames (Melissa's Templates) ───────────────────────────────

CONTENT_FRAMES: List[Dict[str, Any]] = [
    {
        "id": "thought_leadership",
        "name": "Thought Leadership",
        "description": (
            "Positions CAAI as a leading voice in applied AI. "
            "Commentary on trends, policy, responsible AI, and "
            "the future of AI in academia and industry."
        ),
        "post_structures": [
            {
                "name": "Hot Take / Trend Commentary",
                "template": (
                    "[Hook: Bold statement about an AI trend]\n\n"
                    "[2-3 sentences explaining CAAI's perspective]\n\n"
                    "[Call-to-action or question to drive engagement]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "The gap between AI research and real-world impact is growing. Here's how we're closing it.",
                    "Everyone's talking about AI in healthcare. Few are actually deploying it. We are.",
                    "The next frontier in AI isn't bigger models — it's better applications.",
                ],
            },
            {
                "name": "Insight / Data Share",
                "template": (
                    "[Compelling statistic or insight]\n\n"
                    "[Why this matters for applied AI]\n\n"
                    "[CAAI connection or action]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "Only 10% of AI research makes it into production. We're working to change that.",
                ],
            },
        ],
        "keywords": [
            "AI trends", "responsible AI", "AI policy", "future of AI",
            "AI ethics", "AI governance", "opinion", "perspective",
            "industry outlook", "AI adoption", "translational AI",
        ],
        "best_practices": [
            "Lead with a strong, specific claim",
            "Reference real data or concrete outcomes",
            "End with a question to drive comments",
            "Share a unique perspective, not consensus views",
        ],
        "suggested_cadence": "2-3 times per month",
    },
    {
        "id": "next_generation",
        "name": "Empowering the Next Generation",
        "description": (
            "Highlights student achievements, training programs, "
            "workshops, internships, and CAAI's role in building "
            "AI workforce capacity in Kentucky and beyond."
        ),
        "post_structures": [
            {
                "name": "Student Spotlight",
                "template": (
                    "[Student name and program]\n\n"
                    "[What they're working on at CAAI]\n\n"
                    "[Impact or outcome of their work]\n\n"
                    "[Encouragement / CTA]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "Meet [Name], a [program] student at CAAI who is building [project].",
                ],
            },
            {
                "name": "Workshop / Event Announcement",
                "template": (
                    "[Event name and date]\n\n"
                    "[Who it's for and what they'll learn]\n\n"
                    "[Registration or details link]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "Join us for [event] on [date] — learn how to [skill].",
                ],
            },
        ],
        "keywords": [
            "student", "graduate", "training", "workshop", "intern",
            "workforce", "education", "mentorship", "next generation",
            "career", "learning", "skills", "fellowship",
        ],
        "best_practices": [
            "Tag students and collaborators for amplification",
            "Use photos or video when possible",
            "Mention specific skills or tools learned",
            "Celebrate achievements with concrete metrics",
        ],
        "suggested_cadence": "2-4 times per month",
    },
    {
        "id": "project_showcase",
        "name": "Project Showcase",
        "description": (
            "Deep dives into CAAI projects, tools, and outcomes. "
            "Demonstrates real-world impact and technical capability."
        ),
        "post_structures": [
            {
                "name": "Project Highlight",
                "template": (
                    "[Project name and domain]\n\n"
                    "[Problem being solved]\n\n"
                    "[CAAI's approach and unique value]\n\n"
                    "[Results or current status]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "Our [project name] is transforming how [domain] works. Here's the story.",
                    "From research to deployment: How CAAI's [tool] is making a real difference.",
                ],
            },
            {
                "name": "Technical Deep Dive",
                "template": (
                    "[Technology or method spotlight]\n\n"
                    "[What makes this approach novel]\n\n"
                    "[Real-world application and results]\n\n"
                    "[Link to paper, demo, or code]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [],
            },
        ],
        "keywords": [
            "project", "launch", "deployment", "tool", "platform",
            "results", "impact", "research", "publication", "demo",
            "case study", "pipeline", "system",
        ],
        "best_practices": [
            "Focus on impact, not just technology",
            "Include concrete metrics when possible",
            "Link to published papers or press coverage",
            "Use before/after framing for impact stories",
        ],
        "suggested_cadence": "1-2 times per month",
    },
    {
        "id": "partnership_collaboration",
        "name": "Partnership & Collaboration",
        "description": (
            "Highlights partnerships with industry, other universities, "
            "government agencies, and community organizations."
        ),
        "post_structures": [
            {
                "name": "Partner Spotlight",
                "template": (
                    "[Partner name and relationship]\n\n"
                    "[What we're doing together]\n\n"
                    "[Mutual benefit / impact]\n\n"
                    "[Tag partner organization]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "Excited to announce our partnership with [org] to [goal].",
                    "Great things happen when [domain] meets applied AI. Our work with [partner].",
                ],
            },
            {
                "name": "Grant / Funding Announcement",
                "template": (
                    "[Funding source and amount]\n\n"
                    "[What the project will accomplish]\n\n"
                    "[Team and partners involved]\n\n"
                    "[Broader significance]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [],
            },
        ],
        "keywords": [
            "partner", "collaboration", "grant", "funding", "award",
            "NSF", "NIH", "DOE", "DARPA", "joint", "consortium",
            "MOU", "agreement", "co-PI",
        ],
        "best_practices": [
            "Always tag the partner organization",
            "Emphasize mutual benefit, not just CAAI's role",
            "Mention specific funding amounts when public",
            "Thank collaborators by name",
        ],
        "suggested_cadence": "1-2 times per month",
    },
    {
        "id": "behind_the_scenes",
        "name": "Behind the Scenes / Culture",
        "description": (
            "Shows the human side of CAAI — team events, lab tours, "
            "day-in-the-life content, and celebrations."
        ),
        "post_structures": [
            {
                "name": "Team Moment",
                "template": (
                    "[What's happening / why it matters]\n\n"
                    "[Personal touch or quote]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "A look inside our lab at [activity].",
                    "This is what building the future of AI looks like.",
                ],
            },
            {
                "name": "Milestone / Celebration",
                "template": (
                    "[Achievement or milestone]\n\n"
                    "[Who made it happen]\n\n"
                    "[What's next]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [],
            },
        ],
        "keywords": [
            "team", "culture", "lab", "office", "celebration",
            "milestone", "anniversary", "event", "retreat", "fun",
            "day in the life", "behind the scenes",
        ],
        "best_practices": [
            "Use authentic photos, not stock images",
            "Keep it human and relatable",
            "Show diversity of team and activities",
            "Short, personal tone works best",
        ],
        "suggested_cadence": "1-2 times per month",
    },
    {
        "id": "community_impact",
        "name": "Community Impact / Kentucky Focus",
        "description": (
            "Highlights CAAI's impact on Kentucky communities — "
            "rural AI access, state government analytics, agricultural "
            "AI, and workforce development."
        ),
        "post_structures": [
            {
                "name": "Impact Story",
                "template": (
                    "[Community or region]\n\n"
                    "[Challenge they face]\n\n"
                    "[How CAAI/AI is helping]\n\n"
                    "[Outcome or next steps]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [
                    "AI isn't just for Silicon Valley. Here's how it's transforming [Kentucky community].",
                    "In [county/region], farmers are using AI to [outcome]. We helped build it.",
                ],
            },
            {
                "name": "Extension / Outreach",
                "template": (
                    "[Program or initiative name]\n\n"
                    "[Who it serves]\n\n"
                    "[What participants gain]\n\n"
                    "[How to get involved]\n\n"
                    "[Hashtags]"
                ),
                "example_hooks": [],
            },
        ],
        "keywords": [
            "Kentucky", "rural", "community", "agriculture", "extension",
            "workforce", "outreach", "public service", "state government",
            "Appalachia", "local", "impact", "equity",
        ],
        "best_practices": [
            "Lead with the community, not the technology",
            "Include quotes from beneficiaries when possible",
            "Connect local impact to broader mission",
            "Mention specific locations and communities",
        ],
        "suggested_cadence": "1-2 times per month",
    },
]

# Build lookup for easy access
CONTENT_FRAME_BY_ID = {frame["id"]: frame for frame in CONTENT_FRAMES}


# ── Engagement Best Practices ──────────────────────────────────────────

ENGAGEMENT_BEST_PRACTICES = {
    "posting_times": {
        "best_days": ["Tuesday", "Wednesday", "Thursday"],
        "best_hours": ["8:00-9:00 AM", "12:00-1:00 PM", "5:00-6:00 PM"],
        "timezone": "US/Eastern",
    },
    "content_mix": {
        "thought_leadership": 0.25,
        "next_generation": 0.20,
        "project_showcase": 0.20,
        "partnership_collaboration": 0.15,
        "behind_the_scenes": 0.10,
        "community_impact": 0.10,
    },
    "engagement_tactics": [
        "Ask a question in every post",
        "Tag relevant people and organizations",
        "Respond to comments within 4 hours",
        "Use carousel posts for higher engagement",
        "Include 3-5 hashtags per post",
        "Use line breaks for readability",
        "Post consistently (8-12 times per month)",
        "Engage with other pages' content between posts",
    ],
    "post_length": {
        "optimal_words": "100-200",
        "max_characters": 3000,
        "hook_max_words": 15,
    },
}


# ── Industry Benchmarks for University AI Centers ──────────────────────

INDUSTRY_BENCHMARKS = {
    "engagement_rate": {
        "poor": 0.01,
        "good": 0.02,
        "excellent": 0.05,
        "label": "Engagement Rate",
    },
    "follower_growth_monthly": {
        "poor": 0.01,
        "good": 0.03,
        "excellent": 0.08,
        "label": "Monthly Follower Growth",
    },
    "impressions_per_post": {
        "poor": 200,
        "good": 500,
        "excellent": 2000,
        "label": "Impressions per Post",
    },
    "click_through_rate": {
        "poor": 0.005,
        "good": 0.02,
        "excellent": 0.05,
        "label": "Click-Through Rate",
    },
}


def classify_post_to_frame(text: str) -> Dict[str, Any]:
    """Classify a post's text to the best-matching content frame.

    Uses keyword matching similar to compute_match_score in caai_knowledge.py.

    Returns:
        {"frame_id": str, "frame_name": str, "score": int, "matched_keywords": list}
    """
    text_lower = text.lower()
    best_frame = None
    best_score = 0
    best_keywords = []

    for frame in CONTENT_FRAMES:
        matched = []
        for kw in frame.get("keywords", []):
            if kw.lower() in text_lower:
                matched.append(kw)
        score = len(matched)
        if score > best_score:
            best_score = score
            best_frame = frame
            best_keywords = matched

    if best_frame is None:
        return {
            "frame_id": "uncategorized",
            "frame_name": "Uncategorized",
            "score": 0,
            "matched_keywords": [],
        }

    return {
        "frame_id": best_frame["id"],
        "frame_name": best_frame["name"],
        "score": best_score,
        "matched_keywords": best_keywords,
    }


def get_benchmark_rating(metric: str, value: float) -> str:
    """Rate a metric value against industry benchmarks.

    Returns: "excellent", "good", "poor", or "unknown"
    """
    bench = INDUSTRY_BENCHMARKS.get(metric)
    if not bench:
        return "unknown"
    if value >= bench["excellent"]:
        return "excellent"
    if value >= bench["good"]:
        return "good"
    return "poor"
