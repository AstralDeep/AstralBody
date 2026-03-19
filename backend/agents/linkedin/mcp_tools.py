#!/usr/bin/env python3
"""
MCP Tools for the LinkedIn Agent.

Tools split into two categories:
  1. API Actions — require OAuth token (publish posts, react, comment, profile)
  2. Content Strategy — offline helpers using the CAAI knowledge base (draft, suggestions, engagement tips)
"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.a2ui_builders import (
    card, text, table, metric_card, alert, row, tabs,
    list_component, create_response, Node,
)
from agents.linkedin.linkedin_api import LinkedInClient, REACTION_TYPES
from agents.linkedin.caai_linkedin_knowledge import (
    CONTENT_FRAMES, CONTENT_FRAME_BY_ID,
    CAAI_BRAND_VOICE, ENGAGEMENT_BEST_PRACTICES, INDUSTRY_BENCHMARKS,
    LINKEDIN_PAGE,
    classify_post_to_frame, get_benchmark_rating,
    CAAI_MISSION, EXPERTISE_AREAS, KEY_PERSONNEL, PROJECT_HISTORY,
)

logger = logging.getLogger("LinkedInTools")


# ── Helpers ────────────────────────────────────────────────────────────

def _get_client(**kwargs) -> LinkedInClient:
    """Build a LinkedInClient using injected credentials or env vars."""
    creds = kwargs.get("_credentials", {})
    return LinkedInClient(credentials=creds)


def _no_token_alert() -> List[Node]:
    """Standard alert when API token is missing."""
    return [
        alert(
            "LinkedIn API not connected. Open the agent's settings panel "
            "and click 'Authorize with LinkedIn' to connect your account.",
            variant="warning",
            title="Authorization Required",
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 1 — Get My Profile
# ═══════════════════════════════════════════════════════════════════════

def get_my_profile(
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Retrieve the authenticated LinkedIn user's profile information.
    Shows name, headline, email, profile picture, and verification status.
    """
    client = _get_client(**kwargs)

    if not client.api_available:
        return create_response(_no_token_alert(), data={"status": "not_connected"})

    profile = client.get_my_profile()
    if not profile:
        return create_response([
            alert(
                "Failed to fetch profile. Your token may have expired — try re-authorizing.",
                variant="error", title="API Error",
            ),
        ], data={"status": "error"})

    name = profile.get("name", "Unknown")
    email = profile.get("email", "N/A")
    picture = profile.get("picture", "")
    person_id = profile.get("sub", "")
    verified = profile.get("email_verified", False)

    components = [
        card("LinkedIn Profile", [
            row([
                metric_card("Name", name),
                metric_card("Email", email),
                metric_card("Member ID", person_id or "N/A"),
            ]),
            text(
                f"Email verified: {'Yes' if verified else 'No'}",
                variant="caption",
            ),
            text(
                f"Person URN: urn:li:person:{person_id}" if person_id else "Person URN: N/A",
                variant="caption",
            ),
        ]),
    ]

    org_id = client.org_id
    if org_id:
        components.append(
            alert(
                f"Organization ID configured: {org_id} (urn:li:organization:{org_id})",
                variant="info",
                title="Linked Organization",
            )
        )

    return create_response(components, data={
        "name": name,
        "email": email,
        "person_id": person_id,
        "person_urn": f"urn:li:person:{person_id}" if person_id else None,
        "email_verified": verified,
        "org_id": org_id,
    })


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 2 — Publish Post
# ═══════════════════════════════════════════════════════════════════════

def publish_post(
    text: str,
    visibility: str = "PUBLIC",
    article_url: str = "",
    article_title: str = "",
    article_description: str = "",
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Publish a LinkedIn post as the authenticated user.
    Supports plain-text posts and article shares with commentary.

    Args:
        text: The post text / commentary. Max 3000 characters.
        visibility: PUBLIC, CONNECTIONS, or LOGGED_IN.
        article_url: Optional URL to share as an article attachment.
        article_title: Optional title for the article card.
        article_description: Optional description for the article card.
    """
    # Import the builder 'text' is shadowed by the parameter name
    from shared.a2ui_builders import text as text_node

    client = _get_client(**kwargs)

    if not client.api_available:
        return create_response(_no_token_alert(), data={"status": "not_connected"})

    if not text or not text.strip():
        return create_response([
            alert("Post text cannot be empty.", variant="error", title="Validation Error"),
        ])

    if len(text) > 3000:
        return create_response([
            alert(
                f"Post text is {len(text)} characters — LinkedIn allows a maximum of 3000.",
                variant="error",
                title="Too Long",
            ),
        ])

    result = client.create_post(
        text=text.strip(),
        visibility=visibility,
        article_url=article_url or None,
        article_title=article_title or None,
        article_description=article_description or None,
    )

    if result is None:
        return create_response([
            alert("Failed to create post — no response from LinkedIn.", variant="error"),
        ])

    if not result.get("success"):
        return create_response([
            alert(
                f"Post failed: {result.get('error', 'Unknown error')}",
                variant="error",
                title="Publish Failed",
            ),
        ], data=result)

    post_urn = result.get("post_urn", "")
    components = [
        alert("Post published successfully!", variant="success", title="Published"),
        card("Post Details", [
            text_node(text[:500] + ("..." if len(text) > 500 else ""), variant="body"),
            row([
                metric_card("Visibility", visibility),
                metric_card("Characters", str(len(text))),
                metric_card("Words", str(len(text.split()))),
            ]),
        ]),
    ]
    if article_url:
        components.append(
            text_node(f"Article: {article_title or article_url}", variant="caption")
        )
    if post_urn:
        components.append(
            text_node(f"Post URN: {post_urn}", variant="caption")
        )

    return create_response(components, data={
        "success": True,
        "post_urn": post_urn,
        "visibility": visibility,
        "character_count": len(text),
    })


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 3 — React to Post
# ═══════════════════════════════════════════════════════════════════════

def react_to_post(
    post_urn: str,
    reaction_type: str = "LIKE",
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """React to a LinkedIn post. Reaction types: LIKE, PRAISE (Celebrate),
    EMPATHY (Support), INTEREST (Curious), ENTERTAINMENT (Funny), APPRECIATION (Love).

    Args:
        post_urn: The URN of the post (e.g. urn:li:share:7012345678901234567).
        reaction_type: One of LIKE, PRAISE, EMPATHY, INTEREST, ENTERTAINMENT, APPRECIATION.
    """
    client = _get_client(**kwargs)

    if not client.api_available:
        return create_response(_no_token_alert(), data={"status": "not_connected"})

    if not post_urn or not post_urn.strip():
        return create_response([
            alert("post_urn is required. Provide the URN of the post to react to.", variant="error"),
        ])

    result = client.react_to_post(post_urn.strip(), reaction_type.upper())

    if result is None:
        return create_response([
            alert("Failed to react — no response from LinkedIn.", variant="error"),
        ])

    if not result.get("success"):
        return create_response([
            alert(
                f"Reaction failed: {result.get('error', 'Unknown error')}",
                variant="error",
            ),
        ], data=result)

    reaction_labels = {
        "LIKE": "Like", "PRAISE": "Celebrate", "EMPATHY": "Support",
        "INTEREST": "Curious", "ENTERTAINMENT": "Funny", "APPRECIATION": "Love",
    }
    label = reaction_labels.get(reaction_type.upper(), reaction_type)

    return create_response([
        alert(f"Reacted with '{label}' on the post.", variant="success", title="Reaction Added"),
        text(f"Post: {post_urn}", variant="caption"),
    ], data=result)


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 4 — Comment on Post
# ═══════════════════════════════════════════════════════════════════════

def comment_on_post(
    post_urn: str,
    text: str,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Add a comment to a LinkedIn post as the authenticated user.

    Args:
        post_urn: The URN of the post to comment on.
        text: The comment text.
    """
    from shared.a2ui_builders import text as text_node

    client = _get_client(**kwargs)

    if not client.api_available:
        return create_response(_no_token_alert(), data={"status": "not_connected"})

    if not post_urn or not post_urn.strip():
        return create_response([
            alert("post_urn is required.", variant="error"),
        ])
    if not text or not text.strip():
        return create_response([
            alert("Comment text cannot be empty.", variant="error"),
        ])

    result = client.comment_on_post(post_urn.strip(), text.strip())

    if result is None:
        return create_response([
            alert("Failed to comment — no response from LinkedIn.", variant="error"),
        ])

    if not result.get("success"):
        return create_response([
            alert(
                f"Comment failed: {result.get('error', 'Unknown error')}",
                variant="error",
            ),
        ], data=result)

    return create_response([
        alert("Comment posted successfully!", variant="success", title="Comment Added"),
        card("Comment", [
            text_node(text.strip(), variant="body"),
            text_node(f"On post: {post_urn}", variant="caption"),
        ]),
    ], data=result)


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 5 — Draft LinkedIn Post (offline — uses knowledge base)
# ═══════════════════════════════════════════════════════════════════════

def draft_linkedin_post(
    frame: str,
    topic: str,
    structure: str = "",
    tone_override: str = "",
    include_hashtags: bool = True,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Draft a ready-to-publish LinkedIn post using CAAI content frames
    and brand voice guidelines. Generates Standard, Concise, and Bold
    variations with a publishing checklist. Does NOT publish — use
    publish_post to send a draft to LinkedIn.

    Args:
        frame: Content frame id: thought_leadership, next_generation,
               project_showcase, partnership_collaboration,
               behind_the_scenes, community_impact
        topic: Topic or subject for the post
        structure: Optional specific post structure name within the frame
        tone_override: Optional tone adjustment (e.g. 'more casual')
        include_hashtags: Whether to include hashtags (default true)
    """
    target_frame = CONTENT_FRAME_BY_ID.get(frame)
    if not target_frame:
        valid = ", ".join(f'"{f["id"]}"' for f in CONTENT_FRAMES)
        return create_response([
            alert(f"Unknown content frame: '{frame}'. Valid: {valid}", variant="error", title="Invalid Frame")
        ])

    structures = target_frame.get("post_structures", [])
    target_struct = None
    if structure:
        target_struct = next((s for s in structures if s["name"].lower() == structure.lower()), None)
    if not target_struct and structures:
        target_struct = structures[0]
    if not target_struct:
        return create_response([
            alert(f"No post structures defined for frame '{frame}'", variant="error")
        ])

    template = target_struct.get("template", "")
    example_hooks = target_struct.get("example_hooks", [])
    hook = example_hooks[0] if example_hooks else f"[Strong opening about {topic}]"

    # Pull relevant CAAI context
    relevant_projects = [
        proj for proj in PROJECT_HISTORY
        if topic.lower() in proj.get("name", "").lower()
        or topic.lower() in proj.get("description", "").lower()
    ]
    relevant_expertise = [
        exp for exp in EXPERTISE_AREAS
        if topic.lower() in exp.get("area", "").lower()
        or any(topic.lower() in kw.lower() for kw in exp.get("keywords", []))
    ]

    # Build hashtags
    hashtags = []
    if include_hashtags:
        hashtags = list(CAAI_BRAND_VOICE["hashtags"][:5])
        for kw in target_frame.get("keywords", [])[:3]:
            tag = f"#{kw.replace(' ', '')}"
            if tag not in hashtags:
                hashtags.append(tag)
    hashtag_line = " ".join(hashtags)

    tone_note = CAAI_BRAND_VOICE["tone"]
    if tone_override:
        tone_note = f"{tone_note} (adjusted: {tone_override})"

    # Standard version
    standard_draft = f"{hook}\n\n{template}\n\nTopic: {topic}"
    if relevant_projects:
        proj = relevant_projects[0]
        standard_draft += f"\n\nCAAI Context: Our {proj.get('name', '')} project — {proj.get('description', '')}"
    if include_hashtags:
        standard_draft += f"\n\n{hashtag_line}"

    # Concise version
    concise_draft = f"{hook}\n\n{topic} — this is what applied AI looks like in action.\n\nLearn more: {LINKEDIN_PAGE['website']}"
    if include_hashtags:
        concise_draft += f"\n\n{' '.join(hashtags[:4])}"

    # Bold version
    bold_hook = f"Unpopular opinion: Most {topic.lower()} initiatives fail because they don't start with the problem."
    bold_draft = (
        f"{bold_hook}\n\n"
        f"At CAAI, we flip the script. We start with real-world challenges and work backwards to AI solutions.\n\n"
        f"{topic} isn't just a buzzword for us — it's our daily work.\n\n"
        f"What's your take?"
    )
    if include_hashtags:
        bold_draft += f"\n\n{hashtag_line}"

    drafts = [
        {"variant": "Standard", "text": standard_draft, "word_count": len(standard_draft.split()), "char_count": len(standard_draft)},
        {"variant": "Concise", "text": concise_draft, "word_count": len(concise_draft.split()), "char_count": len(concise_draft)},
        {"variant": "Bold", "text": bold_draft, "word_count": len(bold_draft.split()), "char_count": len(bold_draft)},
    ]

    checklist = [
        "Tagged relevant people or organizations?",
        "Includes a clear call-to-action or question?",
        "Uses 3-5 relevant hashtags?",
        f"Under {ENGAGEMENT_BEST_PRACTICES['post_length']['max_characters']} characters?",
        f"Optimal length ({ENGAGEMENT_BEST_PRACTICES['post_length']['optimal_words']} words)?",
        "Includes a link or media attachment?",
        "Reviewed for brand voice consistency?",
    ]

    # Build UI
    draft_tab_labels = [d["variant"] for d in drafts]
    draft_tab_children = []
    for d in drafts:
        draft_tab_children.append([
            text(d["text"], variant="body"),
            text(f"Words: {d['word_count']} | Characters: {d['char_count']}", variant="caption"),
        ])

    card_content = [
        text(f"Frame: {target_frame['name']} | Structure: {target_struct['name']} | Topic: {topic}", variant="caption"),
        alert(f"Brand voice: {tone_note}", variant="info", title="Tone Guide"),
        tabs(draft_tab_labels, draft_tab_children),
        alert(
            "These are drafts. Use the 'publish_post' tool to send one to LinkedIn.",
            variant="info",
            title="Next Step",
        ),
        card("Post Checklist", [
            list_component([text(item) for item in checklist]),
        ], collapsible=True),
        card(f"Best Practices: {target_frame['name']}", [
            list_component([text(item) for item in target_frame.get("best_practices", [])]),
        ], collapsible=True),
    ]

    if relevant_projects or relevant_expertise:
        context_items = []
        for exp in relevant_expertise[:2]:
            context_items.append(f"Expertise: {exp.get('area', '')} — {exp.get('description', '')[:100]}")
        for proj in relevant_projects[:2]:
            context_items.append(f"Project: {proj.get('name', '')} — {proj.get('description', '')[:100]}")
        card_content.append(
            card("Relevant CAAI Context", [
                list_component([text(item) for item in context_items]),
            ], collapsible=True)
        )

    components = [card("LinkedIn Post Draft", card_content)]

    return create_response(components, data={
        "frame": target_frame["name"],
        "structure": target_struct["name"],
        "topic": topic,
        "drafts": drafts,
        "hashtags": hashtags,
        "checklist": checklist,
    })


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 6 — Get Content Suggestions (offline)
# ═══════════════════════════════════════════════════════════════════════

def get_content_suggestions(
    frame: str = "all",
    topic: str = "",
    count: int = 3,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Generate content ideas using CAAI content frames.
    Frames: Thought Leadership, Empowering the Next Generation,
    Project Showcase, Partnership & Collaboration, Behind the Scenes,
    and Community Impact.

    Args:
        frame: Content frame id or 'all'.
        topic: Optional specific topic focus.
        count: Number of suggestions per frame (default 3).
    """
    if frame == "all":
        target_frames = CONTENT_FRAMES
    else:
        target_frame = CONTENT_FRAME_BY_ID.get(frame)
        if not target_frame:
            valid = ", ".join(f'"{f["id"]}"' for f in CONTENT_FRAMES)
            return create_response([
                alert(f"Unknown content frame: '{frame}'. Valid: {valid}", variant="error", title="Invalid Frame")
            ])
        target_frames = [target_frame]

    all_suggestions = []
    frame_components = []

    for fr in target_frames:
        suggestions = []
        for struct in fr.get("post_structures", []):
            template = struct.get("template", "")
            example_hooks = struct.get("example_hooks", [])

            for i in range(min(count, max(1, len(example_hooks) if example_hooks else 1))):
                hook = example_hooks[i] if i < len(example_hooks) else f"[Your hook about {topic or fr['name']}]"
                if topic:
                    hook = hook.replace("[topic]", topic).replace("[subject]", topic)

                outline = f"Structure: {struct['name']}\n\nHook: {hook}\n\nTemplate:\n{template}"
                if topic:
                    outline += f"\n\nTopic Focus: {topic}"

                relevant_hashtags = list(CAAI_BRAND_VOICE["hashtags"][:5])
                for kw in fr.get("keywords", [])[:3]:
                    tag = f"#{kw.replace(' ', '')}"
                    if tag not in relevant_hashtags:
                        relevant_hashtags.append(tag)

                suggestions.append({
                    "frame": fr["name"],
                    "frame_id": fr["id"],
                    "structure": struct["name"],
                    "outline": outline,
                    "hashtags": relevant_hashtags,
                })

        all_suggestions.extend(suggestions)

        tab_labels = [s["structure"] for s in suggestions]
        tab_children = []
        for s in suggestions:
            tab_children.append([
                text(s["outline"], variant="body"),
                text(f"Suggested hashtags: {' '.join(s['hashtags'])}", variant="caption"),
            ])

        practices = list_component([text(p) for p in fr.get("best_practices", [])])

        frame_content = [
            text(fr["description"], variant="caption"),
            text(f"Suggested cadence: {fr.get('suggested_cadence', 'N/A')}", variant="caption"),
            tabs(tab_labels, tab_children) if tab_labels else text("No templates for this frame.", variant="body"),
            card("Best Practices", [practices], collapsible=True),
        ]

        frame_card = card(fr["name"], frame_content)
        frame_components.append(frame_card)

    return create_response(frame_components, data={
        "frames_covered": [fr["id"] for fr in target_frames],
        "suggestions": all_suggestions,
    })


# ═══════════════════════════════════════════════════════════════════════
#  TOOL 7 — Suggest Engagement Actions (offline)
# ═══════════════════════════════════════════════════════════════════════

def suggest_engagement_actions(
    focus: str = "all",
    current_followers: int = 0,
    current_engagement_rate: float = 0.0,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Generate actionable suggestions to grow LinkedIn presence.
    Provides Quick Wins, Weekly Actions, Strategic initiatives,
    and a content calendar based on best practices.

    Args:
        focus: Focus area — 'all', 'followers', 'engagement', or 'content'.
        current_followers: Current follower count (optional context).
        current_engagement_rate: Current engagement rate as decimal (optional).
    """
    eng_rate = current_engagement_rate
    followers = current_followers
    eng_rating = get_benchmark_rating("engagement_rate", eng_rate) if eng_rate > 0 else "unknown"

    quick_wins = [
        "Respond to all pending comments on recent posts (builds algorithmic favor)",
        "Like and comment on 5 posts from partner organizations today",
        "Add a call-to-action question to your next scheduled post",
        "Update the company page tagline and description with current focus areas",
        "Share a team member's personal post to the company page",
    ]

    weekly_actions = [
        f"Post {ENGAGEMENT_BEST_PRACTICES['posting_times']['best_days'][0]} at {ENGAGEMENT_BEST_PRACTICES['posting_times']['best_hours'][0]} ET (peak engagement window)",
        "Create a carousel post highlighting a recent CAAI project outcome",
        "Tag 3-5 collaborators or partner organizations in your next post",
        "Share a 'behind the scenes' photo from the lab or a team meeting",
        "Engage with 10+ posts in your industry feed to boost page visibility",
        "Repurpose a recent grant win or publication as a LinkedIn post",
    ]

    strategic_actions = [
        "Develop a monthly content calendar using the 6 content frames",
        "Launch an employee advocacy program — team members share company posts",
        "Create a LinkedIn newsletter for the CAAI page (weekly AI insights)",
        "Partner with 2-3 peer AI centers for cross-promotion",
        "Develop a signature hashtag campaign (e.g., #AppliedAIKentucky)",
        "Create a series format (e.g., 'Applied AI Wednesdays' weekly posts)",
        "Invest in LinkedIn document/carousel posts (2-3x engagement vs. text)",
    ]

    if focus == "followers":
        quick_wins = [q for q in quick_wins if any(kw in q.lower() for kw in ["follow", "page", "share", "tag"])]
        strategic_actions = [s for s in strategic_actions if any(kw in s.lower() for kw in ["advocacy", "newsletter", "partner", "campaign"])]
    elif focus == "engagement":
        quick_wins = [q for q in quick_wins if any(kw in q.lower() for kw in ["comment", "respond", "question", "like"])]
        strategic_actions = [s for s in strategic_actions if any(kw in s.lower() for kw in ["carousel", "series", "content"])]
    elif focus == "content":
        quick_wins = [q for q in quick_wins if any(kw in q.lower() for kw in ["post", "update", "share"])]

    content_mix = ENGAGEMENT_BEST_PRACTICES["content_mix"]
    best_days = ENGAGEMENT_BEST_PRACTICES["posting_times"]["best_days"]
    best_hours = ENGAGEMENT_BEST_PRACTICES["posting_times"]["best_hours"]

    calendar = []
    sorted_mix = sorted(content_mix.items(), key=lambda x: x[1], reverse=True)
    for i, (frame_id, weight) in enumerate(sorted_mix):
        fr = CONTENT_FRAME_BY_ID.get(frame_id, {})
        day = best_days[i % len(best_days)]
        hour = best_hours[i % len(best_hours)]
        calendar.append([day, hour, fr.get("name", frame_id), f"{weight:.0%}", "High" if weight >= 0.20 else "Medium"])

    metrics_grid = row([
        metric_card("Current Followers", f"{followers:,}" if followers > 0 else "Not set"),
        metric_card("Engagement Rate", f"{eng_rate:.1%}" if eng_rate > 0 else "Not set"),
        metric_card("Engagement Rating", eng_rating.upper() if eng_rate > 0 else "N/A"),
    ])

    engagement_tabs = tabs(
        ["Quick Wins", "This Week", "Strategic", "Content Calendar"],
        [
            [
                text("Actions you can take in under an hour:", variant="caption"),
                list_component([text(item) for item in quick_wins]),
            ],
            [
                text("Tactical moves for this week:", variant="caption"),
                list_component([text(item) for item in weekly_actions]),
            ],
            [
                text("Longer-term initiatives for sustained growth:", variant="caption"),
                list_component([text(item) for item in strategic_actions]),
            ],
            [
                text("Suggested weekly posting schedule:", variant="caption"),
                table(
                    ["Day", "Time (ET)", "Content Frame", "Mix Weight", "Priority"],
                    calendar,
                ),
            ],
        ],
    )

    components = [
        card("Engagement Growth Recommendations", [
            text(f"Focus: {focus.title()}", variant="caption"),
            metrics_grid,
            engagement_tabs,
        ]),
    ]

    return create_response(components, data={
        "focus": focus,
        "current_followers": followers,
        "current_engagement_rate": eng_rate,
        "engagement_rating": eng_rating,
        "quick_wins": quick_wins,
        "weekly_actions": weekly_actions,
        "strategic_actions": strategic_actions,
        "calendar": [{"day": c[0], "time": c[1], "frame": c[2], "priority": c[4]} for c in calendar],
    })


# ═══════════════════════════════════════════════════════════════════════
#  Tool Registry
# ═══════════════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_my_profile": {
        "function": get_my_profile,
        "scope": "tools:search",
        "description": (
            "Show the authenticated LinkedIn user's profile — name, email, "
            "member ID, and linked organization. Useful for verifying the "
            "connection is working."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "publish_post": {
        "function": publish_post,
        "scope": "tools:write",
        "description": (
            "Publish a LinkedIn post as the authenticated user. Supports "
            "plain-text posts and article shares with commentary. Use "
            "draft_linkedin_post first to prepare content, then publish_post "
            "to send it live."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The post text / commentary (max 3000 characters)",
                },
                "visibility": {
                    "type": "string",
                    "description": "Post visibility: PUBLIC, CONNECTIONS, or LOGGED_IN",
                    "default": "PUBLIC",
                    "enum": ["PUBLIC", "CONNECTIONS", "LOGGED_IN"],
                },
                "article_url": {
                    "type": "string",
                    "description": "Optional URL to share as an article attachment",
                    "default": "",
                },
                "article_title": {
                    "type": "string",
                    "description": "Optional title for the article card",
                    "default": "",
                },
                "article_description": {
                    "type": "string",
                    "description": "Optional description for the article card",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    "react_to_post": {
        "function": react_to_post,
        "scope": "tools:write",
        "description": (
            "React to a LinkedIn post. Reaction types: LIKE, PRAISE (Celebrate), "
            "EMPATHY (Support), INTEREST (Curious), ENTERTAINMENT (Funny), "
            "APPRECIATION (Love). Requires the post URN."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "post_urn": {
                    "type": "string",
                    "description": "The URN of the post (e.g. urn:li:share:7012345678901234567)",
                },
                "reaction_type": {
                    "type": "string",
                    "description": "Reaction type",
                    "default": "LIKE",
                    "enum": ["LIKE", "PRAISE", "EMPATHY", "INTEREST", "ENTERTAINMENT", "APPRECIATION"],
                },
            },
            "required": ["post_urn"],
        },
    },
    "comment_on_post": {
        "function": comment_on_post,
        "scope": "tools:write",
        "description": (
            "Add a comment to a LinkedIn post as the authenticated user. "
            "Requires the post URN and comment text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "post_urn": {
                    "type": "string",
                    "description": "The URN of the post to comment on",
                },
                "text": {
                    "type": "string",
                    "description": "The comment text",
                },
            },
            "required": ["post_urn", "text"],
        },
    },
    "draft_linkedin_post": {
        "function": draft_linkedin_post,
        "scope": "tools:read",
        "description": (
            "Draft a LinkedIn post using CAAI content frames and brand voice. "
            "Generates Standard, Concise, and Bold variations with a checklist. "
            "Does NOT publish — use publish_post to send it live."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "frame": {
                    "type": "string",
                    "description": "Content frame: thought_leadership, next_generation, project_showcase, partnership_collaboration, behind_the_scenes, community_impact",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic or subject for the post",
                },
                "structure": {
                    "type": "string",
                    "description": "Optional specific post structure name within the frame",
                    "default": "",
                },
                "tone_override": {
                    "type": "string",
                    "description": "Optional tone adjustment (e.g. 'more casual', 'more formal')",
                    "default": "",
                },
                "include_hashtags": {
                    "type": "boolean",
                    "description": "Whether to include hashtags",
                    "default": True,
                },
            },
            "required": ["frame", "topic"],
        },
    },
    "get_content_suggestions": {
        "function": get_content_suggestions,
        "scope": "tools:read",
        "description": (
            "Generate content ideas using CAAI content frames: Thought Leadership, "
            "Empowering the Next Generation, Project Showcase, Partnership & Collaboration, "
            "Behind the Scenes, and Community Impact. No API connection required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "frame": {
                    "type": "string",
                    "description": "Content frame id or 'all'",
                    "default": "all",
                },
                "topic": {
                    "type": "string",
                    "description": "Specific topic to focus suggestions on",
                    "default": "",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of suggestions per frame",
                    "default": 3,
                },
            },
            "required": [],
        },
    },
    "suggest_engagement_actions": {
        "function": suggest_engagement_actions,
        "scope": "tools:read",
        "description": (
            "Get actionable recommendations to grow LinkedIn presence — "
            "Quick Wins, Weekly Actions, Strategic initiatives, and a "
            "content calendar based on best practices. No API connection required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "Focus area: 'all', 'followers', 'engagement', or 'content'",
                    "default": "all",
                    "enum": ["all", "followers", "engagement", "content"],
                },
                "current_followers": {
                    "type": "integer",
                    "description": "Current follower count (optional context)",
                    "default": 0,
                },
                "current_engagement_rate": {
                    "type": "number",
                    "description": "Current engagement rate as decimal (e.g. 0.035 for 3.5%)",
                    "default": 0.0,
                },
            },
            "required": [],
        },
    },
}
