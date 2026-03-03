#!/usr/bin/env python3
"""
MCP Tools for the LinkedIn Engagement Driver Agent.

Provides tools for analyzing and driving engagement on the
UKy Center for Applied AI LinkedIn company page.
"""
import os
import sys
import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Alert, MetricCard, Grid,
    BarChart, PieChart, LineChart, List_, Collapsible, Tabs, TabItem,
    create_ui_response,
)
from agents.linkedin.linkedin_api import LinkedInClient
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


def _manual_input_alert(data_type: str, json_format: str) -> List:
    """Return standard manual-input fallback UI components."""
    return [
        Alert(
            message=(
                f"LinkedIn API credentials not configured. "
                f"You can provide {data_type} manually using the appropriate parameter, "
                f"or set your credentials via the agent credentials API."
            ),
            variant="info",
            title="API Not Connected",
        ),
        Text(
            content=f"Expected JSON format for manual input:\n```\n{json_format}\n```",
            variant="caption",
        ),
    ]


def _parse_manual_json(raw: str, label: str) -> Optional[Any]:
    """Try to parse a manual JSON string, returning None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse manual {label} JSON: {e}")
        return None


# ── Tool 1: Analyze LinkedIn Posts ─────────────────────────────────────

def analyze_linkedin_posts(
    count: int = 20,
    manual_posts: str = "",
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Analyze recent posts from the CAAI LinkedIn page. Categorizes each post
    by content frame, computes engagement metrics, and identifies top performers.

    Args:
        count: Number of recent posts to analyze (default 20)
        manual_posts: JSON array of post data for manual input fallback
    """
    client = _get_client(**kwargs)
    posts_data = None

    # Try API first
    if client.api_available:
        raw_posts = client.get_org_posts(count)
        if raw_posts is not None:
            posts_data = []
            for p in raw_posts:
                text = p.get("commentary", p.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get("text", ""))
                created = p.get("createdAt", p.get("created", {}).get("time", 0))
                if isinstance(created, int) and created > 1e12:
                    created = created // 1000
                stats = p.get("socialMetrics", {})
                posts_data.append({
                    "text": text,
                    "date": datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else "Unknown",
                    "likes": stats.get("numLikes", 0),
                    "comments": stats.get("numComments", 0),
                    "shares": stats.get("numShares", 0),
                    "impressions": stats.get("numImpressions", 0),
                })

    # Try manual input
    if posts_data is None:
        posts_data = _parse_manual_json(manual_posts, "manual_posts")

    # No data available — show instructions
    if not posts_data:
        fmt = '[{"text": "Post text...", "date": "2025-01-15", "likes": 42, "comments": 8, "shares": 5, "impressions": 1200}]'
        components = _manual_input_alert("post data", fmt)
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"status": "no_data", "message": "No post data available. Provide manual_posts or configure LinkedIn API credentials."},
        }

    # Analyze posts
    total_engagement = 0
    frame_counts = Counter()
    frame_engagement = {}
    analyzed = []

    for post in posts_data:
        text = post.get("text", "")
        likes = post.get("likes", 0)
        comments = post.get("comments", 0)
        shares = post.get("shares", 0)
        impressions = post.get("impressions", 0)
        engagement = likes + comments + shares
        total_engagement += engagement
        rate = engagement / impressions if impressions > 0 else 0.0

        classification = classify_post_to_frame(text)
        frame_id = classification["frame_id"]
        frame_counts[frame_id] += 1
        frame_engagement.setdefault(frame_id, []).append(rate)

        analyzed.append({
            "date": post.get("date", "Unknown"),
            "preview": text[:80] + ("..." if len(text) > 80 else ""),
            "frame": classification["frame_name"],
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "engagement_rate": f"{rate:.1%}",
            "full_text": text,
        })

    # Sort by engagement
    analyzed.sort(key=lambda x: x["likes"] + x["comments"] + x["shares"], reverse=True)

    avg_engagement = total_engagement / len(posts_data) if posts_data else 0
    avg_rate = sum(
        float(p["engagement_rate"].strip("%")) for p in analyzed
    ) / len(analyzed) / 100 if analyzed else 0.0

    top_frame = frame_counts.most_common(1)[0][0] if frame_counts else "N/A"
    top_frame_name = CONTENT_FRAME_BY_ID.get(top_frame, {}).get("name", top_frame)

    # Build UI
    metrics = Grid(columns=4, children=[
        MetricCard(title="Posts Analyzed", value=str(len(posts_data))),
        MetricCard(title="Avg Engagement Rate", value=f"{avg_rate:.1%}"),
        MetricCard(title="Top Content Frame", value=top_frame_name),
        MetricCard(title="Total Engagement", value=str(total_engagement)),
    ])

    table = Table(
        headers=["Date", "Preview", "Frame", "Likes", "Comments", "Shares", "Eng. Rate"],
        rows=[[p["date"], p["preview"], p["frame"], str(p["likes"]), str(p["comments"]), str(p["shares"]), p["engagement_rate"]] for p in analyzed],
    )

    pie_labels = [CONTENT_FRAME_BY_ID.get(k, {}).get("name", k) for k in frame_counts.keys()]
    pie_values = [float(v) for v in frame_counts.values()]
    pie = PieChart(title="Post Distribution by Content Frame", labels=pie_labels, data=pie_values)

    bar_labels = []
    bar_values = []
    for fid, rates in frame_engagement.items():
        avg = sum(rates) / len(rates) if rates else 0
        bar_labels.append(CONTENT_FRAME_BY_ID.get(fid, {}).get("name", fid))
        bar_values.append(round(avg * 100, 2))
    bar = BarChart(title="Avg Engagement Rate by Frame (%)", labels=bar_labels, datasets=[{"label": "Engagement Rate (%)", "data": bar_values, "color": "#4f46e5"}])

    # Top 3 posts detail
    top_posts_ui = []
    for i, p in enumerate(analyzed[:3]):
        top_posts_ui.append(Collapsible(
            title=f"#{i+1}: {p['preview']}",
            content=[
                Text(content=p["full_text"], variant="body"),
                Text(content=f"Frame: {p['frame']} | Likes: {p['likes']} | Comments: {p['comments']} | Shares: {p['shares']} | Rate: {p['engagement_rate']}", variant="caption"),
            ],
        ))

    components = [metrics, table, pie, bar] + top_posts_ui

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "posts_analyzed": len(posts_data),
            "avg_engagement_rate": round(avg_rate, 4),
            "total_engagement": total_engagement,
            "frame_distribution": dict(frame_counts),
            "top_post": analyzed[0] if analyzed else None,
            "posts": analyzed,
        },
    }


# ── Tool 2: Get Page Metrics ──────────────────────────────────────────

def get_page_metrics(
    period: str = "30d",
    manual_metrics: str = "",
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Report metrics on the CAAI LinkedIn page — followers, engagement rates,
    impressions, and audience breakdown.

    Args:
        period: Time period — "7d", "30d", "90d", or "all"
        manual_metrics: JSON object with metrics for manual input
    """
    client = _get_client(**kwargs)
    metrics = None

    if client.api_available:
        follower_count = client.get_follower_count()
        page_stats = client.get_page_stats()

        if follower_count is not None:
            total_stats = (page_stats or {}).get("totalShareStatistics", {})
            metrics = {
                "followers": follower_count,
                "follower_growth": 0,
                "impressions": total_stats.get("impressionCount", 0),
                "clicks": total_stats.get("clickCount", 0),
                "engagement_rate": total_stats.get("engagement", 0),
                "posts_count": total_stats.get("shareCount", 0),
                "period": period,
            }

    if metrics is None:
        metrics = _parse_manual_json(manual_metrics, "manual_metrics")

    if not metrics:
        fmt = '{"followers": 500, "follower_growth": 25, "impressions": 12000, "engagement_rate": 0.035, "posts_count": 15}'
        components = _manual_input_alert("page metrics", fmt)
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"status": "no_data", "message": "No metrics available. Provide manual_metrics or configure LinkedIn API credentials."},
        }

    followers = metrics.get("followers", 0)
    growth = metrics.get("follower_growth", 0)
    impressions = metrics.get("impressions", 0)
    eng_rate = metrics.get("engagement_rate", 0.0)
    posts_count = metrics.get("posts_count", 0)

    eng_rating = get_benchmark_rating("engagement_rate", eng_rate)

    metric_grid = Grid(columns=4, children=[
        MetricCard(title="Total Followers", value=f"{followers:,}"),
        MetricCard(title=f"Follower Growth ({period})", value=f"+{growth:,}" if growth >= 0 else str(growth)),
        MetricCard(title="Engagement Rate", value=f"{eng_rate:.1%}"),
        MetricCard(title="Total Impressions", value=f"{impressions:,}"),
    ])

    # Benchmark comparison
    bench_items = []
    for metric_key, bench in INDUSTRY_BENCHMARKS.items():
        current = metrics.get(metric_key, 0)
        if isinstance(current, (int, float)) and current > 0:
            rating = get_benchmark_rating(metric_key, current)
            bench_items.append(
                Text(content=f"{bench['label']}: {current} (Rating: {rating.upper()}, Excellent target: {bench['excellent']})", variant="body")
            )

    bench_card = Card(title="Performance vs. Benchmarks", content=bench_items) if bench_items else None

    practices = List_(
        items=ENGAGEMENT_BEST_PRACTICES["engagement_tactics"],
        variant="default",
    )
    practices_collapsible = Collapsible(
        title="Engagement Best Practices",
        content=[practices],
    )

    components = [metric_grid]
    if bench_card:
        components.append(bench_card)
    components.append(practices_collapsible)

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "followers": followers,
            "follower_growth": growth,
            "engagement_rate": eng_rate,
            "impressions": impressions,
            "posts_count": posts_count,
            "period": period,
            "engagement_rating": eng_rating,
        },
    }


# ── Tool 3: Get Content Suggestions ───────────────────────────────────

def get_content_suggestions(
    frame: str = "all",
    topic: str = "",
    count: int = 3,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Generate templated content suggestions within Melissa's designed content
    frames for the CAAI LinkedIn page.

    Args:
        frame: Content frame id (e.g. "thought_leadership", "next_generation") or "all"
        topic: Optional specific topic to generate suggestions about
        count: Number of suggestions per frame (default 3)
    """
    if frame == "all":
        target_frames = CONTENT_FRAMES
    else:
        target_frame = CONTENT_FRAME_BY_ID.get(frame)
        if not target_frame:
            valid = ", ".join(f'"{f["id"]}"' for f in CONTENT_FRAMES)
            return create_ui_response([
                Alert(message=f"Unknown content frame: '{frame}'. Valid frames: {valid}", variant="error", title="Invalid Frame")
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

        # Build UI per frame
        tab_items = []
        for j, s in enumerate(suggestions):
            tab_items.append(TabItem(
                label=s["structure"],
                content=[
                    Text(content=s["outline"], variant="body"),
                    Text(content=f"Suggested hashtags: {' '.join(s['hashtags'])}", variant="caption"),
                ],
            ))

        practices_list = List_(items=fr.get("best_practices", []), variant="default")

        frame_card = Card(
            title=fr["name"],
            content=[
                Text(content=fr["description"], variant="caption"),
                Text(content=f"Suggested cadence: {fr.get('suggested_cadence', 'N/A')}", variant="caption"),
                Tabs(tabs=tab_items) if tab_items else Text(content="No templates defined for this frame.", variant="body"),
                Collapsible(title="Best Practices", content=[practices_list]),
            ],
        )
        frame_components.append(frame_card)

    return {
        "_ui_components": [c.to_json() for c in frame_components],
        "_data": {
            "frames_covered": [fr["id"] for fr in target_frames],
            "suggestions": all_suggestions,
        },
    }


# ── Tool 4: Draft LinkedIn Post ───────────────────────────────────────

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
    """Draft a complete, ready-to-publish LinkedIn post for the CAAI page
    using the specified content frame template and CAAI brand voice.

    Args:
        frame: Content frame id (e.g. "thought_leadership", "next_generation")
        topic: Topic or subject for the post
        structure: Optional specific post structure name within the frame
        tone_override: Optional tone adjustment (e.g. "more casual", "more formal")
        include_hashtags: Whether to include hashtags (default true)
    """
    target_frame = CONTENT_FRAME_BY_ID.get(frame)
    if not target_frame:
        valid = ", ".join(f'"{f["id"]}"' for f in CONTENT_FRAMES)
        return create_ui_response([
            Alert(message=f"Unknown content frame: '{frame}'. Valid frames: {valid}", variant="error", title="Invalid Frame")
        ])

    structures = target_frame.get("post_structures", [])
    target_struct = None
    if structure:
        target_struct = next((s for s in structures if s["name"].lower() == structure.lower()), None)
    if not target_struct and structures:
        target_struct = structures[0]
    if not target_struct:
        return create_ui_response([
            Alert(message=f"No post structures defined for frame '{frame}'", variant="error")
        ])

    template = target_struct.get("template", "")
    example_hooks = target_struct.get("example_hooks", [])
    hook = example_hooks[0] if example_hooks else f"[Strong opening about {topic}]"

    # Pull relevant CAAI context
    relevant_projects = []
    for proj in PROJECT_HISTORY:
        proj_name = proj.get("name", "")
        proj_desc = proj.get("description", "")
        if topic.lower() in proj_name.lower() or topic.lower() in proj_desc.lower():
            relevant_projects.append(proj)

    relevant_expertise = []
    for exp in EXPERTISE_AREAS:
        area_name = exp.get("area", "")
        if topic.lower() in area_name.lower() or any(topic.lower() in kw.lower() for kw in exp.get("keywords", [])):
            relevant_expertise.append(exp)

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
    bold_draft = f"{bold_hook}\n\nAt CAAI, we flip the script. We start with real-world challenges and work backwards to AI solutions.\n\n{topic} isn't just a buzzword for us — it's our daily work.\n\nWhat's your take?"
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
    draft_tabs = []
    for d in drafts:
        draft_tabs.append(TabItem(
            label=d["variant"],
            content=[
                Text(content=d["text"], variant="body"),
                Text(content=f"Words: {d['word_count']} | Characters: {d['char_count']}", variant="caption"),
            ],
        ))

    card_content = [
        Text(content=f"Frame: {target_frame['name']} | Structure: {target_struct['name']} | Topic: {topic}", variant="caption"),
        Alert(message=f"Brand voice: {tone_note}", variant="info", title="Tone Guide"),
        Tabs(tabs=draft_tabs),
        Collapsible(title="Post Checklist", content=[
            List_(items=checklist, variant="default"),
        ]),
        Collapsible(title=f"Best Practices: {target_frame['name']}", content=[
            List_(items=target_frame.get("best_practices", []), variant="default"),
        ]),
    ]

    # Add CAAI context if relevant
    if relevant_projects or relevant_expertise:
        context_items = []
        if relevant_expertise:
            for exp in relevant_expertise[:2]:
                context_items.append(f"Expertise: {exp.get('area', '')} — {exp.get('description', '')[:100]}")
        if relevant_projects:
            for proj in relevant_projects[:2]:
                context_items.append(f"Project: {proj.get('name', '')} — {proj.get('description', '')[:100]}")
        card_content.append(
            Collapsible(title="Relevant CAAI Context", content=[
                List_(items=context_items, variant="default"),
            ])
        )

    components = [Card(title="LinkedIn Post Draft", content=card_content)]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "frame": target_frame["name"],
            "structure": target_struct["name"],
            "topic": topic,
            "drafts": drafts,
            "hashtags": hashtags,
            "checklist": checklist,
        },
    }


# ── Tool 5: Generate Weekly Digest ────────────────────────────────────

def generate_weekly_digest(
    week_offset: int = 0,
    manual_posts: str = "",
    manual_metrics: str = "",
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Generate a weekly LinkedIn engagement digest combining post performance,
    content gap analysis, and next-week recommendations.

    Args:
        week_offset: 0 = current week, 1 = last week, etc.
        manual_posts: JSON array of post data for the week
        manual_metrics: JSON object with page-level metrics for the week
    """
    client = _get_client(**kwargs)

    today = datetime.now()
    week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
    week_end = week_start + timedelta(days=6)
    week_label = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

    # Get post data
    posts_data = None
    if client.api_available:
        raw_posts = client.get_org_posts(50)
        if raw_posts:
            posts_data = []
            for p in raw_posts:
                text = p.get("commentary", "")
                created = p.get("createdAt", 0)
                if isinstance(created, int) and created > 1e12:
                    created = created // 1000
                post_date = datetime.fromtimestamp(created) if created else None
                if post_date and week_start.date() <= post_date.date() <= week_end.date():
                    stats = p.get("socialMetrics", {})
                    posts_data.append({
                        "text": text,
                        "date": post_date.strftime("%Y-%m-%d"),
                        "likes": stats.get("numLikes", 0),
                        "comments": stats.get("numComments", 0),
                        "shares": stats.get("numShares", 0),
                        "impressions": stats.get("numImpressions", 0),
                    })

    if posts_data is None:
        posts_data = _parse_manual_json(manual_posts, "manual_posts") or []

    # Get page metrics
    page_metrics = None
    if client.api_available:
        follower_count = client.get_follower_count()
        if follower_count is not None:
            page_metrics = {"followers": follower_count, "follower_change": 0}

    if page_metrics is None:
        page_metrics = _parse_manual_json(manual_metrics, "manual_metrics") or {}

    if not posts_data and not page_metrics:
        posts_fmt = '[{"text": "...", "date": "2025-01-15", "likes": 42, "comments": 8, "shares": 5, "impressions": 1200}]'
        metrics_fmt = '{"followers": 500, "follower_change": 12}'
        components = _manual_input_alert("post and metrics data", f"manual_posts: {posts_fmt}\nmanual_metrics: {metrics_fmt}")
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"status": "no_data", "week": week_label},
        }

    # Analyze
    total_engagement = sum(p.get("likes", 0) + p.get("comments", 0) + p.get("shares", 0) for p in posts_data)
    frame_counts = Counter()
    for p in posts_data:
        classification = classify_post_to_frame(p.get("text", ""))
        frame_counts[classification["frame_id"]] += 1

    used_frames = set(frame_counts.keys())
    all_frame_ids = {f["id"] for f in CONTENT_FRAMES}
    gap_frames = all_frame_ids - used_frames
    gap_suggestions = []
    for gap_id in gap_frames:
        fr = CONTENT_FRAME_BY_ID.get(gap_id, {})
        gap_suggestions.append(f"{fr.get('name', gap_id)}: {fr.get('description', '')[:100]}")

    sorted_posts = sorted(posts_data, key=lambda p: p.get("likes", 0) + p.get("comments", 0) + p.get("shares", 0), reverse=True)

    content_mix = ENGAGEMENT_BEST_PRACTICES["content_mix"]
    recommended_frames = sorted(content_mix.items(), key=lambda x: x[1], reverse=True)
    best_days = ENGAGEMENT_BEST_PRACTICES["posting_times"]["best_days"]
    best_hours = ENGAGEMENT_BEST_PRACTICES["posting_times"]["best_hours"]

    next_week_plan = []
    for i, (frame_id, weight) in enumerate(recommended_frames[:len(best_days)]):
        fr = CONTENT_FRAME_BY_ID.get(frame_id, {})
        day = best_days[i % len(best_days)]
        hour = best_hours[i % len(best_hours)]
        next_week_plan.append({
            "day": day,
            "time": hour,
            "frame": fr.get("name", frame_id),
            "priority": "High" if weight >= 0.20 else "Medium",
        })

    # Build UI
    followers_val = page_metrics.get('followers', 'N/A')
    followers_str = f"{followers_val:,}" if isinstance(followers_val, int) else str(followers_val)
    fc = page_metrics.get('follower_change', 0)

    metrics_grid = Grid(columns=4, children=[
        MetricCard(title="Posts Published", value=str(len(posts_data))),
        MetricCard(title="Total Engagement", value=str(total_engagement)),
        MetricCard(title="Follower Change", value=f"+{fc}" if fc >= 0 else str(fc)),
        MetricCard(title="Current Followers", value=followers_str),
    ])

    perf_table = Table(
        headers=["Date", "Preview", "Likes", "Comments", "Shares"],
        rows=[[p.get("date", ""), p.get("text", "")[:60], str(p.get("likes", 0)), str(p.get("comments", 0)), str(p.get("shares", 0))] for p in sorted_posts],
    )

    what_worked = []
    for i, p in enumerate(sorted_posts[:3]):
        engagement = p.get("likes", 0) + p.get("comments", 0) + p.get("shares", 0)
        what_worked.append(Collapsible(
            title=f"#{i+1}: {engagement} engagements — {p.get('text', '')[:50]}...",
            content=[
                Text(content=p.get("text", ""), variant="body"),
                Text(content=f"Frame: {classify_post_to_frame(p.get('text', ''))['frame_name']}", variant="caption"),
            ],
        ))
    if not what_worked:
        what_worked = [Text(content="No posts to analyze this week.", variant="body")]

    gaps_content = [List_(items=gap_suggestions, variant="default")] if gap_suggestions else [Text(content="All content frames covered this week!", variant="body")]

    plan_table = Table(
        headers=["Day", "Time", "Content Frame", "Priority"],
        rows=[[r["day"], r["time"], r["frame"], r["priority"]] for r in next_week_plan],
    )

    tabs = Tabs(tabs=[
        TabItem(label="Performance", content=[perf_table]),
        TabItem(label="What Worked", content=what_worked),
        TabItem(label="Content Gaps", content=gaps_content),
        TabItem(label="Next Week Plan", content=[plan_table]),
    ])

    components = [
        Card(title="Weekly LinkedIn Digest", content=[
            Text(content=week_label, variant="h2"),
            metrics_grid,
            tabs,
        ]),
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "week": week_label,
            "posts_count": len(posts_data),
            "total_engagement": total_engagement,
            "follower_change": page_metrics.get("follower_change", 0),
            "content_gaps": list(gap_frames),
            "top_posts": [{"text": p.get("text", "")[:100], "engagement": p.get("likes", 0) + p.get("comments", 0) + p.get("shares", 0)} for p in sorted_posts[:3]],
            "next_week_plan": next_week_plan,
        },
    }


# ── Tool 6: Suggest Engagement Actions ────────────────────────────────

def suggest_engagement_actions(
    focus: str = "all",
    current_followers: int = 0,
    current_engagement_rate: float = 0.0,
    session_id: str = "default",
    user_id: str = "legacy",
    **kwargs,
) -> Dict[str, Any]:
    """Generate actionable suggestions to drive engagement and grow followers
    on the CAAI LinkedIn page, based on current performance gaps.

    Args:
        focus: Focus area — "all", "followers", "engagement", or "content"
        current_followers: Current follower count (used when API unavailable)
        current_engagement_rate: Current engagement rate (used when API unavailable)
    """
    client = _get_client(**kwargs)

    followers = current_followers
    eng_rate = current_engagement_rate

    if client.api_available:
        fc = client.get_follower_count()
        if fc is not None:
            followers = fc
        page_stats = client.get_page_stats()
        if page_stats:
            total = page_stats.get("totalShareStatistics", {})
            eng_rate = total.get("engagement", eng_rate)

    eng_rating = get_benchmark_rating("engagement_rate", eng_rate)

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

    metrics_grid = Grid(columns=3, children=[
        MetricCard(title="Current Followers", value=f"{followers:,}" if followers > 0 else "Not set"),
        MetricCard(title="Engagement Rate", value=f"{eng_rate:.1%}" if eng_rate > 0 else "Not set"),
        MetricCard(title="Engagement Rating", value=eng_rating.upper() if eng_rate > 0 else "N/A"),
    ])

    tabs = Tabs(tabs=[
        TabItem(label="Quick Wins", content=[
            Text(content="Actions you can take in under an hour:", variant="caption"),
            List_(items=quick_wins, variant="default"),
        ]),
        TabItem(label="This Week", content=[
            Text(content="Tactical moves for this week:", variant="caption"),
            List_(items=weekly_actions, variant="default"),
        ]),
        TabItem(label="Strategic", content=[
            Text(content="Longer-term initiatives for sustained growth:", variant="caption"),
            List_(items=strategic_actions, variant="default"),
        ]),
        TabItem(label="Content Calendar", content=[
            Text(content="Suggested weekly posting schedule:", variant="caption"),
            Table(
                headers=["Day", "Time (ET)", "Content Frame", "Mix Weight", "Priority"],
                rows=calendar,
            ),
        ]),
    ])

    components = [
        Card(title="Engagement Growth Recommendations", content=[
            Text(content=f"Focus: {focus.title()}", variant="caption"),
            metrics_grid,
            tabs,
        ]),
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "focus": focus,
            "current_followers": followers,
            "current_engagement_rate": eng_rate,
            "engagement_rating": eng_rating,
            "quick_wins": quick_wins,
            "weekly_actions": weekly_actions,
            "strategic_actions": strategic_actions,
            "calendar": [{"day": c[0], "time": c[1], "frame": c[2], "priority": c[4]} for c in calendar],
        },
    }


# ── Tool Registry ─────────────────────────────────────────────────────

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "analyze_linkedin_posts": {
        "function": analyze_linkedin_posts,
        "description": (
            "Analyze recent posts from the CAAI LinkedIn page. Categorizes each "
            "post by content frame (Thought Leadership, Empowering the Next Generation, etc.), "
            "computes engagement metrics, and identifies top-performing content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent posts to analyze",
                    "default": 20,
                },
                "manual_posts": {
                    "type": "string",
                    "description": "JSON array of post data for manual input when API unavailable",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    "get_page_metrics": {
        "function": get_page_metrics,
        "description": (
            "Report metrics on the CAAI LinkedIn page — followers, engagement rates, "
            "impressions, and audience breakdown. Compares performance against "
            "industry benchmarks for university AI centers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period: '7d', '30d', '90d', or 'all'",
                    "default": "30d",
                    "enum": ["7d", "30d", "90d", "all"],
                },
                "manual_metrics": {
                    "type": "string",
                    "description": "JSON object with metrics for manual input when API unavailable",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    "get_content_suggestions": {
        "function": get_content_suggestions,
        "description": (
            "Generate templated content suggestions within Melissa's designed content "
            "frames for the CAAI LinkedIn page. Frames include: Thought Leadership, "
            "Empowering the Next Generation, Project Showcase, Partnership & Collaboration, "
            "Behind the Scenes, and Community Impact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "frame": {
                    "type": "string",
                    "description": "Content frame id or 'all'. Options: thought_leadership, next_generation, project_showcase, partnership_collaboration, behind_the_scenes, community_impact",
                    "default": "all",
                },
                "topic": {
                    "type": "string",
                    "description": "Specific topic to generate suggestions about",
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
    "draft_linkedin_post": {
        "function": draft_linkedin_post,
        "description": (
            "Draft a complete, ready-to-publish LinkedIn post for the CAAI page "
            "using the specified content frame template and CAAI brand voice. "
            "Generates Standard, Concise, and Bold variations with a post checklist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "frame": {
                    "type": "string",
                    "description": "Content frame id: thought_leadership, next_generation, project_showcase, partnership_collaboration, behind_the_scenes, community_impact",
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
    "generate_weekly_digest": {
        "function": generate_weekly_digest,
        "description": (
            "Generate a weekly LinkedIn engagement digest for the CAAI page. "
            "Combines post performance analysis, content gap identification, "
            "and next-week recommendations with suggested posting schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "week_offset": {
                    "type": "integer",
                    "description": "Week offset: 0 = current week, 1 = last week, etc.",
                    "default": 0,
                },
                "manual_posts": {
                    "type": "string",
                    "description": "JSON array of post data for the week (manual input fallback)",
                    "default": "",
                },
                "manual_metrics": {
                    "type": "string",
                    "description": "JSON object with page-level metrics (manual input fallback)",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    "suggest_engagement_actions": {
        "function": suggest_engagement_actions,
        "description": (
            "Generate actionable suggestions to drive engagement and grow followers "
            "on the CAAI LinkedIn page. Analyzes current performance against benchmarks "
            "and provides Quick Wins, Weekly Actions, Strategic initiatives, and a content calendar."
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
                    "description": "Current follower count (used when API unavailable)",
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
