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
    BarChart, PieChart, LineChart, List_, Tabs, TabItem,
    create_ui_response,
)
from agents.grants.caai_knowledge import (
    CAAI_MISSION, EXPERTISE_AREAS, KEY_PERSONNEL, PROJECT_HISTORY,
    GRANT_PREFERENCES, AGENCY_CODES, compute_match_score,
)
from agents.grants.nsf_techaccess_knowledge import (
    SOLICITATION_META,
    OPPORTUNITY_FAMILY,
    SECTION_HEADINGS,
    SECTION_REQUIREMENTS,
    HUB_RESPONSIBILITIES,
    NSF_REQUIRED_METRICS,
    EXTENDED_METRIC_LAYERS,
    KY_PARTNERS,
    KY_PRIORITY_SECTORS,
    KY_EQUITY_LENSES,
    AI_LITERACY_LEVELS,
    LOI_RULES,
    SUPPLEMENTAL_RULES,
    FRAMING_RULES,
    ADMINISTRATION_PRIORITIES,
    ADMINISTRATION_PRIORITY_PHRASES,
    PROGRAM_OFFICER_QUESTION_TOPICS,
    SOLICITATION_VERBATIM_PHRASES,
    PAGE_BUDGET,
    DEADLINES,
    get_section,
    get_partner,
    get_hub_responsibilities_for_section,
    get_framing_rules_for_section,
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
                Text(content=desc_display, variant="body"),
                Text(content=eligibility, variant="body"),
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
            Card(
                title=f"#{idx + 1}: {s.get('title', 'Untitled')[:60]} (Score: {m['score']})",
                content=[
                    List_(items=detail_items, id=f"match-detail-{idx}"),
                    Text(
                        content=f"Opportunity: {s.get('number', 'N/A')} | Agency: {s.get('agencyCode', 'N/A')}",
                        variant="caption",
                    ),
                ],
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
#  NSF TECHACCESS (NSF 26-508) TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════
#
#  These tools support drafting and gap-checking the Kentucky
#  Coordination Hub LOI and full proposal. They are deterministic
#  scaffolders — they return structured guidance (heading, required
#  sub-elements, framing rules, KY anchors) that the orchestrator LLM
#  composes against. They do not make their own LLM calls.

_TECHACCESS_FAMILY_KEYWORDS = {
    "hub": [
        "kentucky coordination hub",
        "coordination hub",
        "ky hub",
        "state coordination hub",
        "state/territory coordination hub",
    ],
    "national_lead": [
        "national coordination lead",
        "national lead",
        "other transaction agreement",
        "ota for national",
    ],
    "catalyst": [
        "ai-ready catalyst",
        "catalyst award",
        "catalyst competition",
        "ai ready catalyst",
    ],
}

_TECHACCESS_KEYWORDS = [
    "techaccess",
    "tech access",
    "ai-ready america",
    "ai ready america",
    "nsf 26-508",
    "26-508",
    "26508",
]


def _classify_techaccess_request(user_request: str) -> Dict[str, Any]:
    """Classify a user request against the TechAccess family.

    Returns a dict with ``classification`` ∈
    ``{"primary_hub", "sibling_national_lead", "sibling_catalyst",
    "out_of_family"}`` and a ``reason`` field describing the keyword
    evidence.
    """
    text = (user_request or "").lower().strip()
    if not text:
        return {
            "classification": "out_of_family",
            "reason": "empty user_request",
        }

    family_signal = any(k in text for k in _TECHACCESS_KEYWORDS)
    hub_signal = any(k in text for k in _TECHACCESS_FAMILY_KEYWORDS["hub"])
    nat_signal = any(
        k in text for k in _TECHACCESS_FAMILY_KEYWORDS["national_lead"]
    )
    cat_signal = any(
        k in text for k in _TECHACCESS_FAMILY_KEYWORDS["catalyst"]
    )

    if nat_signal:
        return {
            "classification": "sibling_national_lead",
            "reason": "matched National Coordination Lead keywords",
        }
    if cat_signal:
        return {
            "classification": "sibling_catalyst",
            "reason": "matched AI-Ready Catalyst Award keywords",
        }
    if hub_signal or family_signal:
        return {
            "classification": "primary_hub",
            "reason": "matched Coordination Hub / TechAccess family keywords",
        }
    return {
        "classification": "out_of_family",
        "reason": "no TechAccess family keywords detected",
    }


def techaccess_scope_check(
    user_request: str,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Classify a user request as in-scope (Hub / National Lead /
    Catalyst) or out-of-family.

    Implements FR-001 + the TechAccess scope edge cases. Used both as a
    standalone tool and as a precondition gate inside the other
    TechAccess tools.

    Args:
        user_request: Free-text user message to classify.
        session_id: Session identifier (unused; reserved).

    Returns:
        ``create_ui_response`` payload describing the scope decision.
    """
    if not user_request or not str(user_request).strip():
        logger.warning("techaccess_scope_check called with empty user_request")
        return create_ui_response([
            Alert(
                message="No request supplied to scope-check.",
                variant="error",
                title="Empty Input",
            )
        ])

    decision = _classify_techaccess_request(user_request)
    classification = decision["classification"]
    logger.info(
        "techaccess_scope_check: classification=%s reason=%s",
        classification, decision["reason"],
    )

    if classification == "primary_hub":
        verdict = "In scope: NSF 26-508 Coordination Hub (Kentucky)."
        return create_ui_response([
            Card(
                title="Scope Decision",
                content=[Text(content=verdict, variant="body")],
            ),
        ])

    if classification == "sibling_national_lead":
        verdict = (
            "In scope but different mechanism: National Coordination Lead "
            "(Other Transaction Agreement)."
        )
        return create_ui_response([
            Card(
                title="Scope Decision",
                content=[Text(content=verdict, variant="body")],
            ),
            Alert(
                title="Different mechanism",
                message=(
                    "The National Coordination Lead is selected separately "
                    "via Other Transaction Agreement. Different rules, "
                    "different deadlines. Confirm which opportunity you are "
                    "drafting for so framing is not reused from the Hub "
                    "proposal."
                ),
                variant="info",
            ),
        ])

    if classification == "sibling_catalyst":
        verdict = (
            "In scope but different mechanism: AI-Ready Catalyst Award "
            "Competition."
        )
        return create_ui_response([
            Card(
                title="Scope Decision",
                content=[Text(content=verdict, variant="body")],
            ),
            Alert(
                title="Different mechanism",
                message=(
                    "AI-Ready Catalyst Award Competitions are announced "
                    "separately from the Coordination Hub solicitation. "
                    "Different rules, different deadlines. Confirm which "
                    "opportunity you are drafting for so framing is not "
                    "reused from the Hub proposal."
                ),
                variant="info",
            ),
        ])

    # out_of_family
    return create_ui_response([
        Card(
            title="Scope Decision",
            content=[Text(
                content=(
                    "Out of scope. Redirecting back to the Kentucky "
                    "Coordination Hub proposal."
                ),
                variant="body",
            )],
        ),
        Alert(
            title="Out of NSF TechAccess family",
            message=(
                "This request is outside the NSF TechAccess: AI-Ready "
                "America (NSF 26-508) family. Returning focus to the "
                "Kentucky Coordination Hub proposal. Tell me which "
                "section you are working on (Section 1–5 or LOI synopsis) "
                "or which supplemental artifact you need."
            ),
            variant="warning",
        ),
    ])


def _required_subelement_list(section_key: str) -> List_:
    """Return a List_ of the required sub-elements for a section."""
    items = SECTION_REQUIREMENTS.get(section_key, [])
    return List_(items=list(items), ordered=False)


def _ky_anchor_table(partner_keys: Optional[List[str]]) -> Table:
    """Return a Table summarizing the Kentucky partners the draft
    should anchor against."""
    if partner_keys:
        partners = []
        for key in partner_keys:
            try:
                partners.append(get_partner(key))
            except KeyError:
                # Free-string partner — record the name as-is
                partners.append({
                    "key": key,
                    "name": key,
                    "unique_contribution": (
                        "User-supplied partner; contribution to be "
                        "specified by the proposal team."
                    ),
                })
    else:
        partners = list(KY_PARTNERS)

    rows = [
        [p["name"], p.get("unique_contribution", "")]
        for p in partners
    ]
    return Table(
        headers=["Partner", "Unique contribution"],
        rows=rows,
    )


def _build_loi_synopsis_scaffold(
    partner_keys: Optional[List[str]] = None,
    extra_context: str = "",
) -> List[Any]:
    """Shared LOI synopsis builder. Used by both ``draft_loi(produce=
    "synopsis")`` and ``draft_proposal_section(section_key=
    "loi_synopsis")`` so output is identical (Decision 8 / D1).

    Returns the list of UI components for the synopsis Card. The caller
    wraps them in a Card with the canonical heading.
    """
    components: List[Any] = [
        Text(
            content=(
                "One-page synopsis budget: ~"
                f"{LOI_RULES['synopsis_word_budget']} words. The synopsis "
                "must function as compressed Section 1 + Section 2 "
                "narrative — vision, all five Hub responsibilities, lead "
                "organization's convening capacity, partner architecture, "
                "and governance."
            ),
            variant="body",
        ),
        Text(content="Required coverage:", variant="h3"),
        _required_subelement_list("loi_synopsis"),
        Text(content="Hub responsibilities (must all appear):", variant="h3"),
        List_(
            items=[r["name"] for r in HUB_RESPONSIBILITIES],
            ordered=False,
        ),
        Text(content="Kentucky partner architecture:", variant="h3"),
        _ky_anchor_table(partner_keys),
    ]
    if extra_context:
        components.append(
            Text(
                content=f"Team-supplied context: {extra_context}",
                variant="body",
            )
        )
    return components


def draft_loi(
    produce: str = "both",
    descriptive_phrase: str = "",
    pi_email: str = "",
    senior_personnel: Optional[List[Dict[str, Any]]] = None,
    participating_organizations: Optional[List[str]] = None,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Produce LOI title and/or one-page synopsis scaffolds for the
    Kentucky Coordination Hub LOI (due 2026-06-16 via Research.gov).

    Implements FR-002 (LOI scope), FR-013 (title prefix + no acronyms),
    FR-014 (synopsis ≤ 1 page), FR-020 (deadline citation in LOI flow).

    Args:
        produce: One of ``"title"``, ``"synopsis"``, ``"both"``.
        descriptive_phrase: Optional phrase the user wants in the title
            after the required prefix. Acronyms are rejected.
        pi_email: Optional PI email for the LOI's PI/contact field.
        senior_personnel: Optional list of ``{name, affiliation, role}``
            dicts.
        participating_organizations: Optional list of all institutions
            and community partners. Defaults to the likely Kentucky
            partnership architecture.
        session_id: Session identifier (unused; reserved).

    Returns:
        ``create_ui_response`` payload with title and/or synopsis Cards
        plus a deadline-reminder info Alert.
    """
    produce = (produce or "both").lower().strip()
    if produce not in {"title", "synopsis", "both"}:
        logger.warning(
            "draft_loi: invalid produce=%r", produce,
        )
        return create_ui_response([
            Alert(
                message=(
                    "Invalid 'produce' value. Use 'title', 'synopsis', "
                    "or 'both'."
                ),
                variant="error",
                title="Invalid Input",
            )
        ])

    components: List[Any] = []

    # --- Title scaffold ---------------------------------------------
    if produce in {"title", "both"}:
        descriptor = (descriptive_phrase or "").strip()
        # Acronym check — token-wise word boundaries
        offending = _detect_forbidden_acronyms(descriptor)
        if offending:
            logger.warning(
                "draft_loi: title rejected, forbidden acronyms=%s",
                offending,
            )
            return create_ui_response([
                Alert(
                    title="Title contains forbidden acronyms",
                    message=(
                        "The LOI title must not contain acronyms. "
                        f"Found: {', '.join(sorted(set(offending)))}. "
                        "Expand them — for example, 'NSF' → 'National "
                        "Science Foundation', 'AI' → 'Artificial "
                        "Intelligence', 'UK' → 'University of Kentucky'."
                    ),
                    variant="error",
                )
            ])

        title_text = LOI_RULES["title_prefix"]
        if descriptor:
            title_text = f"{title_text} {descriptor}"

        components.append(
            Card(
                title="LOI Title",
                content=[
                    Text(content=title_text, variant="h2"),
                    Text(
                        content=(
                            "The title MUST start with "
                            f"'{LOI_RULES['title_prefix']}' and MUST NOT "
                            "contain acronyms. Add a descriptive phrase "
                            "after the prefix to refine."
                        ),
                        variant="caption",
                    ),
                ],
            )
        )

    # --- Synopsis scaffold ------------------------------------------
    if produce in {"synopsis", "both"}:
        synopsis_components = _build_loi_synopsis_scaffold(
            partner_keys=None,
            extra_context="",
        )
        components.append(
            Card(
                title=SECTION_HEADINGS["loi_synopsis"],
                content=synopsis_components,
            )
        )

    # --- PI / personnel block ---------------------------------------
    personnel_rows: List[List[Any]] = []
    if pi_email:
        personnel_rows.append(["PI (point of contact)", pi_email, ""])
    if senior_personnel:
        for entry in senior_personnel:
            personnel_rows.append([
                entry.get("role", "Senior Personnel"),
                entry.get("name", ""),
                entry.get("affiliation", ""),
            ])
    if not personnel_rows:
        personnel_rows = [[
            "PI (point of contact)",
            "(provide PI name + email)",
            "University of Kentucky",
        ]]
    components.append(
        Card(
            title="PI and Senior Personnel",
            content=[
                Table(
                    headers=["Role", "Name / contact", "Affiliation"],
                    rows=personnel_rows,
                ),
            ],
        )
    )

    # --- Participating organizations block --------------------------
    if participating_organizations:
        org_items = list(participating_organizations)
    else:
        org_items = [p["name"] for p in KY_PARTNERS]
    components.append(
        Card(
            title="Participating Organizations",
            content=[List_(items=org_items, ordered=False)],
        )
    )

    # --- Deadline reminder ------------------------------------------
    components.append(
        Alert(
            title="Deadline reminder",
            message=(
                f"LOI due {DEADLINES['loi']['date_iso']} via "
                f"{DEADLINES['loi']['submission_path']}. No "
                "supplementary documents are permitted in the LOI."
            ),
            variant="info",
        )
    )

    return create_ui_response(components)


def _detect_forbidden_acronyms(text: str) -> List[str]:
    """Tokenize ``text`` and return any token that matches an entry in
    ``LOI_RULES['forbidden_acronyms']``. Matching is case-sensitive
    and applies at three levels:

    1. Whole-token equality with a forbidden entry (catches multi-token
       forbidden entries like ``"K-12"``).
    2. Hyphen-separated subtokens of the whole token (catches embedded
       acronyms like ``"AI-Readiness"`` → ``"AI"``).

    Both levels are required because the spec forbids both bare
    acronyms in the title and acronyms hiding inside hyphenated
    compounds.
    """
    if not text:
        return []
    forbidden = set(LOI_RULES["forbidden_acronyms"])
    offenders: List[str] = []
    for part in text.split():
        cleaned = part.strip(".,;:!?'\"()[]{}")
        if not cleaned:
            continue
        # Whole-token check first (preserves hyphenated entries like K-12).
        if cleaned in forbidden:
            offenders.append(cleaned)
            continue
        # Hyphen subtoken check — but only if the whole token did NOT
        # match a forbidden hyphenated entry. Splits "AI-Readiness" into
        # ["AI", "Readiness"] and checks each.
        if "-" in cleaned:
            for sub in cleaned.split("-"):
                sub_clean = sub.strip()
                if sub_clean and sub_clean in forbidden:
                    offenders.append(sub_clean)
    return offenders


def draft_proposal_section(
    section_key: str,
    opportunity: str = "hub",
    existing_draft: str = "",
    partner_roster_override: Optional[List[str]] = None,
    extra_context: str = "",
    request_administration_priority_alignment: bool = False,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Produce a structured drafting scaffold for any of the five
    full-proposal sections or the LOI synopsis.

    Returns a Card whose title is the exact required heading, plus the
    required-sub-element checklist, applicable Hub responsibilities,
    applicable framing rules, KY partner anchors, and (for Section 4)
    the full NSF-required metric list and extended layers. The
    orchestrator LLM composes prose against this scaffold.

    Implements FR-002 / FR-003 / FR-004 / FR-005 / FR-006 / FR-007 /
    FR-008 / FR-009 / FR-010 / FR-017 / FR-018 / FR-019.

    Args:
        section_key: One of ``loi_synopsis``, ``section_1`` …
            ``section_5``.
        opportunity: One of ``hub``, ``national_lead``, ``catalyst``.
        existing_draft: Optional prior text to use as a starting point.
        partner_roster_override: Optional partner keys to scope the
            draft to.
        extra_context: Optional extra context (PI roster, prior
            decisions, page-budget constraint).
        request_administration_priority_alignment: When true, the
            scaffold names every Administration-priority phrase the
            draft must include.
        session_id: Session identifier (unused; reserved).
    """
    section_key = (section_key or "").strip()
    if section_key not in SECTION_HEADINGS:
        logger.warning(
            "draft_proposal_section: unknown section_key=%r", section_key,
        )
        return create_ui_response([
            Alert(
                title="Unknown section",
                message=(
                    f"Unknown section_key: {section_key!r}. Use one of: "
                    f"{', '.join(sorted(SECTION_HEADINGS))}."
                ),
                variant="error",
            )
        ])

    # Decision 8 / D1 — delegate LOI synopsis to draft_loi so output is
    # identical between entry points.
    if section_key == "loi_synopsis":
        return draft_loi(produce="synopsis", session_id=session_id)

    opportunity = (opportunity or "hub").lower().strip()
    if opportunity not in {"hub", "national_lead", "catalyst"}:
        return create_ui_response([
            Alert(
                title="Unknown opportunity",
                message=(
                    "Unknown opportunity. Use 'hub', 'national_lead', "
                    "or 'catalyst'."
                ),
                variant="error",
            )
        ])

    heading = SECTION_HEADINGS[section_key]
    required = SECTION_REQUIREMENTS[section_key]
    hub_responsibilities = get_hub_responsibilities_for_section(section_key)
    framing_rules = get_framing_rules_for_section(section_key)

    # --- Build the scaffold -----------------------------------------
    section_components: List[Any] = [
        Text(
            content=(
                "Draft the section as clear, direct prose against the "
                "required coverage below. Use the exact heading verbatim."
            ),
            variant="body",
        ),
        Text(content="Required coverage:", variant="h3"),
        List_(items=list(required), ordered=False),
    ]

    if hub_responsibilities:
        section_components.extend([
            Text(
                content="Hub responsibilities to address in this section:",
                variant="h3",
            ),
            Table(
                headers=["Responsibility", "Framing constraint"],
                rows=[
                    [r["name"], r["framing_constraint"]]
                    for r in hub_responsibilities
                ],
            ),
        ])

    if framing_rules:
        section_components.extend([
            Text(content="Framing rules (must be honored):", variant="h3"),
            List_(
                items=[
                    f"{r['key']}: {r['description']}"
                    for r in framing_rules
                ],
                ordered=False,
            ),
        ])

    if partner_roster_override is not None:
        partner_assumption_note = (
            "Partner roster scoped to user-supplied keys."
        )
    else:
        partner_assumption_note = (
            "Partner roster: using the likely Kentucky partnership "
            "architecture as a working assumption — name this assumption "
            "explicitly in the draft."
        )
    section_components.extend([
        Text(content="Kentucky partner anchors:", variant="h3"),
        Text(content=partner_assumption_note, variant="caption"),
        _ky_anchor_table(partner_roster_override),
    ])

    # Section-1-specific equity surface
    if section_key == "section_1":
        section_components.extend([
            Text(content="Equity lenses to address explicitly:", variant="h3"),
            Table(
                headers=["Equity lens", "Trusted-messenger partners"],
                rows=[
                    [
                        lens["name"],
                        ", ".join(
                            get_partner(pk)["name"]
                            for pk in lens["connected_partners"]
                        ) or "(none enumerated)",
                    ]
                    for lens in KY_EQUITY_LENSES
                ],
            ),
        ])

    # Section-4-specific metric scaffold
    if section_key == "section_4":
        section_components.extend([
            Text(
                content="NSF-required performance metrics (all six MUST appear by name):",
                variant="h3",
            ),
            Table(
                headers=["Metric", "Notes"],
                rows=[
                    [m["name"], m["notes"]]
                    for m in NSF_REQUIRED_METRICS
                ],
            ),
            Text(
                content="Extended metric layers (reach / depth / system-change):",
                variant="h3",
            ),
            Table(
                headers=["Metric", "Layer", "Notes"],
                rows=[
                    [m["name"], m["category"], m["notes"]]
                    for m in EXTENDED_METRIC_LAYERS
                ],
            ),
            Alert(
                title="Year 1 baseline + independent evaluation",
                message=(
                    "Year 1 establishes baselines; Years 2–3 track "
                    "against baselines. The draft MUST cite a common "
                    "cross-partner data-collection instrument and an "
                    "independent evaluation component (UK CAAI is "
                    "positioned to play this role)."
                ),
                variant="info",
            ),
        ])

    # AI literacy continuum reminder for any section that touches
    # training (section_1 and section_4 do).
    if section_key in {"section_1", "section_4"}:
        section_components.extend([
            Text(content="AI literacy continuum mapping:", variant="h3"),
            Table(
                headers=["Level", "Definition", "Audience examples"],
                rows=[
                    [
                        lvl["name"],
                        lvl["definition"],
                        ", ".join(lvl["audience_examples"]),
                    ]
                    for lvl in AI_LITERACY_LEVELS
                ],
            ),
            Text(
                content=(
                    "Every training reference in the draft MUST name "
                    "both an audience and a literacy/proficiency/fluency "
                    "level."
                ),
                variant="caption",
            ),
        ])

    # Administration-priority alignment surface (FR-019)
    if request_administration_priority_alignment:
        section_components.extend([
            Text(
                content="Administration-priority alignment phrases (insert at least one verbatim):",
                variant="h3",
            ),
            List_(
                items=list(ADMINISTRATION_PRIORITY_PHRASES),
                ordered=False,
            ),
        ])

    # Existing draft context (if supplied)
    if existing_draft:
        section_components.extend([
            Text(content="Existing draft (refine, do not rewrite from scratch):", variant="h3"),
            Text(content=existing_draft, variant="body"),
        ])

    if extra_context:
        section_components.append(
            Text(
                content=f"Team-supplied context: {extra_context}",
                variant="body",
            )
        )

    response_components: List[Any] = [
        Card(title=heading, content=section_components),
    ]

    if opportunity != "hub":
        family_entry = next(
            (o for o in OPPORTUNITY_FAMILY if o["key"] == opportunity),
            None,
        )
        if family_entry:
            response_components.append(
                Alert(
                    title=f"Different mechanism: {family_entry['name']}",
                    message=family_entry["framing_notes"],
                    variant="info",
                )
            )

    return create_ui_response(response_components)


def _scan_required_subelements(
    section_key: str,
    draft_text: str,
) -> List[Dict[str, Any]]:
    """For each required sub-element of ``section_key``, return a
    coverage row: ``{name, status}`` where status is ``"present"``,
    ``"partial"``, or ``"absent"``.

    Heuristic: split the sub-element into significant tokens (length
    ≥ 4, not a stop-word) and compute the fraction present in the
    draft text (case-insensitive). ≥ 0.6 → present; ≥ 0.3 → partial;
    < 0.3 → absent.
    """
    stopwords = {
        "and", "the", "for", "that", "with", "this", "from", "their",
        "have", "into", "than", "what", "where", "which", "while",
        "they", "them", "those", "these", "such", "must", "will",
        "across", "within", "section", "every", "each", "other",
    }
    rows = []
    text_lower = (draft_text or "").lower()
    for subelement in SECTION_REQUIREMENTS.get(section_key, []):
        tokens = [
            t.lower().strip(".,;:!?'\"()[]{}")
            for t in subelement.split()
        ]
        significant = [
            t for t in tokens
            if len(t) >= 4 and t not in stopwords
        ]
        if not significant:
            status = "absent"
        else:
            present = sum(1 for t in significant if t in text_lower)
            ratio = present / len(significant)
            if ratio >= 0.6:
                status = "present"
            elif ratio >= 0.3:
                status = "partial"
            else:
                status = "absent"
        rows.append({"name": subelement, "status": status})
    return rows


def _scan_framing_violations(
    section_key: str,
    draft_text: str,
) -> List[Dict[str, str]]:
    """Detect substring matches against ``FRAMING_RULES.violation_pattern_hints``
    that apply to ``section_key``. Returns a list of
    ``{rule_key, offender}`` dicts.
    """
    violations: List[Dict[str, str]] = []
    text_lower = (draft_text or "").lower()
    for rule in get_framing_rules_for_section(section_key):
        for hint in rule.get("violation_pattern_hints", []):
            if hint.lower() in text_lower:
                violations.append({
                    "rule_key": rule["key"],
                    "offender": hint,
                })
    return violations


def refine_section(
    section_key: str,
    draft_text: str,
    preserve_factual_claims: bool = True,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Strengthen a pasted draft section: detect tone violations
    (direct-delivery framing, overpromising), surface generic
    "AI training" language, and produce structured guidance for the
    orchestrator LLM to lift into prose rewrites.

    Implements FR-005 / FR-006 / FR-009 / FR-010 / FR-011 / FR-017 /
    FR-018.
    """
    section_key = (section_key or "").strip()
    if section_key not in SECTION_HEADINGS:
        return create_ui_response([
            Alert(
                title="Unknown section",
                message=(
                    f"Unknown section_key: {section_key!r}. Use one of: "
                    f"{', '.join(sorted(SECTION_HEADINGS))}."
                ),
                variant="error",
            )
        ])
    if not draft_text or not str(draft_text).strip():
        return create_ui_response([
            Alert(
                title="No draft supplied",
                message=(
                    "No draft supplied. Use draft_proposal_section to "
                    "start from scratch."
                ),
                variant="error",
            )
        ])

    coverage = _scan_required_subelements(section_key, draft_text)
    violations = _scan_framing_violations(section_key, draft_text)
    generic_training = "ai training" in draft_text.lower()

    refinement_directives: List[str] = []
    if violations:
        refinement_directives.append(
            "Rewrite passages that overcommit to direct delivery or "
            "overpromise. Anchor language in coordination/convening, not "
            "service provision."
        )
    if generic_training:
        refinement_directives.append(
            "Replace generic 'AI training' phrases with specific "
            "literacy/proficiency/fluency level + named audience."
        )
    if any(row["status"] != "present" for row in coverage):
        refinement_directives.append(
            "Strengthen weak or partial sub-elements (see coverage table)."
        )
    if preserve_factual_claims:
        refinement_directives.append(
            "Preserve every named partner, number, and date verbatim."
        )

    components: List[Any] = [
        Card(
            title="Refined Draft",
            content=[
                Text(content=draft_text, variant="body"),
                Text(
                    content=(
                        "Above is the input draft. The orchestrator "
                        "should produce a refined version that honors "
                        "the directives below and addresses every "
                        "weak/absent sub-element in the coverage table."
                    ),
                    variant="caption",
                ),
            ],
        ),
        Card(
            title="What Changed and Why",
            content=[
                Text(
                    content="Refinement directives:",
                    variant="h3",
                ),
                List_(items=refinement_directives, ordered=False)
                if refinement_directives
                else Text(
                    content=(
                        "No refinement directives detected — draft is "
                        "framed correctly. Confirm with a gap-check."
                    ),
                    variant="body",
                ),
                Text(
                    content="Coverage of required sub-elements:",
                    variant="h3",
                ),
                Table(
                    headers=["Sub-element", "Status"],
                    rows=[
                        [row["name"], row["status"]] for row in coverage
                    ],
                ),
                Text(
                    content="Framing violations detected:",
                    variant="h3",
                ),
                Table(
                    headers=["Rule", "Offending phrase"],
                    rows=[
                        [v["rule_key"], v["offender"]] for v in violations
                    ],
                ) if violations else Text(
                    content="None detected.",
                    variant="body",
                ),
            ],
        ),
    ]
    return create_ui_response(components)


def gap_check_section(
    section_key: str,
    draft_text: str,
    include_rewrites: bool = True,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Produce a structured gap analysis of a draft section: required
    sub-element coverage, named verdicts against NSF review criteria,
    framing/tone violations, and suggested-rewrite scaffolding for
    weakest passages.

    Implements FR-011 + US2 acceptance scenarios 1–3.
    """
    section_key = (section_key or "").strip()
    if section_key not in SECTION_HEADINGS:
        return create_ui_response([
            Alert(
                title="Unknown section",
                message=(
                    f"Unknown section_key: {section_key!r}. Use one of: "
                    f"{', '.join(sorted(SECTION_HEADINGS))}."
                ),
                variant="error",
            )
        ])
    if not draft_text or not str(draft_text).strip():
        return create_ui_response([
            Alert(
                title="No draft supplied",
                message="No draft supplied. Provide section text to gap-check.",
                variant="error",
            )
        ])

    coverage = _scan_required_subelements(section_key, draft_text)
    violations = _scan_framing_violations(section_key, draft_text)
    text_lower = draft_text.lower()

    # NSF review criteria (standard + solicitation-specific)
    review_criteria = [
        ("Intellectual Merit", "potential to advance knowledge"),
        ("Broader Impacts", "potential to benefit society"),
        (
            "Vision and approach alignment",
            "clear vision and approach aligned with program goals and Hub responsibilities",
        ),
        (
            "Statewide convening capacity",
            "demonstrates statewide convening and coordination capacity in lead organization and partners",
        ),
        (
            "Understanding of current Kentucky AI efforts",
            "reflects understanding of current Kentucky AI efforts and offers strategies to address gaps",
        ),
        (
            "Realistic milestones & evidence-based scaling",
            "includes realistic milestones, measurable outcomes, and mechanisms for evidence-based scaling",
        ),
        (
            "Resource mobilization",
            "outlines credible strategies for mobilizing additional resources beyond NSF funding",
        ),
    ]
    verdict_rows = []
    for label, criterion_text in review_criteria:
        # Confidence is heuristic: present-coverage ratio across
        # required sub-elements as a proxy for criterion coverage.
        present_count = sum(1 for r in coverage if r["status"] == "present")
        total = max(1, len(coverage))
        coverage_pct = round(100 * present_count / total)
        if coverage_pct >= 75:
            confidence = "high"
        elif coverage_pct >= 50:
            confidence = "medium"
        else:
            confidence = "low"
        verdict_rows.append([label, criterion_text, confidence])

    components: List[Any] = [
        Card(
            title="Required Sub-Element Coverage",
            content=[
                Table(
                    headers=["Sub-element", "Status"],
                    rows=[[row["name"], row["status"]] for row in coverage],
                ),
            ],
        ),
        Card(
            title="Review Criteria Verdicts",
            content=[
                Table(
                    headers=["Criterion", "Definition", "Confidence"],
                    rows=verdict_rows,
                ),
                Text(
                    content=(
                        "Confidence is a heuristic based on required-"
                        "sub-element coverage. The orchestrator should "
                        "produce a one-paragraph verdict per criterion "
                        "anchored in the actual draft text."
                    ),
                    variant="caption",
                ),
            ],
        ),
        Card(
            title="Framing & Tone Violations",
            content=[
                Table(
                    headers=["Rule", "Offending phrase"],
                    rows=[[v["rule_key"], v["offender"]] for v in violations],
                ) if violations else Text(
                    content="None detected.",
                    variant="body",
                ),
            ],
        ),
    ]

    # Section 4–specific Metric Coverage card
    if section_key == "section_4":
        nsf_metric_rows = []
        for metric in NSF_REQUIRED_METRICS:
            # Check by metric key tokens
            tokens = metric["key"].split("_")
            present = all(
                tok in text_lower
                for tok in tokens
                if len(tok) >= 4 and tok not in {"with", "from"}
            ) or metric["name"].lower()[:30] in text_lower
            nsf_metric_rows.append([
                metric["name"],
                "present" if present else "missing",
            ])

        baseline_present = (
            "year 1 baseline" in text_lower
            or "baseline year 1" in text_lower
            or "year-1 baseline" in text_lower
        )
        independent_eval_present = (
            "independent evaluation" in text_lower
            or "independent evaluator" in text_lower
        )
        common_instrument_present = (
            "common instrument" in text_lower
            or "common cross-partner" in text_lower
            or "shared instrument" in text_lower
        )

        components.append(
            Card(
                title="Metric Coverage",
                content=[
                    Text(content="NSF-required metrics:", variant="h3"),
                    Table(
                        headers=["Metric", "Status"],
                        rows=nsf_metric_rows,
                    ),
                    Table(
                        headers=["Required element", "Status"],
                        rows=[
                            [
                                "Year 1 baseline",
                                "present" if baseline_present else "missing",
                            ],
                            [
                                "Independent evaluation component",
                                "present" if independent_eval_present else "missing",
                            ],
                            [
                                "Common cross-partner instrument",
                                "present" if common_instrument_present else "missing",
                            ],
                        ],
                    ),
                ],
            )
        )

    if include_rewrites:
        rewrite_targets = [
            row["name"] for row in coverage
            if row["status"] != "present"
        ]
        if violations:
            rewrite_targets.extend(
                f"Reframe: '{v['offender']}' → coordination/convening language ({v['rule_key']})"
                for v in violations
            )
        if not rewrite_targets:
            rewrite_targets = [
                "No rewrites required — coverage is adequate. Run a "
                "second-pass review for prose tightness."
            ]
        components.append(
            Card(
                title="Suggested Rewrites",
                content=[
                    List_(items=rewrite_targets, ordered=False),
                    Text(
                        content=(
                            "The orchestrator should produce concrete "
                            "rewrites for each item above, lifting "
                            "language from the framing rules and the KY "
                            "partner anchors."
                        ),
                        variant="caption",
                    ),
                ],
            )
        )

    return create_ui_response(components)


_FORBIDDEN_LOC_ENDORSEMENT_PHRASES = [
    "strongly support",
    "fully support",
    "highly recommend",
    "endorse this proposal",
    "endorse the proposal",
    "outstanding",
    "exceptional",
    "letter of support",
]


def draft_supplemental_artifact(
    artifact_key: str,
    partner_key: str = "",
    partner_contribution: str = "",
    budget_includes_postdocs_or_grad_students: bool = False,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Produce a permitted supplemental document (Letter of
    Collaboration, Data Management Plan, or Mentoring Plan). Refuse
    prohibited artifacts (Letters of Support, additional narrative).

    Implements FR-012 and US3 supplemental scenarios.
    """
    artifact_key = (artifact_key or "").strip()
    rule = SUPPLEMENTAL_RULES.get(artifact_key)
    if rule is None:
        return create_ui_response([
            Alert(
                title="Unknown artifact",
                message=(
                    f"Unknown artifact_key: {artifact_key!r}. Use one of: "
                    f"{', '.join(sorted(SUPPLEMENTAL_RULES))}."
                ),
                variant="error",
            )
        ])

    if not rule["is_allowed"]:
        logger.warning(
            "draft_supplemental_artifact: refusing prohibited artifact=%s",
            artifact_key,
        )
        return create_ui_response([
            Alert(
                title="Prohibited supplemental artifact",
                message=rule["refusal_message"],
                variant="error",
            )
        ])

    # Mentoring plan condition gate
    if rule["condition"] == "budget_includes_postdocs_or_grad_students":
        if not budget_includes_postdocs_or_grad_students:
            logger.warning(
                "draft_supplemental_artifact: mentoring_plan refused — "
                "budget flag not set",
            )
            return create_ui_response([
                Alert(
                    title="Mentoring Plan condition not met",
                    message=rule["refusal_message"],
                    variant="error",
                )
            ])

    # --- Letter of Collaboration -----------------------------------
    if artifact_key == "letter_of_collaboration":
        partner_key = (partner_key or "").strip()
        if not partner_key:
            return create_ui_response([
                Alert(
                    title="Partner required",
                    message=(
                        "Specify a partner via 'partner_key' (one of: "
                        f"{', '.join(p['key'] for p in KY_PARTNERS)}) or "
                        "supply a free-string partner name."
                    ),
                    variant="error",
                )
            ])
        partner_name = partner_key
        contribution = partner_contribution.strip() if partner_contribution else ""
        try:
            partner_entry = get_partner(partner_key)
            partner_name = partner_entry["name"]
            if not contribution:
                contribution = partner_entry["unique_contribution"]
        except KeyError:
            # Free-string partner — keep partner_key as the name
            if not contribution:
                contribution = (
                    "(Specify the partner's contribution to the Hub.)"
                )

        # Scrub forbidden endorsement substrings from the (user-supplied)
        # contribution text. The replacement marker is deliberately
        # phrased to NOT contain any token that could re-match a
        # forbidden phrase (otherwise the scrubber would loop).
        scrubbed_contribution = contribution
        replacement_marker = "[endorsement language removed]"
        for phrase in _FORBIDDEN_LOC_ENDORSEMENT_PHRASES:
            # Replace case-insensitively in a single linear pass per
            # phrase. Bounded loop — each iteration shortens the
            # remaining tail being scanned.
            lower = scrubbed_contribution.lower()
            phrase_lower = phrase.lower()
            idx = lower.find(phrase_lower)
            cursor = 0
            buffer: List[str] = []
            while idx >= 0:
                buffer.append(scrubbed_contribution[cursor:idx])
                buffer.append(replacement_marker)
                cursor = idx + len(phrase)
                # Continue search past the replacement to avoid
                # rescanning replacement text.
                idx = lower.find(phrase_lower, cursor)
            buffer.append(scrubbed_contribution[cursor:])
            scrubbed_contribution = "".join(buffer)

        body = (
            f"To the National Science Foundation:\n\n"
            f"If the proposal 'Kentucky Coordination Hub: NSF TechAccess "
            f"AI-Ready America' (NSF 26-508) is selected for funding, "
            f"{partner_name} intends to collaborate as described.\n\n"
            f"Specific contribution:\n{scrubbed_contribution}\n\n"
            f"This letter conforms to PAPPG format. It documents intent "
            f"to collaborate and does not endorse the merits of the "
            f"proposal.\n\n"
            f"Sincerely,\n[Authorized signatory — name, title, "
            f"institution]"
        )
        return create_ui_response([
            Card(
                title=f"Letter of Collaboration — {partner_name}",
                content=[Text(content=body, variant="body")],
            ),
            Alert(
                title="PAPPG format reminder",
                message=(
                    "Letters of Collaboration document intent to "
                    "collaborate and the partner's specific contribution. "
                    "They MUST NOT endorse the merits of the proposal "
                    "(those would be Letters of Support, which are "
                    "prohibited)."
                ),
                variant="info",
            ),
        ])

    # --- Data Management Plan --------------------------------------
    if artifact_key == "data_management_plan":
        body = (
            "Data Management Plan — NSF TechAccess Kentucky Coordination Hub\n\n"
            "1. Data the Hub will collect across partners:\n"
            "   - Training participation (educators, workforce, small business owners)\n"
            "   - Business-assistance outcomes (organizations assisted; hours / dollars saved)\n"
            "   - Convening attendance and guidance facilitated\n"
            "   - AI Deployment Corps roster and assistance activity\n"
            "   - Pre/post AI-literacy assessments mapped to the "
            "literacy → proficiency → fluency continuum\n"
            "   - Reach metrics by sector, geography, demographics, and "
            "prior AI exposure\n"
            "   - System-change indicators (new partnerships, curriculum, "
            "policy, leveraged funding)\n\n"
            "2. Common cross-partner data-collection instrument: a single "
            "instrument designed by UK CAAI (the independent evaluation "
            "component) and used by every partner so cross-partner "
            "comparisons are valid.\n\n"
            "3. Independent evaluation: UK CAAI serves as the independent "
            "evaluator; evaluation data are version-controlled and "
            "auditable.\n\n"
            "4. Data formats and standards: FAIR-aligned where applicable; "
            "open formats (CSV, JSON) for tabular data; controlled "
            "vocabularies for credentials (mapped to DOL AI Literacy "
            "Framework, WIOA, Perkins V).\n\n"
            "5. Access, sharing, and privacy: training-participation and "
            "assessment data containing PII are stored in IRB-approved "
            "systems; aggregated and de-identified data are contributed "
            "to national best-practice repositories.\n\n"
            "6. Retention: data retained for the duration of the award "
            "and at least three years after, per UK Office of Sponsored "
            "Projects policy.\n\n"
            "7. Roles: UK is the steward of record; UK CAAI is the "
            "evaluator; sub-awardees are data producers under a common "
            "data-sharing agreement."
        )
        return create_ui_response([
            Card(
                title="Data Management Plan",
                content=[Text(content=body, variant="body")],
            ),
        ])

    # --- Mentoring Plan --------------------------------------------
    if artifact_key == "mentoring_plan":
        body = (
            "Mentoring Plan — NSF TechAccess Kentucky Coordination Hub\n\n"
            "Postdocs and graduate students supported under this award "
            "will receive structured mentoring spanning research "
            "methodology, professional development, and career "
            "preparation.\n\n"
            "1. Research mentoring: weekly one-on-one meetings with the "
            "supervising PI / co-PI; quarterly review of the individual "
            "development plan (IDP).\n\n"
            "2. Professional development: required participation in UK "
            "Graduate School / Office of Postdoctoral Affairs offerings "
            "covering grant writing, research ethics, peer review, and "
            "communicating with non-technical audiences.\n\n"
            "3. AI-readiness exposure: each postdoc/grad student "
            "completes a structured rotation across at least two Hub "
            "responsibility areas (e.g., AI Deployment Support and "
            "Strategic Plan) so they leave the project fluent across "
            "the coordination model.\n\n"
            "4. Career preparation: annual networking with NSF and NIH "
            "program staff; structured introduction to the AI Deployment "
            "Corps practitioner network; presentation of work at one "
            "national venue per year.\n\n"
            "5. Diversity and inclusion: explicit recruitment from "
            "first-generation and underrepresented communities; "
            "mentoring partnership with KCTCS faculty for cross-"
            "institutional perspectives."
        )
        return create_ui_response([
            Card(
                title="Mentoring Plan",
                content=[Text(content=body, variant="body")],
            ),
        ])

    # Defensive fallback (should never hit — all allowed keys handled).
    return create_ui_response([
        Alert(
            title="Unhandled artifact",
            message=f"Allowed artifact {artifact_key!r} has no implementation.",
            variant="error",
        )
    ])


def _question_overlaps_solicitation(question: str) -> bool:
    """True iff the question text contains any canonical solicitation
    phrase from ``SOLICITATION_VERBATIM_PHRASES``."""
    text = (question or "").lower()
    return any(p.lower() in text for p in SOLICITATION_VERBATIM_PHRASES)


def draft_program_officer_questions(
    topics: Optional[List[str]] = None,
    team_specific_context: str = "",
    max_questions: int = 8,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Produce a structured ready-to-send list of questions for the
    NSF program officer. Filters out topics whose answers are explicit
    in NSF 26-508. Implements FR-015 / SC-012.
    """
    try:
        max_questions = int(max_questions)
    except (TypeError, ValueError):
        max_questions = 8
    max_questions = max(1, min(20, max_questions))

    # Resolve which topics to consider
    if topics:
        requested = set(topics)
        candidates = [
            t for t in PROGRAM_OFFICER_QUESTION_TOPICS
            if t["key"] in requested
        ]
    else:
        candidates = list(PROGRAM_OFFICER_QUESTION_TOPICS)

    if not candidates:
        return create_ui_response([
            Alert(
                title="No matching topics",
                message=(
                    "None of the requested topics are recognized. "
                    f"Available topics: "
                    f"{', '.join(t['key'] for t in PROGRAM_OFFICER_QUESTION_TOPICS)}."
                ),
                variant="error",
            )
        ])

    keep, filtered_out = [], []
    for topic in candidates:
        if topic.get("solicitation_resolved"):
            filtered_out.append(topic)
            continue
        keep.append(topic)

    if not keep:
        return create_ui_response([
            Alert(
                title="All topics already answered in solicitation",
                message=(
                    "Every requested topic has its answer explicit in "
                    "NSF 26-508; there is nothing to ask the program "
                    "officer about."
                ),
                variant="error",
            )
        ])

    # Compose questions, filtering any whose seed phrasing overlaps
    # with canonical solicitation language.
    questions: List[str] = []
    for topic in keep[:max_questions]:
        question = topic["seed_question"]
        if team_specific_context:
            question = (
                f"{question} (In our case: {team_specific_context.strip()})"
            )
        if _question_overlaps_solicitation(question):
            continue
        questions.append(question)

    if not questions:
        return create_ui_response([
            Alert(
                title="No questions remain after filtering",
                message=(
                    "Every candidate question overlapped with verbatim "
                    "solicitation phrasing and was discarded. Refine "
                    "team-specific context."
                ),
                variant="warning",
            )
        ])

    components: List[Any] = [
        Card(
            title="Questions for the NSF Program Officer",
            content=[
                Text(
                    content=(
                        "These questions are scoped to the Kentucky "
                        "Coordination Hub proposal and avoid topics "
                        "already addressed in NSF 26-508."
                    ),
                    variant="body",
                ),
                List_(items=questions, ordered=True),
            ],
        ),
    ]
    if filtered_out:
        components.append(
            Card(
                title="Topics filtered out (already answered in solicitation)",
                content=[
                    List_(
                        items=[t["name"] for t in filtered_out],
                        ordered=False,
                    ),
                ],
            )
        )
    return create_ui_response(components)


def prioritize_page_budget(
    current_pages: Dict[str, Any],
    drafts: Optional[Dict[str, str]] = None,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Surface per-section current-vs-target page allocation, name
    protected required sub-elements, and propose an ordered cut list
    when the 15-page budget is exceeded. Implements FR-016 / SC-013.
    """
    if not isinstance(current_pages, dict) or not current_pages:
        return create_ui_response([
            Alert(
                title="Page allocation required",
                message=(
                    "Provide current_pages as a mapping from section_key "
                    "(section_1 … section_5) to current page count."
                ),
                variant="error",
            )
        ])

    valid_keys = {"section_1", "section_2", "section_3", "section_4", "section_5"}
    for key, value in current_pages.items():
        if key not in valid_keys:
            logger.warning(
                "prioritize_page_budget: unknown section_key=%r", key,
            )
            return create_ui_response([
                Alert(
                    title="Unknown section",
                    message=(
                        f"Unknown section_key in current_pages: {key!r}. "
                        f"Use one of: {', '.join(sorted(valid_keys))}."
                    ),
                    variant="error",
                )
            ])
        try:
            page_count = float(value)
        except (TypeError, ValueError):
            return create_ui_response([
                Alert(
                    title="Invalid page count",
                    message=(
                        f"Page count for {key!r} is not a number: {value!r}."
                    ),
                    variant="error",
                )
            ])
        if page_count < 0:
            return create_ui_response([
                Alert(
                    title="Negative page count",
                    message="Page counts must be non-negative.",
                    variant="error",
                )
            ])

    # Build status table
    rows = []
    total_current = 0.0
    total_target = 0.0
    under_invested: List[str] = []
    for section_key in ("section_1", "section_2", "section_3", "section_4", "section_5"):
        target_pages = float(PAGE_BUDGET[section_key]["target_pages"])
        current = float(current_pages.get(section_key, 0))
        delta = round(current - target_pages, 2)
        rows.append([
            SECTION_HEADINGS[section_key],
            round(current, 2),
            round(target_pages, 2),
            ("+" if delta > 0 else "") + f"{delta}",
        ])
        total_current += current
        total_target += target_pages
        if current > 0 and current < 0.5 * target_pages:
            under_invested.append(SECTION_HEADINGS[section_key])

    rows.append([
        "TOTAL",
        round(total_current, 2),
        round(SOLICITATION_META["narrative_page_limit"], 2),
        ("+" if total_current - 15 > 0 else "")
        + f"{round(total_current - 15, 2)}",
    ])

    components: List[Any] = [
        Card(
            title="Page Budget Status",
            content=[
                Table(
                    headers=["Section", "Current", "Target", "Delta"],
                    rows=rows,
                ),
            ],
        ),
        Card(
            title="Required Sub-Elements (Protected)",
            content=[
                Text(
                    content=(
                        "These sub-elements MUST be preserved in any "
                        "proposed cut. Discretionary text outside these "
                        "lists is the cut surface."
                    ),
                    variant="body",
                ),
                Tabs(tabs=[
                    TabItem(
                        label=SECTION_HEADINGS[sk],
                        content=[
                            List_(
                                items=list(SECTION_REQUIREMENTS[sk]),
                                ordered=False,
                            ),
                        ],
                    )
                    for sk in (
                        "section_1", "section_2", "section_3",
                        "section_4", "section_5",
                    )
                ]),
            ],
        ),
    ]

    if total_current <= 15:
        components.append(
            Alert(
                title="No cuts required",
                message=(
                    f"Current allocation totals {round(total_current, 2)} "
                    "pages — at or under the 15-page limit. Polish, "
                    "don't cut."
                ),
                variant="info",
            )
        )
    else:
        # Build cut list — order by largest positive delta first.
        overage_rows = [
            (sk, current_pages.get(sk, 0) - PAGE_BUDGET[sk]["target_pages"])
            for sk in (
                "section_1", "section_2", "section_3",
                "section_4", "section_5",
            )
            if current_pages.get(sk, 0) > PAGE_BUDGET[sk]["target_pages"]
        ]
        overage_rows.sort(key=lambda x: x[1], reverse=True)
        cut_items = []
        for section_key, overage in overage_rows:
            cut_items.append(
                f"{SECTION_HEADINGS[section_key]}: trim "
                f"{round(overage, 2)} pages of discretionary "
                "elaboration. Preserve every required sub-element listed "
                "above."
            )
        cut_items.append(
            f"Projected total after cuts: ~"
            f"{round(total_current - sum(o for _, o in overage_rows), 2)} "
            "pages (target ≤ 15)."
        )
        components.append(
            Card(
                title="Recommended Cut Order",
                content=[List_(items=cut_items, ordered=True)],
            )
        )

    if under_invested:
        components.append(
            Alert(
                title="Under-investment warning",
                message=(
                    "These sections are below 50% of their target page "
                    "allocation — review whether required sub-elements "
                    f"are adequately covered: {', '.join(under_invested)}."
                ),
                variant="warning",
            )
        )

    return create_ui_response(components)


def cite_deadlines(
    include: Optional[List[str]] = None,
    session_id: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Standalone deadline-citation tool. Returns a Card with the three
    NSF 26-508 deadlines (LOI 2026-06-16, full proposal 2026-07-16,
    internal ~2026-07-09). Implements FR-020 / SC-014.
    """
    valid_keys = list(DEADLINES.keys())
    if include:
        unknown = [k for k in include if k not in valid_keys]
        if unknown:
            return create_ui_response([
                Alert(
                    title="Unknown deadline key",
                    message=(
                        f"Unknown deadline key(s): {', '.join(unknown)}. "
                        f"Use one or more of: {', '.join(valid_keys)}."
                    ),
                    variant="error",
                )
            ])
        keys_to_show = [k for k in valid_keys if k in include]
    else:
        keys_to_show = valid_keys

    rows = []
    for k in keys_to_show:
        d = DEADLINES[k]
        notes = ""
        if k == "full_proposal":
            notes = "AOR signature required"
        elif k == "internal":
            notes = "Approximate; confirm with OSP"
        rows.append([
            d["display_label"],
            d["date_iso"],
            d["submission_path"],
            notes,
        ])

    return create_ui_response([
        Card(
            title="NSF 26-508 Critical Deadlines",
            content=[
                Table(
                    headers=["Deadline", "Date", "Submission path", "Notes"],
                    rows=rows,
                ),
            ],
        ),
    ])


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
    # ───────────────────────────────────────────────────────────────
    #  NSF TechAccess (NSF 26-508) tools
    # ───────────────────────────────────────────────────────────────
    "techaccess_scope_check": {
        "function": techaccess_scope_check,
        "scope": "tools:read",
        "description": (
            "Classify a user request against the NSF TechAccess: "
            "AI-Ready America (NSF 26-508) family. Returns one of "
            "'primary_hub' (Kentucky Coordination Hub), "
            "'sibling_national_lead' (Other Transaction Agreement), "
            "'sibling_catalyst' (AI-Ready Catalyst Award Competition), "
            "or 'out_of_family' with a redirect message. Use when the "
            "user's request might be off-topic or about a sibling "
            "opportunity that has different rules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_request": {
                    "type": "string",
                    "description": (
                        "The free-text user message to classify."
                    ),
                },
            },
            "required": ["user_request"],
        },
    },
    "draft_loi": {
        "function": draft_loi,
        "scope": "tools:search",
        "description": (
            "Produce a scaffold for the NSF 26-508 Letter of Intent — "
            "the title (must begin 'Kentucky Coordination Hub:' and "
            "contain no acronyms) and/or the one-page synopsis "
            "(compressed Section 1 + Section 2). LOI is due 2026-06-16 "
            "via Research.gov."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "produce": {
                    "type": "string",
                    "enum": ["title", "synopsis", "both"],
                    "default": "both",
                    "description": (
                        "Which LOI artifact to draft: 'title', 'synopsis', "
                        "or 'both'."
                    ),
                },
                "descriptive_phrase": {
                    "type": "string",
                    "description": (
                        "Optional phrase to append after 'Kentucky "
                        "Coordination Hub:'. Acronyms are rejected."
                    ),
                },
                "pi_email": {
                    "type": "string",
                    "description": "Optional PI email for the contact field.",
                },
                "senior_personnel": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Optional list of {name, affiliation, role} dicts."
                    ),
                },
                "participating_organizations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of all institutions and community "
                        "partners. Defaults to the likely Kentucky "
                        "partnership architecture if omitted."
                    ),
                },
            },
        },
    },
    "draft_proposal_section": {
        "function": draft_proposal_section,
        "scope": "tools:search",
        "description": (
            "Produce a structured drafting scaffold for any NSF 26-508 "
            "full-proposal section (Section 1 — Vision, Section 2 — "
            "Organizational Background, Section 3 — Current State, "
            "Section 4 — Work Plan & Metrics, Section 5 — Resource "
            "Mobilization) or the LOI synopsis. Returns the exact "
            "required heading, required-sub-element checklist, applicable "
            "Hub responsibilities, framing rules, KY partner anchors, and "
            "(for Section 4) the full NSF-required metric list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_key": {
                    "type": "string",
                    "enum": [
                        "loi_synopsis",
                        "section_1",
                        "section_2",
                        "section_3",
                        "section_4",
                        "section_5",
                    ],
                    "description": "Which section to draft.",
                },
                "opportunity": {
                    "type": "string",
                    "enum": ["hub", "national_lead", "catalyst"],
                    "default": "hub",
                    "description": (
                        "Which TechAccess opportunity. Defaults to the "
                        "Kentucky Coordination Hub."
                    ),
                },
                "existing_draft": {
                    "type": "string",
                    "description": (
                        "Optional prior text to use as a starting point."
                    ),
                },
                "partner_roster_override": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional partner keys to scope the draft to."
                    ),
                },
                "extra_context": {
                    "type": "string",
                    "description": (
                        "Optional extra context (PI roster, prior decisions)."
                    ),
                },
                "request_administration_priority_alignment": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, the scaffold includes Administration-"
                        "priority phrases that the draft must contain."
                    ),
                },
            },
            "required": ["section_key"],
        },
    },
    "refine_section": {
        "function": refine_section,
        "scope": "tools:search",
        "description": (
            "Strengthen a pasted draft of any NSF 26-508 full-proposal "
            "section: detect direct-delivery framing, generic 'AI "
            "training' language, and missing required sub-elements; "
            "return refinement directives plus a coverage table the "
            "orchestrator can rewrite against."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_key": {
                    "type": "string",
                    "enum": [
                        "loi_synopsis",
                        "section_1",
                        "section_2",
                        "section_3",
                        "section_4",
                        "section_5",
                    ],
                },
                "draft_text": {
                    "type": "string",
                    "description": "The user's existing draft to refine.",
                },
                "preserve_factual_claims": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, preserve named partners, numbers, and "
                        "dates verbatim."
                    ),
                },
            },
            "required": ["section_key", "draft_text"],
        },
    },
    "gap_check_section": {
        "function": gap_check_section,
        "scope": "tools:search",
        "description": (
            "Produce a structured gap analysis of a pasted NSF 26-508 "
            "section draft: required-sub-element coverage table, "
            "review-criteria verdicts, framing/tone violations, and "
            "(for Section 4) explicit metric coverage. Drives SC-001 / "
            "SC-002 verification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_key": {
                    "type": "string",
                    "enum": [
                        "loi_synopsis",
                        "section_1",
                        "section_2",
                        "section_3",
                        "section_4",
                        "section_5",
                    ],
                },
                "draft_text": {
                    "type": "string",
                    "description": "The draft text to gap-check.",
                },
                "include_rewrites": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, include a 'Suggested Rewrites' card."
                    ),
                },
            },
            "required": ["section_key", "draft_text"],
        },
    },
    "draft_supplemental_artifact": {
        "function": draft_supplemental_artifact,
        "scope": "tools:search",
        "description": (
            "Produce a permitted NSF 26-508 supplemental document: "
            "PAPPG-format Letter of Collaboration for a named partner, "
            "Data Management Plan, or Mentoring Plan (only if the user "
            "confirms the budget includes postdocs/grad-students). "
            "Refuses prohibited artifacts (Letters of Support, "
            "additional narrative)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_key": {
                    "type": "string",
                    "enum": [
                        "letter_of_collaboration",
                        "data_management_plan",
                        "mentoring_plan",
                        "letter_of_support",
                        "additional_narrative",
                    ],
                    "description": (
                        "The artifact to draft. The last two are "
                        "prohibited and will be refused."
                    ),
                },
                "partner_key": {
                    "type": "string",
                    "description": (
                        "Required when artifact_key='letter_of_collaboration'. "
                        "Either a KY_PARTNERS key (uk, kctcs, cpe, cot, "
                        "cooperative_extension, kced, kentuckianaworks, "
                        "ky_sbdc, kde, uk_caai) or a free-string name."
                    ),
                },
                "partner_contribution": {
                    "type": "string",
                    "description": (
                        "Optional explicit partner contribution. Defaults "
                        "to KY_PARTNERS unique_contribution if the key "
                        "matches."
                    ),
                },
                "budget_includes_postdocs_or_grad_students": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Required true when artifact_key='mentoring_plan'."
                    ),
                },
            },
            "required": ["artifact_key"],
        },
    },
    "draft_program_officer_questions": {
        "function": draft_program_officer_questions,
        "scope": "tools:read",
        "description": (
            "Produce a structured ready-to-send list of questions for "
            "the NSF program officer. Filters out topics whose answers "
            "are explicit in NSF 26-508."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional subset of topic keys to focus on. If "
                        "omitted, every unresolved topic is considered."
                    ),
                },
                "team_specific_context": {
                    "type": "string",
                    "description": (
                        "Optional free-text context that shapes each "
                        "question."
                    ),
                },
                "max_questions": {
                    "type": "integer",
                    "default": 8,
                    "description": "Cap on number of questions (1–20).",
                },
            },
        },
    },
    "prioritize_page_budget": {
        "function": prioritize_page_budget,
        "scope": "tools:read",
        "description": (
            "Advise on prioritization within the 15-page narrative limit. "
            "Produces a per-section current-vs-target page allocation "
            "table, names protected required sub-elements, and proposes "
            "an ordered cut list when the budget is exceeded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "current_pages": {
                    "type": "object",
                    "description": (
                        "Map of section_key → current page count. Keys: "
                        "section_1, section_2, section_3, section_4, "
                        "section_5."
                    ),
                    "additionalProperties": {"type": "number"},
                },
                "drafts": {
                    "type": "object",
                    "description": (
                        "Optional map of section_key → current draft text."
                    ),
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["current_pages"],
        },
    },
    "cite_deadlines": {
        "function": cite_deadlines,
        "scope": "tools:read",
        "description": (
            "Standalone NSF 26-508 deadline-citation tool. Returns the "
            "three relevant dates: LOI 2026-06-16 (Research.gov), full "
            "proposal 2026-07-16 (Research.gov or Grants.gov; AOR "
            "signature required), internal institutional deadline "
            "approximately 2026-07-09."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["loi", "full_proposal", "internal"],
                    },
                    "description": (
                        "Optional subset of deadlines to cite. Defaults to "
                        "all three."
                    ),
                },
            },
        },
    },
}
