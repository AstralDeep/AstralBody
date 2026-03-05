#!/usr/bin/env python3
"""
MCP Tools for the Grant Searching Agent.

Provides tools for searching federal funding opportunities (NSF, NIH, DOE, DoD)
via grants.gov and NIH Reporter APIs, matching them to UKy CAAI capabilities.
"""
import os
import sys
import json
import time
import logging
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Alert, MetricCard, Grid, Grids,
    BarChart, PieChart, LineChart, List_, Collapsible, Tabs, TabItem,
    create_ui_response,
)
from agents.grants.caai_knowledge import (
    CAAI_MISSION, EXPERTISE_AREAS, KEY_PERSONNEL, PROJECT_HISTORY,
    GRANT_PREFERENCES, AGENCY_CODES, compute_match_score,
)

logger = logging.getLogger("GrantsTools")

# ── API Endpoints ───────────────────────────────────────────────────────

GRANTS_GOV_SEARCH_URL = "https://api.grants.gov/v1/api/search2"
GRANTS_GOV_FETCH_URL = "https://api.grants.gov/v1/api/fetchOpportunity"
NIH_REPORTER_SEARCH_URL = "https://api.reporter.nih.gov/v2/projects/search"

# ── Simple In-Memory Cache ──────────────────────────────────────────────

_SEARCH_CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes


def _cache_key(*args: Any) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[Any]:
    if key in _SEARCH_CACHE:
        ts, data = _SEARCH_CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _SEARCH_CACHE[key]
    return None


def _set_cached(key: str, data: Any) -> None:
    _SEARCH_CACHE[key] = (time.time(), data)


# ── Helper Functions ────────────────────────────────────────────────────


GRANTS_GOV_DETAIL_URL = "https://www.grants.gov/search-results-detail"


def _grant_url(opp_id: Any) -> str:
    """Build a clickable grants.gov URL for an opportunity."""
    return f"{GRANTS_GOV_DETAIL_URL}/{opp_id}"


def _format_date(date_str: Optional[str]) -> str:
    """Format a date string from grants.gov to readable form.

    Handles both search format (MM/DD/YYYY) and detail format
    (e.g. "Aug 05, 2026 12:00:00 AM EDT").
    """
    if not date_str:
        return "N/A"
    # Try search result format first
    for fmt in ("%m/%d/%Y", "%b %d, %Y %I:%M:%S %p %Z", "%b %d, %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%b %d, %Y")
        except (ValueError, TypeError):
            continue
    # Fallback: if it already looks like "Aug 05, 2026 ..." just take the date part
    if len(str(date_str)) > 12:
        return str(date_str).split(" 12:")[0].split(" 00:")[0]
    return str(date_str)


def _days_until(date_str: Optional[str]) -> Optional[int]:
    """Calculate days until a deadline date string."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%b %d, %Y %I:%M:%S %p %Z", "%b %d, %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            delta = dt - datetime.now()
            return delta.days
        except (ValueError, TypeError):
            continue
    return None


def _format_currency(amount: Any) -> str:
    """Format a number as USD currency string."""
    if amount is None or str(amount).lower() in ("none", "", "n/a"):
        return "N/A"
    try:
        num = float(amount)
        if num >= 1_000_000:
            return f"USD {num / 1_000_000:,.1f}M"
        elif num >= 1_000:
            return f"USD {num / 1_000:,.0f}K"
        else:
            return f"USD {num:,.0f}"
    except (ValueError, TypeError):
        return str(amount)


def _search_grants_raw(
    keyword: str,
    agency: str = "ALL",
    status: str = "posted|forecasted",
    max_results: int = 25,
) -> List[Dict[str, Any]]:
    """
    Raw search against grants.gov search2 API.
    Returns list of opportunity dicts.
    """
    ck = _cache_key("search", keyword, agency, status, max_results)
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    body: Dict[str, Any] = {
        "keyword": keyword,
        "oppStatuses": status,
        "rows": min(int(max_results), 100),
        "sortBy": "openDate|desc",
    }

    if agency.upper() != "ALL":
        code = AGENCY_CODES.get(agency.upper(), agency.upper())
        body["agencies"] = code

    try:
        resp = requests.post(
            GRANTS_GOV_SEARCH_URL,
            json=body,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        logger.error(f"grants.gov search failed: {exc}")
        raise

    hits = data.get("data", {}).get("oppHits", [])
    _set_cached(ck, hits)
    return hits


def _fetch_nih_projects(
    keyword: str,
    fiscal_years: List[int],
    max_results: int = 50,
) -> List[Dict[str, Any]]:
    """Query NIH Reporter for funded project data."""
    body = {
        "criteria": {
            "advanced_text_search": {
                "operator": "and",
                "search_field": "projecttitle,terms",
                "search_text": keyword,
            },
            "fiscal_years": fiscal_years,
        },
        "offset": 0,
        "limit": min(max_results, 500),
        "sort_field": "award_amount",
        "sort_order": "desc",
    }

    try:
        resp = requests.post(
            NIH_REPORTER_SEARCH_URL,
            json=body,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except requests.exceptions.RequestException as exc:
        logger.error(f"NIH Reporter search failed: {exc}")
        return []


# ═══════════════════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════


def search_grants(
    keyword: str,
    agency: str = "ALL",
    status: str = "posted|forecasted",
    max_results: int = 25,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Search federal funding opportunities across NSF, NIH, DOE, DoD
    and other agencies via the grants.gov API.
    """
    try:
        hits = _search_grants_raw(keyword, agency, status, max_results)
    except requests.exceptions.Timeout:
        return create_ui_response([
            Alert(
                message="Grant search timed out. The grants.gov API may be slow — please try again.",
                variant="warning",
                title="Search Timeout",
            )
        ])
    except requests.exceptions.RequestException as exc:
        return create_ui_response([
            Alert(
                message=f"Failed to search grants.gov: {exc}",
                variant="error",
                title="API Error",
            )
        ])

    if not hits:
        return create_ui_response([
            Alert(
                message=f"No funding opportunities found for '{keyword}'.",
                variant="info",
                title="No Results",
            )
        ])

    # Aggregate stats
    agencies_seen = Counter(h.get("agencyCode", "Unknown") for h in hits)
    status_counts = Counter(h.get("oppStatus", "Unknown") for h in hits)
    open_count = status_counts.get("posted", 0)
    forecast_count = status_counts.get("forecasted", 0)

    # Build table rows with clickable grant links
    rows = []
    for h in hits:
        title = h.get("title", "Untitled")
        if len(title) > 80:
            title = title[:77] + "..."
        opp_id = h.get("id", "")
        link = _grant_url(opp_id) if opp_id else ""
        rows.append([
            h.get("number", "N/A"),
            title,
            h.get("agencyCode", "N/A"),
            _format_date(h.get("openDate")),
            _format_date(h.get("closeDate")),
            h.get("oppStatus", "N/A"),
            link,
        ])

    components = [
        Card(
            title=f"Grant Search Results — '{keyword}'",
            id="search-results",
            content=[
                Grid(
                    columns=4,
                    children=[
                        MetricCard(title="Total Found", value=str(len(hits)), id="total-metric"),
                        MetricCard(title="Open Now", value=str(open_count), id="open-metric"),
                        MetricCard(title="Forecasted", value=str(forecast_count), id="forecast-metric"),
                        MetricCard(title="Agencies", value=str(len(agencies_seen)), id="agency-metric"),
                    ],
                ),
                Text(
                    content=f"Showing {len(hits)} results" + (f" for agency: {agency}" if agency.upper() != "ALL" else ""),
                    variant="caption",
                ),
                Table(
                    headers=["Opp #", "Title", "Agency", "Open Date", "Close Date", "Status", "Link"],
                    rows=rows,
                    id="grants-table",
                ),
            ],
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total": len(hits),
            "open": open_count,
            "forecasted": forecast_count,
            "agencies": dict(agencies_seen),
            "hits": [
                {**h, "url": _grant_url(h.get("id", ""))}
                for h in hits
            ],
        },
    }


def _strip_html(text: str) -> str:
    """Strip HTML tags from a string for plain-text display."""
    import re
    text = re.sub(r"&mdash;", "—", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li[^>]*>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_grant_details(
    opportunity_id: str,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific grant opportunity
    including description, eligibility, and award amounts.

    opportunity_id can be a numeric ID (e.g. '320753') or an
    opportunity number (e.g. 'PD-19-127Y').
    """
    # Determine whether we received a numeric ID or an opportunity number.
    # The fetchOpportunity API requires the numeric opportunityId.
    numeric_id = opportunity_id.strip()
    opp_number = None
    if not numeric_id.isdigit():
        # We got an opportunity number — look it up via search first
        opp_number = numeric_id
        try:
            search_resp = requests.post(
                GRANTS_GOV_SEARCH_URL,
                json={"keyword": opp_number, "rows": 5},
                timeout=20,
                headers={"Content-Type": "application/json"},
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            search_hits = search_data.get("data", {}).get("oppHits", [])
            # Find exact match on opportunity number
            found = None
            for sh in search_hits:
                if sh.get("number", "").upper() == opp_number.upper():
                    found = sh
                    break
            if not found and search_hits:
                found = search_hits[0]
            if found:
                numeric_id = str(found.get("id", ""))
            else:
                return create_ui_response([
                    Alert(
                        message=f"Opportunity '{opportunity_id}' not found in grants.gov.",
                        variant="warning",
                        title="Not Found",
                    )
                ])
        except requests.exceptions.RequestException as exc:
            return create_ui_response([
                Alert(
                    message=f"Failed to look up opportunity number: {exc}",
                    variant="error",
                    title="API Error",
                )
            ])

    # Fetch full opportunity details using numeric ID
    try:
        resp = requests.post(
            GRANTS_GOV_FETCH_URL,
            json={"opportunityId": numeric_id},
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return create_ui_response([
            Alert(
                message=f"Request for '{opportunity_id}' timed out.",
                variant="warning",
                title="Timeout",
            )
        ])
    except requests.exceptions.RequestException as exc:
        return create_ui_response([
            Alert(
                message=f"Failed to fetch opportunity details: {exc}",
                variant="error",
                title="API Error",
            )
        ])

    opp = data.get("data", {})
    if not opp or isinstance(opp.get("message"), str):
        # Backend service may be unavailable
        error_msg = opp.get("message", "No data returned") if isinstance(opp, dict) else "No data"
        return create_ui_response([
            Alert(
                message=f"grants.gov detail service unavailable: {error_msg}",
                variant="warning",
                title="Service Unavailable",
            )
        ])

    # Parse the nested response structure
    synopsis = opp.get("synopsis") or {}
    doc_type = opp.get("docType", "")
    is_forecast = doc_type == "forecast" or not synopsis.get("synopsisDesc")

    title = opp.get("opportunityTitle", "Unknown")
    number = opp.get("opportunityNumber", opportunity_id)
    agency = opp.get("owningAgencyCode", synopsis.get("agencyCode", "N/A"))
    agency_name = synopsis.get("agencyName", "")
    description_html = synopsis.get("synopsisDesc", "")
    description = _strip_html(description_html) if description_html else ""
    close_date_raw = synopsis.get("responseDate", synopsis.get("archiveDate"))
    open_date_raw = synopsis.get("postingDate")
    award_ceiling = synopsis.get("awardCeiling")
    award_floor = synopsis.get("awardFloor")
    cost_sharing = synopsis.get("costSharing", False)
    funding_url = synopsis.get("fundingDescLinkUrl", "")
    contact_name = synopsis.get("agencyContactName", "")
    contact_email = synopsis.get("agencyContactEmail", "")

    # Eligibility from applicantTypes list
    applicant_types = synopsis.get("applicantTypes", [])
    if isinstance(applicant_types, list) and applicant_types:
        eligibility = "\n".join(
            f"• {at.get('description', str(at))}" for at in applicant_types
        )
    else:
        eligibility = "Not specified"

    # CFDA numbers
    cfdas = opp.get("cfdas", [])
    if isinstance(cfdas, list) and cfdas:
        cfda_str = ", ".join(c.get("cfdaNumber", "") for c in cfdas if c.get("cfdaNumber"))
    else:
        cfda_str = "N/A"

    # Funding instruments
    instruments = synopsis.get("fundingInstruments", [])
    instrument_str = ", ".join(i.get("description", "") for i in instruments) if instruments else "N/A"

    # Grants.gov link
    detail_url = _grant_url(opp.get("id", numeric_id))

    # Truncate long descriptions for UI
    desc_display = description if description else "No description available yet."
    if len(desc_display) > 3000:
        desc_display = desc_display[:3000] + "..."

    # Build alerts
    alert_components = []
    if is_forecast:
        alert_components.append(
            Alert(
                message=(
                    "This is a forecasted opportunity. Full details (description, "
                    "award amounts, eligibility) are not yet available on grants.gov. "
                    "Check back when the opportunity is officially posted."
                ),
                variant="info",
                title="Forecasted — Limited Details",
            )
        )

    days_left = _days_until(close_date_raw)
    if days_left is not None and 0 <= days_left <= 30:
        alert_components.append(
            Alert(
                message=f"Deadline in {days_left} day{'s' if days_left != 1 else ''}!",
                variant="warning",
                title="Approaching Deadline",
            )
        )
    elif days_left is not None and days_left < 0:
        alert_components.append(
            Alert(
                message="This opportunity has closed.",
                variant="info",
                title="Closed",
            )
        )

    info_rows = [
        ["Opportunity #", number],
        ["Agency", f"{agency_name} ({agency})" if agency_name else agency],
        ["Status", opp.get("docType", "N/A")],
        ["Open Date", _format_date(open_date_raw)],
        ["Close Date", _format_date(close_date_raw)],
        ["CFDA / ALN", cfda_str],
        ["Funding Type", instrument_str],
        ["Cost Sharing", "Yes" if cost_sharing else "No"],
        ["Grants.gov Link", detail_url],
    ]
    if contact_email:
        info_rows.append(["Contact", f"{contact_name} ({contact_email})"])
    if funding_url:
        info_rows.append(["Agency Listing", funding_url])

    components = [
        Card(
            title=f"{number}: {title}",
            id="grant-detail",
            content=[
                *alert_components,
                Grid(
                    columns=4,
                    children=[
                        MetricCard(
                            title="Award Ceiling",
                            value=_format_currency(award_ceiling),
                            id="ceiling-metric",
                        ),
                        MetricCard(
                            title="Award Floor",
                            value=_format_currency(award_floor),
                            id="floor-metric",
                        ),
                        MetricCard(
                            title="Close Date",
                            value=_format_date(close_date_raw),
                            id="close-metric",
                        ),
                        MetricCard(
                            title="Agency",
                            value=str(agency),
                            id="agency-metric",
                        ),
                    ],
                ),
                Table(
                    headers=["Field", "Value"],
                    rows=info_rows,
                    id="detail-table",
                ),
                Collapsible(
                    title="Description",
                    content=[Text(content=desc_display, variant="body")],
                    default_open=True,
                ),
                Collapsible(
                    title="Eligibility",
                    content=[Text(content=eligibility, variant="body")],
                    default_open=False,
                ),
            ],
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "opportunity_id": number,
            "numeric_id": numeric_id,
            "title": title,
            "agency": agency,
            "agency_name": agency_name,
            "award_ceiling": str(award_ceiling) if award_ceiling else None,
            "award_floor": str(award_floor) if award_floor else None,
            "close_date": _format_date(close_date_raw),
            "open_date": _format_date(open_date_raw),
            "description": description,
            "eligibility": eligibility,
            "url": detail_url,
            "funding_url": funding_url,
            "contact_email": contact_email,
        },
    }


def match_grants_to_caai(
    keyword: str = "",
    agency: str = "ALL",
    min_score: int = 20,
    max_results: int = 15,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Search grants and score them against UKy CAAI capabilities.
    Returns opportunities ranked by match score.
    """
    if not keyword:
        keyword = "artificial intelligence machine learning"

    try:
        hits = _search_grants_raw(keyword, agency, "posted|forecasted", max_results)
    except requests.exceptions.RequestException as exc:
        return create_ui_response([
            Alert(
                message=f"Failed to search grants.gov: {exc}",
                variant="error",
                title="API Error",
            )
        ])

    if not hits:
        return create_ui_response([
            Alert(
                message=f"No opportunities found for '{keyword}'.",
                variant="info",
                title="No Results",
            )
        ])

    # Score each opportunity.
    # Note: grants.gov search hits only include titles, not full descriptions.
    # We pass the search keyword as grant_keywords since grants.gov already
    # matched these results against the keyword in their full text.
    search_keywords = [k.strip() for k in keyword.split() if len(k.strip()) > 2]
    scored: List[Dict[str, Any]] = []
    for h in hits:
        title = h.get("title", "")
        desc = h.get("description", h.get("synopsis", ""))
        match = compute_match_score(
            grant_title=title,
            grant_description=str(desc) if desc else "",
            grant_keywords=search_keywords,
        )
        if match["score"] >= min_score:
            scored.append({**h, "_match": match})

    scored.sort(key=lambda x: x["_match"]["score"], reverse=True)

    # Compute summary stats
    total_analyzed = len(hits)
    total_matched = len(scored)
    scores = [s["_match"]["score"] for s in scored]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    excellent = sum(1 for s in scored if s["_match"]["tier"] == "Excellent Match")
    strong = sum(1 for s in scored if s["_match"]["tier"] == "Strong Match")

    # Build table rows with grants.gov links
    rows = []
    for s in scored:
        title = s.get("title", "Untitled")
        if len(title) > 65:
            title = title[:62] + "..."
        opp_id = s.get("id", "")
        link = _grant_url(opp_id) if opp_id else ""
        rows.append([
            str(s["_match"]["score"]),
            s["_match"]["tier"],
            title,
            s.get("agencyCode", "N/A"),
            _format_date(s.get("closeDate")),
            link,
        ])

    # Build top match detail collapsibles
    top_details = []
    for idx, s in enumerate(scored[:3]):
        m = s["_match"]
        opp_id = s.get("id", "")
        detail_items = []
        if m["matching_expertise_areas"]:
            detail_items.append(f"Expertise: {', '.join(m['matching_expertise_areas'])}")
        if m["matching_projects"]:
            detail_items.append(f"Related Projects: {', '.join(m['matching_projects'])}")
        if m["strong_keyword_matches"]:
            detail_items.append(f"Keywords: {', '.join(m['strong_keyword_matches'][:8])}")
        detail_items.append(f"View: {_grant_url(opp_id)}")

        top_details.append(
            Collapsible(
                title=f"#{idx + 1}: {s.get('title', 'Untitled')[:60]} (Score: {m['score']})",
                content=[
                    List_(items=detail_items, id=f"match-detail-{idx}"),
                    Text(
                        content=f"Opportunity: {s.get('number', 'N/A')} | Agency: {s.get('agencyCode', 'N/A')}",
                        variant="caption",
                    ),
                ],
                default_open=idx == 0,
            )
        )

    # Score distribution for chart
    buckets = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
    for sc in scores:
        if sc < 25:
            buckets["0-25"] += 1
        elif sc < 50:
            buckets["25-50"] += 1
        elif sc < 75:
            buckets["50-75"] += 1
        else:
            buckets["75-100"] += 1

    components = [
        Card(
            title="CAAI Grant Match Analysis",
            id="match-analysis",
            content=[
                Grid(
                    columns=4,
                    children=[
                        MetricCard(title="Analyzed", value=str(total_analyzed), id="analyzed-metric"),
                        MetricCard(title="Matched", value=str(total_matched), id="matched-metric"),
                        MetricCard(title="Excellent", value=str(excellent), id="excellent-metric"),
                        MetricCard(title="Avg Score", value=str(avg_score), id="avg-metric"),
                    ],
                ),
                Table(
                    headers=["Score", "Tier", "Title", "Agency", "Close Date", "Link"],
                    rows=rows,
                    id="match-table",
                ),
                BarChart(
                    title="Match Score Distribution",
                    labels=list(buckets.keys()),
                    datasets=[{
                        "label": "Opportunities",
                        "data": list(buckets.values()),
                        "color": "#4f46e5",
                    }],
                    id="score-chart",
                ),
                *top_details,
            ],
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total_analyzed": total_analyzed,
            "total_matched": total_matched,
            "average_score": avg_score,
            "excellent_matches": excellent,
            "strong_matches": strong,
            "scored_results": [
                {
                    "number": s.get("number"),
                    "title": s.get("title"),
                    "agency": s.get("agencyCode"),
                    "close_date": s.get("closeDate"),
                    "match_score": s["_match"]["score"],
                    "match_tier": s["_match"]["tier"],
                    "matching_areas": s["_match"]["matching_expertise_areas"],
                    "matching_projects": s["_match"]["matching_projects"],
                    "url": _grant_url(s.get("id", "")),
                }
                for s in scored
            ],
        },
    }


def get_caai_profile(
    section: str = "all",
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Get the UKy Center for Applied AI profile including mission,
    expertise areas, key personnel, and project history.
    """
    section = section.lower().strip()

    # ── Mission tab ────────────────────────────────────────────────
    mission_content = [
        Text(content=CAAI_MISSION["mission"], variant="body"),
        Grid(
            columns=3,
            children=[
                MetricCard(
                    title="Award Participation",
                    value=CAAI_MISSION["stats"]["total_award_participation"],
                    id="awards-metric",
                ),
                MetricCard(
                    title="Funded Projects",
                    value=str(CAAI_MISSION["stats"]["funded_projects"]),
                    id="funded-metric",
                ),
                MetricCard(
                    title="Collaborators",
                    value=f"{CAAI_MISSION['stats']['collaborators']}+",
                    id="collab-metric",
                ),
            ],
        ),
        Table(
            headers=["Field", "Value"],
            rows=[
                ["Director", CAAI_MISSION["director"]],
                ["Parent Org", CAAI_MISSION["parent_org"]],
                ["University", CAAI_MISSION["university"]],
                ["Founded", str(CAAI_MISSION["founded"])],
                ["Funding Rate", CAAI_MISSION["stats"]["funding_rate"]],
                ["Partners", str(CAAI_MISSION["stats"]["partners"])],
            ],
            id="mission-table",
        ),
    ]

    # ── Expertise tab ──────────────────────────────────────────────
    expertise_rows = []
    for area in EXPERTISE_AREAS:
        tools = ", ".join(area["tools_built"]) if area["tools_built"] else "—"
        expertise_rows.append([
            area["area"],
            area["description"],
            tools,
        ])

    expertise_content = [
        Table(
            headers=["Area", "Description", "Tools Built"],
            rows=expertise_rows,
            id="expertise-table",
        ),
    ]

    # ── Personnel tab ──────────────────────────────────────────────
    personnel_rows = []
    for p in KEY_PERSONNEL:
        expertise = ", ".join(p["expertise"])
        notable = p.get("notable", "")
        personnel_rows.append([
            p["name"],
            p["title"],
            expertise,
            notable,
        ])

    personnel_content = [
        Table(
            headers=["Name", "Title", "Expertise", "Notable"],
            rows=personnel_rows,
            id="personnel-table",
        ),
    ]

    # ── Projects tab ───────────────────────────────────────────────
    project_rows = []
    for proj in PROJECT_HISTORY:
        project_rows.append([
            proj["title"],
            proj["domain"],
            proj["agency"],
            proj["description"],
        ])

    projects_content = [
        Table(
            headers=["Project", "Domain", "Agency", "Description"],
            rows=project_rows,
            id="projects-table",
        ),
    ]

    # Build response based on requested section
    if section == "all":
        components = [
            Card(
                title=f"{CAAI_MISSION['full_name']}",
                id="caai-profile",
                content=[
                    Tabs(
                        tabs=[
                            TabItem(label="Mission", content=mission_content),
                            TabItem(label="Expertise", content=expertise_content),
                            TabItem(label="Personnel", content=personnel_content),
                            TabItem(label="Projects", content=projects_content),
                        ],
                        id="profile-tabs",
                    ),
                ],
            )
        ]
    elif section == "mission":
        components = [Card(title="CAAI Mission", id="caai-mission", content=mission_content)]
    elif section == "expertise":
        components = [Card(title="CAAI Expertise Areas", id="caai-expertise", content=expertise_content)]
    elif section == "personnel":
        components = [Card(title="CAAI Key Personnel", id="caai-personnel", content=personnel_content)]
    elif section == "projects":
        components = [Card(title="CAAI Project History", id="caai-projects", content=projects_content)]
    else:
        return create_ui_response([
            Alert(
                message=f"Unknown section '{section}'. Use: all, mission, expertise, personnel, projects.",
                variant="warning",
                title="Invalid Section",
            )
        ])

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "name": CAAI_MISSION["name"],
            "mission": CAAI_MISSION["mission"],
            "expertise_areas": [a["area"] for a in EXPERTISE_AREAS],
            "project_count": len(PROJECT_HISTORY),
            "personnel_count": len(KEY_PERSONNEL),
        },
    }


def analyze_funding_trends(
    keyword: str = "artificial intelligence",
    include_nih_history: bool = False,
    fiscal_years: str = "",
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """
    Analyze federal funding trends for AI and CAAI-relevant topics
    across agencies.  Shows distribution by agency, status, and
    optionally includes NIH Reporter historical data.
    """
    try:
        hits = _search_grants_raw(keyword, "ALL", "posted|forecasted|closed", 100)
    except requests.exceptions.RequestException as exc:
        return create_ui_response([
            Alert(
                message=f"Failed to search grants.gov: {exc}",
                variant="error",
                title="API Error",
            )
        ])

    if not hits:
        return create_ui_response([
            Alert(
                message=f"No opportunities found for '{keyword}'.",
                variant="info",
                title="No Results",
            )
        ])

    # Aggregate stats
    agency_counts = Counter(h.get("agencyCode", "Other") for h in hits)
    status_counts = Counter(h.get("oppStatus", "Unknown") for h in hits)
    open_count = status_counts.get("posted", 0)
    forecast_count = status_counts.get("forecasted", 0)

    # Top agencies for charts
    top_agencies = agency_counts.most_common(8)
    agency_labels = [a[0] for a in top_agencies]
    agency_data = [float(a[1]) for a in top_agencies]

    # Colors for pie chart
    pie_colors = [
        "#4f46e5", "#059669", "#d97706", "#dc2626",
        "#7c3aed", "#0891b2", "#be185d", "#65a30d",
    ]

    tab_items = [
        TabItem(
            label="By Agency",
            content=[
                PieChart(
                    title=f"Opportunities by Agency — '{keyword}'",
                    labels=agency_labels,
                    data=agency_data,
                    colors=pie_colors[: len(agency_labels)],
                    id="agency-pie",
                ),
            ],
        ),
        TabItem(
            label="By Status",
            content=[
                BarChart(
                    title="Opportunities by Status",
                    labels=list(status_counts.keys()),
                    datasets=[{
                        "label": "Count",
                        "data": [float(v) for v in status_counts.values()],
                        "color": "#4f46e5",
                    }],
                    id="status-bar",
                ),
            ],
        ),
    ]

    # Optional NIH Reporter historical data
    nih_data_section: Dict[str, Any] = {}
    if include_nih_history:
        current_year = datetime.now().year
        if fiscal_years:
            years = [int(y.strip()) for y in fiscal_years.split(",") if y.strip().isdigit()]
        else:
            years = list(range(current_year - 2, current_year + 1))

        nih_projects = _fetch_nih_projects(keyword, years, max_results=100)

        if nih_projects:
            # Aggregate award amounts by fiscal year
            year_totals: Dict[int, float] = {}
            year_counts: Dict[int, int] = {}
            for proj in nih_projects:
                fy = proj.get("fiscal_year", proj.get("fy"))
                amount = proj.get("award_amount", 0) or 0
                if fy:
                    year_totals[fy] = year_totals.get(fy, 0) + amount
                    year_counts[fy] = year_counts.get(fy, 0) + 1

            sorted_years = sorted(year_totals.keys())
            year_labels = [str(y) for y in sorted_years]
            amount_data = [year_totals[y] / 1_000_000 for y in sorted_years]  # In millions
            count_data = [float(year_counts[y]) for y in sorted_years]

            tab_items.append(
                TabItem(
                    label="NIH History",
                    content=[
                        LineChart(
                            title="NIH Funding Over Time (USD millions)",
                            labels=year_labels,
                            datasets=[{
                                "label": "Total Funding (USD millions)",
                                "data": amount_data,
                                "color": "#059669",
                            }],
                            id="nih-funding-line",
                        ),
                        BarChart(
                            title="NIH Projects by Year",
                            labels=year_labels,
                            datasets=[{
                                "label": "Projects",
                                "data": count_data,
                                "color": "#4f46e5",
                            }],
                            id="nih-count-bar",
                        ),
                    ],
                )
            )

            nih_data_section = {
                "nih_years": year_labels,
                "nih_totals_millions": amount_data,
                "nih_project_counts": {str(y): year_counts[y] for y in sorted_years},
            }
        else:
            tab_items.append(
                TabItem(
                    label="NIH History",
                    content=[
                        Alert(
                            message="No NIH Reporter data found for this keyword.",
                            variant="info",
                        ),
                    ],
                )
            )

    most_active = top_agencies[0][0] if top_agencies else "N/A"

    components = [
        Card(
            title=f"Funding Trend Analysis — '{keyword}'",
            id="trend-analysis",
            content=[
                Grid(
                    columns=4,
                    children=[
                        MetricCard(title="Total Opportunities", value=str(len(hits)), id="total-trend"),
                        MetricCard(title="Most Active", value=most_active, id="active-trend"),
                        MetricCard(title="Open Now", value=str(open_count), id="open-trend"),
                        MetricCard(title="Forecasted", value=str(forecast_count), id="forecast-trend"),
                    ],
                ),
                Tabs(tabs=tab_items, id="trend-tabs"),
            ],
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total_opportunities": len(hits),
            "agency_distribution": dict(agency_counts),
            "status_distribution": dict(status_counts),
            "most_active_agency": most_active,
            **nih_data_section,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY
# ═══════════════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "search_grants": {
        "function": search_grants,
        "scope": "tools:search",
        "description": (
            "Search federal funding opportunities across NSF, NIH, DOE, DoD "
            "and other agencies via grants.gov. Filters by keyword, agency, "
            "and status. Returns opportunities with title, agency, dates, "
            "and status. Use this for broad searches across agencies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": (
                        "Search keyword(s) for grant opportunities "
                        "(e.g., 'artificial intelligence', 'machine learning healthcare')"
                    ),
                },
                "agency": {
                    "type": "string",
                    "description": (
                        "Agency filter: 'NSF', 'NIH', 'DOE', 'DoD', 'DARPA', "
                        "'ARPA-H', 'ALL'. Default: 'ALL'"
                    ),
                    "default": "ALL",
                },
                "status": {
                    "type": "string",
                    "description": (
                        "Opportunity status filter: 'posted', 'forecasted', "
                        "'closed', 'posted|forecasted'. Default: 'posted|forecasted'"
                    ),
                    "default": "posted|forecasted",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-100). Default: 25",
                    "default": 25,
                },
            },
            "required": ["keyword"],
        },
    },
    "get_grant_details": {
        "function": get_grant_details,
        "scope": "tools:search",
        "description": (
            "Get detailed information about a specific grant opportunity "
            "including full description, eligibility, award ceiling/floor, "
            "and application deadlines. Accepts either a numeric grants.gov "
            "ID or an opportunity number. Use after search_grants to drill "
            "into a specific opportunity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "opportunity_id": {
                    "type": "string",
                    "description": (
                        "The grants.gov numeric ID (e.g., '320753') or "
                        "opportunity number (e.g., 'PD-19-127Y')"
                    ),
                },
            },
            "required": ["opportunity_id"],
        },
    },
    "match_grants_to_caai": {
        "function": match_grants_to_caai,
        "scope": "tools:search",
        "description": (
            "Search funding opportunities and score them against UKy Center "
            "for Applied AI (CAAI) capabilities. Ranks opportunities by "
            "alignment with CAAI's expertise in LLMs, ML, biomedical "
            "informatics, computer vision, HPC, and agricultural AI. "
            "Shows matching expertise areas and related past projects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": (
                        "Search keyword to find and match grants. "
                        "Defaults to 'artificial intelligence machine learning' if empty."
                    ),
                    "default": "",
                },
                "agency": {
                    "type": "string",
                    "description": "Agency filter: 'NSF', 'NIH', 'DOE', 'DoD', 'ALL'. Default: 'ALL'",
                    "default": "ALL",
                },
                "min_score": {
                    "type": "integer",
                    "description": "Minimum match score (0-100) to include. Default: 20",
                    "default": 20,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to analyze. Default: 15",
                    "default": 15,
                },
            },
        },
    },
    "get_caai_profile": {
        "function": get_caai_profile,
        "scope": "tools:read",
        "description": (
            "Get UKy Center for Applied AI (CAAI) profile including mission, "
            "expertise areas, key personnel, project history, and capabilities. "
            "Use to understand CAAI before searching for matching grants."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": (
                        "Section to show: 'all', 'mission', 'expertise', "
                        "'personnel', 'projects'. Default: 'all'"
                    ),
                    "default": "all",
                },
            },
        },
    },
    "analyze_funding_trends": {
        "function": analyze_funding_trends,
        "scope": "tools:search",
        "description": (
            "Analyze federal funding trends for AI and CAAI-relevant topics "
            "across agencies. Shows distribution of opportunities by agency "
            "and status. Optionally includes NIH Reporter historical funding data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Topic to analyze. Default: 'artificial intelligence'",
                    "default": "artificial intelligence",
                },
                "include_nih_history": {
                    "type": "boolean",
                    "description": "Include NIH Reporter historical data. Default: false",
                    "default": False,
                },
                "fiscal_years": {
                    "type": "string",
                    "description": (
                        "Comma-separated fiscal years for NIH history "
                        "(e.g., '2022,2023,2024,2025'). Default: last 3 years"
                    ),
                    "default": "",
                },
            },
        },
    },
}
