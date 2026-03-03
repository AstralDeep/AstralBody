#!/usr/bin/env python3
"""
MCP Tools for the Grant Budgets Agent.

Financial tools designed to augment the frustrating, time-consuming budget
outlines associated with grants. Informed with CGS documentation, NSF/NIH
PAPPG, SAP salary information. Able to analyze cover letters, suggest budget
line items, calculate costs, and output CGS-templated budgets.

Security: Cover letter text is processed in-memory only — never logged or
persisted to disk.
"""
import os
import sys
import re
import logging
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Alert, MetricCard, Grid, Grids,
    BarChart, PieChart, List_, Collapsible, Tabs, TabItem,
    create_ui_response,
)
from agents.grant_budgets.budget_knowledge import (
    CGS_BUDGET_CATEGORIES, NSF_PAPPG_RULES, NIH_BUDGET_RULES,
    DEFAULT_RATES, SALARY_BANDS, COMMON_BUDGET_ITEMS,
    BUDGET_SIGNAL_KEYWORDS, FA_EXCLUSION_RULES,
)
from agents.grant_budgets.uky_research_admin import (
    OFFICES, FORMS_AND_TEMPLATES, POLICIES, INSTITUTIONAL_INFO,
    PROJECT_LIFECYCLE, QUESTION_ROUTING, DEADLINE_RULES, SEARCH_INDEX,
)

logger = logging.getLogger("GrantBudgetTools")


# ── Helper Functions ───────────────────────────────────────────────────

def _fmt_currency(amount: float) -> str:
    """Format a number as USD currency."""
    if amount >= 1_000_000:
        return f"${amount:,.0f}"
    elif amount >= 1_000:
        return f"${amount:,.0f}"
    else:
        return f"${amount:,.2f}"


def _count_keyword_hits(text: str, keywords: List[str]) -> int:
    """Count how many keywords from a list appear in text."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _extract_keyword_matches(text: str, keywords: List[str]) -> List[str]:
    """Return the keywords that appear in the text."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def _confidence_label(score: float) -> str:
    """Convert a 0-1 confidence score to a label."""
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    elif score > 0:
        return "Low"
    return "None"


# ── Tool 1: Analyze Cover Letter ──────────────────────────────────────

def analyze_cover_letter(
    cover_letter_text: str,
    agency: str = "NSF",
    duration_years: int = 3,
    **kwargs,
) -> Dict[str, Any]:
    """
    Securely analyze a grant cover letter to extract budget-relevant signals.
    Cover letter is processed in-memory only — never logged or persisted.

    Returns structured extraction of project scope, personnel needs,
    travel indicators, equipment mentions, and other budget signals.
    """
    if not cover_letter_text or not cover_letter_text.strip():
        return create_ui_response([
            Alert(
                message="No cover letter text provided. Please paste the cover letter content.",
                variant="error",
                title="Missing Input",
            )
        ])

    text = cover_letter_text.strip()
    agency = agency.upper()

    # Analyze each budget signal category
    categories = {}
    for cat_name, keywords in BUDGET_SIGNAL_KEYWORDS.items():
        hits = _count_keyword_hits(text, keywords)
        matches = _extract_keyword_matches(text, keywords)
        max_possible = min(len(keywords), 8)  # Normalize against reasonable max
        confidence = min(hits / max_possible, 1.0) if max_possible > 0 else 0
        categories[cat_name] = {
            "hits": hits,
            "matches": matches,
            "confidence": confidence,
            "label": _confidence_label(confidence),
        }

    # Extract potential numbers (dollar amounts, counts)
    dollar_amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|M|K))?', text)
    year_mentions = re.findall(r'(\d+)\s*[-–]?\s*year', text, re.IGNORECASE)
    personnel_count_hints = re.findall(
        r'(\d+)\s*(?:personnel|researchers|students|postdoc|staff|team members)',
        text, re.IGNORECASE,
    )

    # Build the signal analysis table
    signal_rows = []
    for cat_name, info in categories.items():
        display_name = cat_name.replace("_", " ").title()
        signal_rows.append([
            display_name,
            info["label"],
            str(info["hits"]),
            ", ".join(info["matches"][:5]) if info["matches"] else "—",
        ])

    # Sort by confidence (highest first)
    signal_rows.sort(key=lambda r: {"High": 3, "Medium": 2, "Low": 1, "None": 0}.get(r[1], 0), reverse=True)

    # Build UI
    components = [
        Alert(
            message="Cover letter analyzed securely — content was processed in-memory only and not stored.",
            variant="info",
            title="Security Notice",
        ),
        Card(
            title="Cover Letter Budget Signal Analysis",
            content=[
                Text(content=f"Agency: {agency} | Duration: {duration_years} year(s)", variant="caption"),
                Text(
                    content=f"Document length: {len(text)} characters, ~{len(text.split())} words",
                    variant="caption",
                ),
            ],
        ),
        Table(
            headers=["Category", "Signal Strength", "Keyword Hits", "Keywords Found"],
            rows=signal_rows,
        ),
    ]

    # Add extracted amounts if found
    if dollar_amounts or personnel_count_hints:
        extraction_items = []
        if dollar_amounts:
            extraction_items.append(f"Dollar amounts mentioned: {', '.join(dollar_amounts[:10])}")
        if year_mentions:
            extraction_items.append(f"Duration mentions: {', '.join(set(year_mentions))} year(s)")
        if personnel_count_hints:
            extraction_items.append(f"Personnel count hints: {', '.join(set(personnel_count_hints))}")

        components.append(
            Card(
                title="Extracted Values",
                content=[Text(content=item) for item in extraction_items],
            )
        )

    # Recommendations
    recommendations = []
    for cat_name, info in categories.items():
        if info["confidence"] >= 0.4:
            display_name = cat_name.replace("_", " ").title()
            recommendations.append(
                f"Budget for **{display_name}** — {info['label'].lower()} signal "
                f"detected ({info['hits']} keyword matches)"
            )

    if agency == "NIH" and any(
        a for a in dollar_amounts
        if "million" in a.lower() or "M" in a
    ):
        recommendations.append(
            "Large dollar amounts detected — may require detailed (non-modular) NIH budget"
        )

    if recommendations:
        components.append(
            Card(
                title="Budget Recommendations",
                content=[Text(content=r) for r in recommendations],
            )
        )

    # Agency-specific alerts
    if agency == "NSF":
        components.append(
            Alert(
                message="NSF 2-month salary rule applies. Senior personnel limited to 2 months salary across all NSF awards.",
                variant="warning",
                title="NSF Rule Reminder",
            )
        )
    elif agency == "NIH":
        cap = NIH_BUDGET_RULES["salary_cap"]["current_cap"]
        components.append(
            Alert(
                message=f"NIH salary cap: ${cap:,}/year. Salaries above this cap must be cost-shared by the institution.",
                variant="warning",
                title="NIH Salary Cap",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "categories": {k: {"confidence": v["confidence"], "label": v["label"]}
                          for k, v in categories.items()},
            "dollar_amounts": dollar_amounts,
            "personnel_hints": personnel_count_hints,
            "agency": agency,
            "duration_years": duration_years,
        },
    }


# ── Tool 2: Suggest Budget Items ──────────────────────────────────────

def suggest_budget_items(
    project_type: str = "research",
    agency: str = "NSF",
    duration_years: int = 3,
    personnel_count: int = 4,
    includes_travel: bool = True,
    includes_equipment: bool = False,
    includes_participants: bool = False,
    includes_subcontracts: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """
    Suggest categorized budget line items based on project parameters.
    Items follow PAPPG/CGS budget categories with typical cost ranges.
    """
    agency = agency.upper()
    suggestions = {}

    # A. Senior Personnel
    senior_items = [
        {"item": "PI — salary (person-months)", "typical": "1-2 months summer salary",
         "notes": "2-month cap for NSF" if agency == "NSF" else "Salary cap applies" if agency == "NIH" else ""},
    ]
    if personnel_count > 1:
        senior_items.append(
            {"item": "Co-PI(s) — salary", "typical": "0.5-2 months per Co-PI",
             "notes": "Same 2-month rule applies" if agency == "NSF" else ""}
        )
    suggestions["A. Senior Personnel"] = senior_items

    # B. Other Personnel
    other_items = []
    if personnel_count >= 3:
        other_items.append(
            {"item": "Postdoctoral Researcher", "typical": "$56K-$72K/year (12-month)",
             "notes": "NIH NRSA minimum: $56,484" if agency == "NIH" else ""}
        )
    other_items.append(
        {"item": "Graduate Research Assistant(s)", "typical": "$24K-$38K/year stipend",
         "notes": "Tuition remission budgeted separately"}
    )
    if personnel_count >= 5:
        other_items.append(
            {"item": "Undergraduate Student Worker(s)", "typical": "$12-$20/hour, 10-20 hrs/week",
             "notes": ""}
        )
    suggestions["B. Other Personnel"] = other_items

    # C. Fringe
    suggestions["C. Fringe Benefits"] = [
        {"item": "Faculty fringe", "typical": f"{DEFAULT_RATES['fringe']['faculty']:.0%} of salary",
         "notes": "Use institutional negotiated rate"},
        {"item": "Postdoc fringe", "typical": f"{DEFAULT_RATES['fringe']['postdoc']:.0%} of salary",
         "notes": ""},
        {"item": "Graduate student fringe", "typical": f"{DEFAULT_RATES['fringe']['graduate_student']:.0%} of stipend",
         "notes": "Often minimal for GRAs"},
    ]

    # D. Equipment
    if includes_equipment:
        suggestions["D. Equipment"] = [
            {"item": i["item"], "typical": f"${i['range'][0]:,}-${i['range'][1]:,}",
             "notes": "Excluded from F&A base"}
            for i in COMMON_BUDGET_ITEMS["equipment"][:3]
        ]

    # E. Travel
    if includes_travel:
        travel_items = [
            {"item": "Domestic Conference Trip(s)", "typical": "$1,500-$3,000/trip",
             "notes": "At least 1 domestic trip recommended" if agency == "NSF" else ""},
        ]
        travel_items.append(
            {"item": "Collaboration/Fieldwork Travel", "typical": "$800-$2,000/trip", "notes": ""}
        )
        suggestions["E. Travel"] = travel_items

    # F. Participant Support
    if includes_participants:
        suggestions["F. Participant Support"] = [
            {"item": "Participant Stipends", "typical": "$500-$3,000/participant",
             "notes": "Excluded from F&A. Cannot re-budget without approval."},
            {"item": "Participant Travel", "typical": "Varies by location", "notes": ""},
        ]

    # G. Other Direct Costs
    other_direct = [
        {"item": "Materials and Supplies", "typical": "$2,000-$15,000/year", "notes": ""},
        {"item": "Publication Costs (Open Access)", "typical": "$1,500-$5,000/article", "notes": ""},
    ]
    for ci in COMMON_BUDGET_ITEMS["computing"][:2]:
        rng = ci.get("range_per_year", (0, 0))
        other_direct.append(
            {"item": ci["item"], "typical": f"${rng[0]:,}-${rng[1]:,}/year", "notes": ""}
        )
    if includes_subcontracts:
        other_direct.append(
            {"item": "Subaward(s)", "typical": "Varies",
             "notes": "First $25K per sub included in MTDC"}
        )
    other_direct.append(
        {"item": "Tuition Remission (per GRA)", "typical": f"~${DEFAULT_RATES['tuition_remission']['graduate_per_semester']:,}/semester",
         "notes": "Excluded from F&A base"}
    )
    suggestions["G. Other Direct Costs"] = other_direct

    # I. F&A
    fa_rate = DEFAULT_RATES["f_and_a"]["on_campus_research"]
    suggestions["I. F&A (Indirect) Costs"] = [
        {"item": "F&A on MTDC base", "typical": f"{fa_rate:.0%} of MTDC",
         "notes": FA_EXCLUSION_RULES["description"][:80] + "..."},
    ]

    # Build tabbed UI
    tab_items = []
    for cat_name, items in suggestions.items():
        rows = [[i["item"], i["typical"], i["notes"]] for i in items]
        tab_items.append(
            TabItem(
                label=cat_name,
                content=[
                    Table(
                        headers=["Line Item", "Typical Range", "Notes"],
                        rows=rows,
                    ),
                ],
            )
        )

    components = [
        Card(
            title="Suggested Budget Line Items",
            content=[
                Text(
                    content=(
                        f"Project: {project_type.title()} | Agency: {agency} | "
                        f"Duration: {duration_years}yr | Team: {personnel_count} personnel"
                    ),
                    variant="caption",
                ),
            ],
        ),
        Tabs(tabs=tab_items),
    ]

    # Add agency-specific guidance
    if agency == "NSF":
        components.append(
            Alert(
                message=NSF_PAPPG_RULES["general"]["budget_justification"],
                variant="info",
                title="NSF Budget Justification Requirement",
            )
        )
    elif agency == "NIH":
        threshold = NIH_BUDGET_RULES["modular_budget"]["threshold"]
        components.append(
            Alert(
                message=f"Direct costs under ${threshold:,}/year? Use modular budget ($25K modules). Above? Detailed categorical budget required.",
                variant="info",
                title="NIH Budget Format",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"suggestions": suggestions, "agency": agency, "duration_years": duration_years},
    }


# ── Tool 3: Calculate Salary & FTE ────────────────────────────────────

def calculate_salary_fte(
    personnel: Optional[List[Dict[str, Any]]] = None,
    fringe_rate: float = 0.30,
    **kwargs,
) -> Dict[str, Any]:
    """
    Calculate salary and FTE costs for project personnel.

    Each person in the personnel list should have:
      - name (str): Person's name or role label
      - role (str): e.g., "PI", "Co-PI", "Postdoc", "GRA", "Staff"
      - base_salary (float): Annual base salary
      - fte_percent (float): FTE percentage (e.g., 10 = 10%)
      - months (int): Person-months on the project per year (alternative to fte_percent)
      - is_academic_year (bool): True for 9-month appointment, False for 12-month
    """
    if not personnel:
        # Provide example with default data
        personnel = [
            {"name": "PI (Example)", "role": "PI", "base_salary": 150000,
             "fte_percent": 11.1, "months": 1, "is_academic_year": True},
            {"name": "Co-PI (Example)", "role": "Co-PI", "base_salary": 120000,
             "fte_percent": 11.1, "months": 1, "is_academic_year": True},
            {"name": "Postdoc (Example)", "role": "Postdoc", "base_salary": 60000,
             "fte_percent": 100, "months": 12, "is_academic_year": False},
            {"name": "GRA (Example)", "role": "GRA", "base_salary": 30000,
             "fte_percent": 50, "months": 12, "is_academic_year": False},
        ]

    rows = []
    total_salary = 0
    total_fringe = 0

    for person in personnel:
        name = person.get("name", "Unnamed")
        role = person.get("role", "Staff")
        base = float(person.get("base_salary", 0))
        fte_pct = float(person.get("fte_percent", 0))
        months = person.get("months")
        is_ay = person.get("is_academic_year", False)

        # Determine the effective fringe rate per role
        role_lower = role.lower()
        if "pi" in role_lower or "faculty" in role_lower:
            eff_fringe = DEFAULT_RATES["fringe"]["faculty"]
        elif "postdoc" in role_lower:
            eff_fringe = DEFAULT_RATES["fringe"]["postdoc"]
        elif "gra" in role_lower or "graduate" in role_lower:
            eff_fringe = DEFAULT_RATES["fringe"]["graduate_student"]
        elif "undergrad" in role_lower:
            eff_fringe = DEFAULT_RATES["fringe"]["undergraduate"]
        else:
            eff_fringe = fringe_rate

        # Calculate salary from months if provided, otherwise use FTE%
        if months is not None:
            appt_months = 9 if is_ay else 12
            salary_requested = base * (float(months) / appt_months)
        elif fte_pct > 0:
            salary_requested = base * (fte_pct / 100)
        else:
            salary_requested = 0

        fringe_amount = salary_requested * eff_fringe
        total_cost = salary_requested + fringe_amount

        total_salary += salary_requested
        total_fringe += fringe_amount

        appt_label = "AY (9-mo)" if is_ay else "CY (12-mo)"
        months_display = f"{months}" if months else f"{fte_pct:.1f}% FTE"

        rows.append([
            name,
            role,
            _fmt_currency(base),
            appt_label,
            months_display,
            _fmt_currency(salary_requested),
            f"{eff_fringe:.0%}",
            _fmt_currency(fringe_amount),
            _fmt_currency(total_cost),
        ])

    grand_total = total_salary + total_fringe

    components = [
        Grids(
            columns=3,
            children=[
                MetricCard(title="Total Salary", value=_fmt_currency(total_salary)),
                MetricCard(title="Total Fringe", value=_fmt_currency(total_fringe)),
                MetricCard(title="Personnel Total", value=_fmt_currency(grand_total)),
            ],
        ),
        Table(
            headers=[
                "Name", "Role", "Base Salary", "Appointment",
                "Effort", "Salary Requested", "Fringe Rate",
                "Fringe Amount", "Total Cost",
            ],
            rows=rows,
        ),
    ]

    # Add salary cap warning for NIH
    nih_cap = NIH_BUDGET_RULES["salary_cap"]["current_cap"]
    over_cap = [p for p in personnel if float(p.get("base_salary", 0)) > nih_cap]
    if over_cap:
        names = ", ".join(p.get("name", "?") for p in over_cap)
        components.append(
            Alert(
                message=f"Personnel with salary above NIH cap (${nih_cap:,}): {names}. "
                        f"For NIH proposals, cap the charged salary at ${nih_cap:,}.",
                variant="warning",
                title="NIH Salary Cap Alert",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total_salary": total_salary,
            "total_fringe": total_fringe,
            "grand_total": grand_total,
            "personnel_count": len(personnel),
        },
    }


# ── Tool 4: Calculate Travel Costs ────────────────────────────────────

def calculate_travel_costs(
    trips: Optional[List[Dict[str, Any]]] = None,
    include_defaults: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """
    Estimate travel costs for a grant budget.

    Each trip dict should include:
      - description (str): Purpose of trip
      - destination_type (str): "domestic" or "international"
      - travelers (int): Number of travelers
      - days (int): Number of days
      - per_diem_rate (float, optional): Daily rate (uses GSA defaults if omitted)
      - airfare_estimate (float, optional): Airfare per person (uses defaults if omitted)
    """
    if not trips and include_defaults:
        trips = [
            {"description": "Annual Conference (Domestic)", "destination_type": "domestic",
             "travelers": 2, "days": 4, "airfare_estimate": 500},
            {"description": "Collaboration Visit (Domestic)", "destination_type": "domestic",
             "travelers": 1, "days": 3, "airfare_estimate": 400},
        ]
    elif not trips:
        return create_ui_response([
            Alert(message="No trips specified. Provide trip details or set include_defaults=true.",
                  variant="error", title="Missing Input")
        ])

    gsa = DEFAULT_RATES["gsa_per_diem"]

    rows = []
    total_travel = 0

    for trip in trips:
        desc = trip.get("description", "Trip")
        dest_type = trip.get("destination_type", "domestic").lower()
        travelers = int(trip.get("travelers", 1))
        days = int(trip.get("days", 3))

        # Per diem defaults
        if dest_type == "international":
            default_lodging = gsa["international_lodging_avg"]
            default_meals = gsa["international_meals_avg"]
            default_airfare = 1500
        else:
            default_lodging = gsa["domestic_lodging_avg"]
            default_meals = gsa["domestic_meals_avg"]
            default_airfare = 500

        per_diem = float(trip.get("per_diem_rate", default_lodging + default_meals))
        airfare = float(trip.get("airfare_estimate", default_airfare))

        per_diem_total = per_diem * days * travelers
        airfare_total = airfare * travelers
        trip_total = per_diem_total + airfare_total
        total_travel += trip_total

        rows.append([
            desc,
            dest_type.title(),
            str(travelers),
            str(days),
            _fmt_currency(per_diem),
            _fmt_currency(airfare),
            _fmt_currency(trip_total),
        ])

    components = [
        MetricCard(title="Total Travel Budget", value=_fmt_currency(total_travel)),
        Table(
            headers=["Trip", "Type", "Travelers", "Days", "Per Diem/Day", "Airfare/Person", "Total"],
            rows=rows,
        ),
        Alert(
            message=(
                f"Per diem defaults based on GSA averages: "
                f"Domestic ${gsa['domestic_lodging_avg']+gsa['domestic_meals_avg']}/day, "
                f"International ${gsa['international_lodging_avg']+gsa['international_meals_avg']}/day. "
                f"Check gsa.gov for location-specific rates."
            ),
            variant="info",
            title="GSA Per Diem Rates",
        ),
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"total_travel": total_travel, "trips": len(trips)},
    }


# ── Tool 5: Estimate Equipment Costs ──────────────────────────────────

def estimate_equipment_costs(
    items: Optional[List[Dict[str, Any]]] = None,
    equipment_threshold: float = 5000.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    Estimate and classify equipment vs. supply costs for a grant budget.

    Each item dict should include:
      - description (str): Item description
      - unit_cost (float): Cost per unit
      - quantity (int): Number of units
    """
    if not items:
        items = [
            {"description": "GPU Server (e.g., 4x A100)", "unit_cost": 45000, "quantity": 1},
            {"description": "Workstation (<$5K)", "unit_cost": 3500, "quantity": 2},
            {"description": "External Storage Array", "unit_cost": 8000, "quantity": 1},
        ]

    equipment_rows = []
    supply_rows = []
    total_equipment = 0
    total_supplies = 0

    for item in items:
        desc = item.get("description", "Item")
        unit_cost = float(item.get("unit_cost", 0))
        qty = int(item.get("quantity", 1))
        total = unit_cost * qty

        row = [desc, _fmt_currency(unit_cost), str(qty), _fmt_currency(total)]

        if unit_cost >= equipment_threshold:
            equipment_rows.append(row)
            total_equipment += total
        else:
            supply_rows.append(row)
            total_supplies += total

    components = [
        Grids(
            columns=3,
            children=[
                MetricCard(
                    title="Equipment (>=threshold)",
                    value=_fmt_currency(total_equipment),
                    subtitle="Excluded from F&A base",
                ),
                MetricCard(
                    title="Supplies (<threshold)",
                    value=_fmt_currency(total_supplies),
                    subtitle="Included in F&A base",
                ),
                MetricCard(
                    title="Total",
                    value=_fmt_currency(total_equipment + total_supplies),
                ),
            ],
        ),
    ]

    if equipment_rows:
        components.append(
            Card(
                title=f"Equipment (unit cost >= {_fmt_currency(equipment_threshold)})",
                content=[
                    Table(
                        headers=["Description", "Unit Cost", "Qty", "Total"],
                        rows=equipment_rows,
                    ),
                ],
            )
        )

    if supply_rows:
        components.append(
            Card(
                title=f"Supplies (unit cost < {_fmt_currency(equipment_threshold)})",
                content=[
                    Table(
                        headers=["Description", "Unit Cost", "Qty", "Total"],
                        rows=supply_rows,
                    ),
                ],
            )
        )

    components.append(
        Alert(
            message=(
                f"Federal equipment threshold: {_fmt_currency(equipment_threshold)}. "
                f"Items at or above this cost with a useful life >1 year are classified "
                f"as equipment and excluded from the F&A (MTDC) base."
            ),
            variant="info",
            title="Equipment Classification",
        )
    )

    if total_equipment > 0:
        components.append(
            Alert(
                message="Equipment items require justification in the budget narrative explaining why they are essential to the project.",
                variant="warning",
                title="Justification Required",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total_equipment": total_equipment,
            "total_supplies": total_supplies,
            "total": total_equipment + total_supplies,
            "equipment_count": len(equipment_rows),
            "supply_count": len(supply_rows),
        },
    }


# ── Tool 6: Calculate F&A Costs ───────────────────────────────────────

def calculate_fa_costs(
    direct_costs: Optional[Dict[str, float]] = None,
    fa_rate: float = 0.56,
    fa_base: str = "MTDC",
    excluded_categories: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Calculate Facilities & Administrative (indirect) costs.

    direct_costs: Dict of category -> dollar amount, e.g.:
      {"salary": 200000, "fringe": 50000, "equipment": 45000,
       "travel": 8000, "participant_support": 0, "other_direct": 20000,
       "subawards": 100000, "tuition": 15000}
    """
    if excluded_categories is None:
        excluded_categories = ["equipment", "participant_support", "tuition"]

    if not direct_costs:
        direct_costs = {
            "salary": 200000,
            "fringe": 50000,
            "equipment": 45000,
            "travel": 8000,
            "participant_support": 0,
            "other_direct": 20000,
            "subawards": 100000,
            "tuition": 15000,
        }

    # Calculate MTDC base
    total_direct = sum(direct_costs.values())
    excluded_total = 0
    breakdown_rows = []

    for cat, amount in direct_costs.items():
        included = True
        exclusion_note = ""

        if cat in excluded_categories:
            included = False
            exclusion_note = "Excluded from MTDC"
            excluded_total += amount
        elif cat == "subawards":
            # Only first $25K per subaward included
            sub_amount = float(amount)
            if sub_amount > 25000:
                excluded_portion = sub_amount - 25000
                excluded_total += excluded_portion
                exclusion_note = f"Only first $25K included; ${excluded_portion:,.0f} excluded"
            else:
                exclusion_note = "Fully included (under $25K)"
        else:
            exclusion_note = "Included in MTDC"

        breakdown_rows.append([
            cat.replace("_", " ").title(),
            _fmt_currency(amount),
            exclusion_note,
        ])

    mtdc_base = total_direct - excluded_total
    fa_amount = mtdc_base * fa_rate
    total_costs = total_direct + fa_amount

    components = [
        Grids(
            columns=4,
            children=[
                MetricCard(title="Total Direct Costs", value=_fmt_currency(total_direct)),
                MetricCard(title="MTDC Base", value=_fmt_currency(mtdc_base),
                           subtitle=f"After ${excluded_total:,.0f} exclusions"),
                MetricCard(title=f"F&A ({fa_rate:.0%})", value=_fmt_currency(fa_amount),
                           subtitle=f"Rate: {fa_rate:.0%} on {fa_base}"),
                MetricCard(title="Total Project Cost", value=_fmt_currency(total_costs)),
            ],
        ),
        Card(
            title="MTDC Base Calculation",
            content=[
                Table(
                    headers=["Cost Category", "Amount", "MTDC Treatment"],
                    rows=breakdown_rows,
                ),
            ],
        ),
        Alert(
            message=FA_EXCLUSION_RULES["description"],
            variant="info",
            title="MTDC Exclusion Rules",
        ),
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "total_direct": total_direct,
            "mtdc_base": mtdc_base,
            "excluded_total": excluded_total,
            "fa_rate": fa_rate,
            "fa_amount": fa_amount,
            "total_costs": total_costs,
        },
    }


# ── Tool 7: Generate CGS Budget ───────────────────────────────────────

def generate_cgs_budget(
    project_title: str = "Research Project",
    pi_name: str = "PI Name",
    agency: str = "NSF",
    duration_years: int = 3,
    budget_items: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Generate a full CGS-templated budget with year-by-year breakdown.

    budget_items should contain:
      - senior_personnel: list of {name, role, annual_salary_request, annual_fringe}
      - other_personnel: list of {name, role, annual_cost, annual_fringe}
      - equipment: list of {description, cost, year} (one-time purchases)
      - travel: float (annual travel budget)
      - participant_support: float (annual)
      - other_direct: dict of {item_name: annual_cost}
      - subawards: float (annual)
      - tuition: float (annual)
      - fa_rate: float (default 0.56)
      - annual_escalation: float (default 0.03 for 3% annual increase)
    """
    agency = agency.upper()

    if not budget_items:
        # Provide a realistic example budget
        budget_items = {
            "senior_personnel": [
                {"name": "PI (1 mo summer)", "role": "PI",
                 "annual_salary_request": 16667, "annual_fringe": 5000},
                {"name": "Co-PI (1 mo summer)", "role": "Co-PI",
                 "annual_salary_request": 13333, "annual_fringe": 4000},
            ],
            "other_personnel": [
                {"name": "Postdoc (12 mo)", "role": "Postdoc",
                 "annual_cost": 60000, "annual_fringe": 15000},
                {"name": "GRA (12 mo)", "role": "GRA",
                 "annual_cost": 30000, "annual_fringe": 1500},
            ],
            "equipment": [
                {"description": "GPU Compute Server", "cost": 45000, "year": 1},
            ],
            "travel": 6000,
            "participant_support": 0,
            "other_direct": {
                "Materials & Supplies": 5000,
                "Publication Costs": 3000,
                "Cloud Computing": 10000,
            },
            "subawards": 0,
            "tuition": 15000,
            "fa_rate": 0.56,
            "annual_escalation": 0.03,
        }

    fa_rate = float(budget_items.get("fa_rate", 0.56))
    escalation = float(budget_items.get("annual_escalation", 0.03))

    # Build year-by-year budget
    yearly_budgets = []
    cumulative = {
        "A_senior": 0, "B_other": 0, "C_fringe": 0, "D_equipment": 0,
        "E_travel": 0, "F_participant": 0, "G_other_direct": 0,
        "G_subawards": 0, "G_tuition": 0,
    }

    for year in range(1, duration_years + 1):
        esc = (1 + escalation) ** (year - 1)
        yb = {}

        # A. Senior Personnel
        senior = budget_items.get("senior_personnel", [])
        yb["A_senior_salary"] = sum(
            float(p.get("annual_salary_request", 0)) * esc for p in senior
        )
        yb["A_senior_fringe"] = sum(
            float(p.get("annual_fringe", 0)) * esc for p in senior
        )

        # B. Other Personnel
        other = budget_items.get("other_personnel", [])
        yb["B_other_salary"] = sum(
            float(p.get("annual_cost", 0)) * esc for p in other
        )
        yb["B_other_fringe"] = sum(
            float(p.get("annual_fringe", 0)) * esc for p in other
        )

        # C. Total Fringe
        yb["C_fringe"] = yb["A_senior_fringe"] + yb["B_other_fringe"]

        # D. Equipment (one-time in specified year)
        equip_list = budget_items.get("equipment", [])
        yb["D_equipment"] = sum(
            float(e.get("cost", 0))
            for e in equip_list
            if int(e.get("year", 1)) == year
        )

        # E. Travel
        yb["E_travel"] = float(budget_items.get("travel", 0)) * esc

        # F. Participant Support
        yb["F_participant"] = float(budget_items.get("participant_support", 0)) * esc

        # G. Other Direct Costs
        other_direct = budget_items.get("other_direct", {})
        yb["G_other_items"] = sum(float(v) * esc for v in other_direct.values())
        yb["G_subawards"] = float(budget_items.get("subawards", 0)) * esc
        yb["G_tuition"] = float(budget_items.get("tuition", 0)) * esc
        yb["G_total"] = yb["G_other_items"] + yb["G_subawards"] + yb["G_tuition"]

        # H. Total Direct
        yb["A_total"] = yb["A_senior_salary"]
        yb["B_total"] = yb["B_other_salary"]
        yb["H_total_direct"] = (
            yb["A_total"] + yb["B_total"] + yb["C_fringe"] +
            yb["D_equipment"] + yb["E_travel"] + yb["F_participant"] + yb["G_total"]
        )

        # I. F&A (MTDC excludes equipment, participant support, tuition, sub > 25K)
        mtdc_excluded = yb["D_equipment"] + yb["F_participant"] + yb["G_tuition"]
        if yb["G_subawards"] > 25000:
            mtdc_excluded += (yb["G_subawards"] - 25000)
        yb["I_mtdc_base"] = yb["H_total_direct"] - mtdc_excluded
        yb["I_fa"] = yb["I_mtdc_base"] * fa_rate

        # J. Total
        yb["J_total"] = yb["H_total_direct"] + yb["I_fa"]

        yearly_budgets.append(yb)

        # Accumulate
        cumulative["A_senior"] += yb["A_total"]
        cumulative["B_other"] += yb["B_total"]
        cumulative["C_fringe"] += yb["C_fringe"]
        cumulative["D_equipment"] += yb["D_equipment"]
        cumulative["E_travel"] += yb["E_travel"]
        cumulative["F_participant"] += yb["F_participant"]
        cumulative["G_other_direct"] += yb["G_total"]

    cumulative_direct = sum(yb["H_total_direct"] for yb in yearly_budgets)
    cumulative_fa = sum(yb["I_fa"] for yb in yearly_budgets)
    cumulative_total = sum(yb["J_total"] for yb in yearly_budgets)

    # Build the CGS budget table
    category_labels = [
        ("A. Senior Personnel", "A_total"),
        ("B. Other Personnel", "B_total"),
        ("C. Fringe Benefits", "C_fringe"),
        ("D. Equipment", "D_equipment"),
        ("E. Travel", "E_travel"),
        ("F. Participant Support", "F_participant"),
        ("G. Other Direct Costs", "G_total"),
        ("H. Total Direct Costs", "H_total_direct"),
        ("I. F&A Costs", "I_fa"),
        ("J. TOTAL COSTS", "J_total"),
    ]

    headers = ["Category"] + [f"Year {y}" for y in range(1, duration_years + 1)] + ["Cumulative"]
    rows = []
    for label, key in category_labels:
        row = [label]
        for yb in yearly_budgets:
            row.append(_fmt_currency(yb[key]))
        row.append(_fmt_currency(sum(yb[key] for yb in yearly_budgets)))
        rows.append(row)

    # Budget distribution for pie chart
    cat_totals = {
        "Personnel (A+B)": cumulative["A_senior"] + cumulative["B_other"],
        "Fringe (C)": cumulative["C_fringe"],
        "Equipment (D)": cumulative["D_equipment"],
        "Travel (E)": cumulative["E_travel"],
        "Participant Support (F)": cumulative["F_participant"],
        "Other Direct (G)": cumulative["G_other_direct"],
        "F&A (I)": cumulative_fa,
    }
    # Filter out zero categories
    pie_labels = [k for k, v in cat_totals.items() if v > 0]
    pie_data = [v for v in cat_totals.values() if v > 0]
    pie_colors = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626", "#6366f1", "#94a3b8"]

    components = [
        Card(
            title="CGS Budget Summary",
            content=[
                Text(content=f"Project: {project_title}", variant="h3"),
                Text(content=f"PI: {pi_name} | Agency: {agency} | Duration: {duration_years} years", variant="caption"),
            ],
        ),
        Grids(
            columns=3,
            children=[
                MetricCard(title="Total Direct Costs", value=_fmt_currency(cumulative_direct)),
                MetricCard(title=f"F&A ({fa_rate:.0%} MTDC)", value=_fmt_currency(cumulative_fa)),
                MetricCard(title="Total Project Cost", value=_fmt_currency(cumulative_total)),
            ],
        ),
        Table(headers=headers, rows=rows),
        PieChart(
            title="Budget Distribution",
            labels=pie_labels,
            data=pie_data,
            colors=pie_colors[:len(pie_labels)],
        ),
    ]

    if escalation > 0:
        components.append(
            Alert(
                message=f"Budget includes {escalation:.0%} annual escalation for salary and recurring costs starting Year 2.",
                variant="info",
                title="Annual Escalation",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "project_title": project_title,
            "pi_name": pi_name,
            "agency": agency,
            "duration_years": duration_years,
            "cumulative_direct": cumulative_direct,
            "cumulative_fa": cumulative_fa,
            "cumulative_total": cumulative_total,
            "yearly_budgets": yearly_budgets,
        },
    }


# ── Tool 8: Get Budget Guidelines ─────────────────────────────────────

def get_budget_guidelines(
    agency: str = "NSF",
    topic: str = "all",
    **kwargs,
) -> Dict[str, Any]:
    """
    Return budget rules and guidelines from the knowledge base.
    Covers NSF PAPPG, NIH rules, CGS requirements, and institutional rates.

    Topics: fringe, travel, equipment, fa_rates, salary_caps, participant_support, all
    """
    agency = agency.upper()
    topic = topic.lower()
    components = []

    def _add_nsf_guidelines():
        if topic in ("all", "salary_caps"):
            components.append(
                Card(
                    title="NSF Salary Rules",
                    content=[
                        Text(content=NSF_PAPPG_RULES["salary"]["two_month_rule"]),
                        Text(content=NSF_PAPPG_RULES["salary"]["academic_year"], variant="caption"),
                        Alert(
                            message=NSF_PAPPG_RULES["salary"]["voluntary_committed_cost_sharing"],
                            variant="warning",
                            title="Cost Sharing",
                        ),
                    ],
                )
            )

        if topic in ("all", "equipment"):
            components.append(
                Card(
                    title="NSF Equipment Rules",
                    content=[
                        Text(content=NSF_PAPPG_RULES["equipment"]["definition"]),
                        Text(content=f"Threshold: ${NSF_PAPPG_RULES['equipment']['threshold']:,}"),
                        Text(content=NSF_PAPPG_RULES["equipment"]["f_and_a"], variant="caption"),
                    ],
                )
            )

        if topic in ("all", "travel"):
            components.append(
                Card(
                    title="NSF Travel Rules",
                    content=[
                        Text(content=NSF_PAPPG_RULES["travel"]["domestic_requirement"]),
                        Text(content=NSF_PAPPG_RULES["travel"]["international"]),
                        Alert(
                            message=NSF_PAPPG_RULES["travel"]["fly_america"],
                            variant="warning",
                            title="Fly America Act",
                        ),
                    ],
                )
            )

        if topic in ("all", "participant_support"):
            components.append(
                Card(
                    title="NSF Participant Support",
                    content=[
                        Text(content=NSF_PAPPG_RULES["participant_support"]["definition"]),
                        Alert(
                            message=NSF_PAPPG_RULES["participant_support"]["restrictions"],
                            variant="warning",
                            title="Restrictions",
                        ),
                    ],
                )
            )

    def _add_nih_guidelines():
        if topic in ("all", "salary_caps"):
            cap = NIH_BUDGET_RULES["salary_cap"]
            components.append(
                Card(
                    title="NIH Salary Cap",
                    content=[
                        Text(content=cap["description"]),
                        MetricCard(
                            title="Current Cap",
                            value=f"${cap['current_cap']:,}",
                            subtitle=f"Effective: {cap['effective_date']}",
                        ),
                    ],
                )
            )

        if topic in ("all", "equipment", "fa_rates"):
            mod = NIH_BUDGET_RULES["modular_budget"]
            components.append(
                Card(
                    title="NIH Budget Format",
                    content=[
                        Text(content=mod["description"]),
                        Text(
                            content=f"Modular threshold: ${mod['threshold']:,}/year | Module size: ${mod['module_size']:,}",
                            variant="caption",
                        ),
                    ],
                )
            )

    def _add_rate_guidelines():
        if topic in ("all", "fringe"):
            fringe = DEFAULT_RATES["fringe"]
            rows = [
                ["Faculty", f"{fringe['faculty']:.0%}"],
                ["Staff", f"{fringe['staff']:.0%}"],
                ["Postdoc", f"{fringe['postdoc']:.0%}"],
                ["Graduate Student", f"{fringe['graduate_student']:.0%}"],
                ["Undergraduate", f"{fringe['undergraduate']:.0%}"],
            ]
            components.append(
                Card(
                    title="Fringe Benefit Rates (Representative)",
                    content=[
                        Table(headers=["Category", "Rate"], rows=rows),
                        Alert(
                            message=fringe["description"],
                            variant="info",
                        ),
                    ],
                )
            )

        if topic in ("all", "fa_rates"):
            fa = DEFAULT_RATES["f_and_a"]
            rows = [
                ["On-Campus Research", f"{fa['on_campus_research']:.0%}"],
                ["Off-Campus Research", f"{fa['off_campus_research']:.0%}"],
                ["Instruction", f"{fa['instruction']:.0%}"],
                ["Other Sponsored", f"{fa['other_sponsored']:.0%}"],
            ]
            components.append(
                Card(
                    title="F&A (Indirect Cost) Rates (Representative)",
                    content=[
                        Table(headers=["Activity Type", "Rate"], rows=rows),
                        Text(content=f"Base: {fa['base']} (Modified Total Direct Costs)", variant="caption"),
                        Alert(message=fa["description"], variant="info"),
                    ],
                )
            )
            components.append(
                Card(
                    title="MTDC Exclusion Rules",
                    content=[
                        Text(content=FA_EXCLUSION_RULES["description"]),
                        List_(
                            items=[
                                f"Always excluded: {', '.join(FA_EXCLUSION_RULES['always_excluded'])}",
                                f"Subawards: {FA_EXCLUSION_RULES['partially_excluded']['subawards']['description']}",
                            ],
                        ),
                    ],
                )
            )

    # Build response based on agency
    if agency in ("NSF", "ALL"):
        _add_nsf_guidelines()
    if agency in ("NIH", "ALL"):
        _add_nih_guidelines()
    _add_rate_guidelines()

    # CGS template reference
    if topic == "all":
        cgs_rows = [
            [cat["code"], cat["name"], cat["description"][:80]]
            for cat in CGS_BUDGET_CATEGORIES.values()
        ]
        components.append(
            Collapsible(
                title="CGS Budget Categories Reference (A-J)",
                content=[
                    Table(
                        headers=["Code", "Category", "Description"],
                        rows=cgs_rows,
                    ),
                ],
            )
        )

    if not components:
        components.append(
            Alert(
                message=f"No guidelines found for agency='{agency}', topic='{topic}'. "
                        f"Try topic='all' or agency='NSF'/'NIH'.",
                variant="warning",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"agency": agency, "topic": topic},
    }


# ═══════════════════════════════════════════════════════════════════════
# UKY RESEARCH ADMIN TOOLS (OSPA / CGS / PDO)
# ═══════════════════════════════════════════════════════════════════════


# ── Tool 9: Search Research Admin ─────────────────────────────────────

def search_research_admin(
    query: str,
    office: str = "all",
    category: str = "all",
    **kwargs,
) -> Dict[str, Any]:
    """
    Search across UKy OSPA, CGS, and PDO policies, forms, processes,
    and institutional information. Returns ranked results with source
    citations and direct links.

    This is the primary Q&A tool for UKy research administration.
    """
    if not query or not query.strip():
        return create_ui_response([
            Alert(message="Please provide a search query.", variant="error", title="Missing Query")
        ])

    query_lower = query.lower().strip()
    query_words = set(query_lower.split())
    office_filter = office.upper() if office.lower() != "all" else None
    cat_filter = category.lower() if category.lower() != "all" else None

    # Score each entry in the search index
    scored = []
    for entry in SEARCH_INDEX:
        # Apply filters
        if office_filter and office_filter not in entry.get("office", "").upper():
            continue
        if cat_filter and entry.get("category", "") != cat_filter:
            continue

        score = 0
        title_lower = entry["title"].lower()
        content_lower = entry["content"].lower()
        tags = [t.lower() for t in entry.get("tags", [])]

        # Exact phrase match in title (highest weight)
        if query_lower in title_lower:
            score += 10

        # Exact phrase match in content
        if query_lower in content_lower:
            score += 5

        # Individual word matches
        for word in query_words:
            if len(word) < 3:
                continue
            if word in title_lower:
                score += 3
            if word in content_lower:
                score += 1
            if word in tags:
                score += 4

        if score > 0:
            scored.append((score, entry))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = scored[:10]

    if not top_results:
        # Try question routing as fallback
        routing_match = None
        for topic_key, routing in QUESTION_ROUTING.items():
            if topic_key in query_lower:
                routing_match = routing
                break

        if routing_match:
            office_data = OFFICES.get(routing_match["office"].split("/")[0], {})
            return create_ui_response([
                Alert(
                    message=routing_match["detail"],
                    variant="info",
                    title=f"→ Contact: {routing_match['office']}",
                ),
                Card(
                    title=f"{routing_match['office']} Contact Info",
                    content=[
                        Text(content=f"Email: {office_data.get('email', 'N/A')}"),
                        Text(content=f"Phone: {office_data.get('phone', 'N/A')}"),
                        Text(content=f"URL: {office_data.get('url', 'N/A')}"),
                    ],
                ),
            ])

        return create_ui_response([
            Alert(
                message=f"No results found for '{query}'. Try different keywords or a broader search.",
                variant="warning",
                title="No Results",
            ),
            Card(
                title="Suggestions",
                content=[
                    Text(content="Try searching for:"),
                    List_(items=[
                        "budget, iaf, pif, cost transfer, f&a",
                        "submit proposal, award setup, closeout",
                        "funding search, proposal review, biosketch",
                        "compliance, export control, conflict of interest",
                    ]),
                ],
            ),
        ])

    # Build results UI
    result_cards = []
    for score, entry in top_results:
        card_content = [
            Text(content=entry["content"]),
        ]
        if entry.get("url"):
            card_content.append(
                Text(content=f"Link: {entry['url']}", variant="caption")
            )
        if entry.get("email"):
            card_content.append(
                Text(content=f"Contact: {entry['email']}", variant="caption")
            )
        office_label = entry.get("office", "")
        cat_label = entry.get("category", "").title()

        result_cards.append(
            Card(
                title=f"[{office_label}] {entry['title']}",
                content=card_content,
                variant="default",
            )
        )

    components = [
        Alert(
            message=f"Found {len(top_results)} results for '{query}'",
            variant="success",
            title="Search Results",
        ),
    ] + result_cards

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "query": query,
            "result_count": len(top_results),
            "results": [
                {"title": e["title"], "office": e.get("office"), "score": s}
                for s, e in top_results
            ],
        },
    }


# ── Tool 10: Route Question to Office ─────────────────────────────────

def find_office_contact(
    topic: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Route a research administration question to the correct UKy office
    (OSPA, CGS, or PDO). Answers the common pain point: 'Who do I
    contact about X?'
    """
    if not topic or not topic.strip():
        return create_ui_response([
            Alert(message="Please describe your topic or question.", variant="error")
        ])

    topic_lower = topic.lower().strip()

    # Check direct routing matches
    matches = []
    for key, routing in QUESTION_ROUTING.items():
        if key in topic_lower:
            matches.append((key, routing))

    if not matches:
        # Fuzzy: check each word
        topic_words = set(topic_lower.split())
        for key, routing in QUESTION_ROUTING.items():
            key_words = set(key.split())
            overlap = topic_words & key_words
            if overlap:
                matches.append((key, routing))

    if not matches:
        # No match — show all offices
        components = [
            Alert(
                message=f"Could not determine the right office for '{topic}'. Here are all three offices:",
                variant="warning",
            ),
        ]
        for abbr, office in OFFICES.items():
            components.append(
                Card(
                    title=f"{abbr} — {office['full_name']}",
                    content=[
                        Text(content=office["role_summary"]),
                        Text(content=f"Email: {office.get('email', 'N/A')} | Phone: {office.get('phone', 'N/A')}", variant="caption"),
                        Text(content=f"URL: {office.get('url', 'N/A')}", variant="caption"),
                    ],
                )
            )
        return create_ui_response(components)

    # Deduplicate by office
    seen_offices = set()
    unique_matches = []
    for key, routing in matches:
        office_name = routing["office"]
        if office_name not in seen_offices:
            seen_offices.add(office_name)
            unique_matches.append((key, routing))

    components = [
        Alert(
            message=f"For '{topic}', contact the following office(s):",
            variant="success",
            title="Office Routing",
        ),
    ]

    for key, routing in unique_matches:
        primary_office = routing["office"].split("/")[0]
        office_data = OFFICES.get(primary_office, {})

        detail_content = [
            Text(content=routing["detail"]),
        ]
        if office_data:
            detail_content.extend([
                Text(content=f"Email: {office_data.get('email', 'N/A')}", variant="caption"),
                Text(content=f"Phone: {office_data.get('phone', 'N/A')}", variant="caption"),
                Text(content=f"Location: {office_data.get('location', 'N/A')}", variant="caption"),
            ])
            if office_data.get("url"):
                detail_content.append(
                    Text(content=f"Website: {office_data['url']}", variant="caption")
                )

        components.append(
            Card(
                title=f"{routing['office']} — {office_data.get('full_name', routing['office'])}",
                content=detail_content,
            )
        )

    # Add "what they DON'T handle" to avoid confusion
    for key, routing in unique_matches:
        primary_office = routing["office"].split("/")[0]
        office_data = OFFICES.get(primary_office, {})
        does_not = office_data.get("does_not_handle", [])
        if does_not:
            components.append(
                Collapsible(
                    title=f"What {primary_office} does NOT handle",
                    content=[List_(items=does_not)],
                )
            )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "topic": topic,
            "routed_to": [r["office"] for _, r in unique_matches],
        },
    }


# ── Tool 11: Calculate Submission Deadlines ────────────────────────────

def calculate_submission_deadlines(
    sponsor_deadline: str,
    college: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """
    Calculate cascading internal deadlines given a sponsor submission deadline.
    Computes PIF (30 business days), college IAF, and OSPA 3-business-day deadlines.

    sponsor_deadline: Date string (YYYY-MM-DD or MM/DD/YYYY)
    college: Optional college name to estimate college-specific IAF deadline
    """
    from datetime import datetime, timedelta

    if not sponsor_deadline:
        return create_ui_response([
            Alert(message="Please provide the sponsor deadline date (YYYY-MM-DD).", variant="error")
        ])

    # Parse date
    parsed = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(sponsor_deadline.strip(), fmt)
            break
        except ValueError:
            continue

    if not parsed:
        return create_ui_response([
            Alert(
                message=f"Could not parse date '{sponsor_deadline}'. Use YYYY-MM-DD format.",
                variant="error",
            )
        ])

    def _subtract_business_days(start: datetime, days: int) -> datetime:
        """Subtract N business days from a date."""
        current = start
        remaining = days
        while remaining > 0:
            current -= timedelta(days=1)
            if current.weekday() < 5:  # Monday-Friday
                remaining -= 1
        return current

    # Calculate deadlines
    ospa_deadline = _subtract_business_days(parsed, 3)
    college_iaf_early = _subtract_business_days(ospa_deadline, 14)
    college_iaf_late = _subtract_business_days(ospa_deadline, 5)
    pif_deadline = _subtract_business_days(parsed, 30)

    date_fmt = "%A, %B %d, %Y"

    rows = [
        ["PIF to CGS", pif_deadline.strftime(date_fmt),
         "30 business days before sponsor deadline",
         DEADLINE_RULES["pif_to_cgs"]["description"]],
        ["College IAF Deadline (earliest)", college_iaf_early.strftime(date_fmt),
         "14 business days before OSPA deadline",
         "Some colleges require 14 business days. Check with your department."],
        ["College IAF Deadline (latest)", college_iaf_late.strftime(date_fmt),
         "5 business days before OSPA deadline",
         "Minimum college lead time. Most colleges fall in the 5-14 day range."],
        ["IAF to OSPA", ospa_deadline.strftime(date_fmt),
         "3 business days before sponsor deadline",
         DEADLINE_RULES["iaf_to_ospa"]["description"]],
        ["SPONSOR DEADLINE", parsed.strftime(date_fmt),
         "—", "Final submission date to the funding agency."],
    ]

    # Days from today
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_to_sponsor = (parsed - today).days
    days_to_pif = (pif_deadline - today).days
    days_to_ospa = (ospa_deadline - today).days

    components = [
        Card(
            title="Submission Deadline Timeline",
            content=[
                Text(content=f"Sponsor Deadline: {parsed.strftime(date_fmt)}", variant="h3"),
                Text(
                    content=f"{days_to_sponsor} calendar days from today" if days_to_sponsor > 0 else "DEADLINE HAS PASSED",
                    variant="caption",
                ),
            ],
        ),
        Grids(
            columns=3,
            children=[
                MetricCard(
                    title="Days to PIF",
                    value=str(max(days_to_pif, 0)),
                    subtitle=pif_deadline.strftime("%b %d"),
                    variant="default" if days_to_pif > 5 else "default",
                ),
                MetricCard(
                    title="Days to OSPA",
                    value=str(max(days_to_ospa, 0)),
                    subtitle=ospa_deadline.strftime("%b %d"),
                ),
                MetricCard(
                    title="Days to Sponsor",
                    value=str(max(days_to_sponsor, 0)),
                    subtitle=parsed.strftime("%b %d"),
                ),
            ],
        ),
        Table(
            headers=["Milestone", "Date", "Rule", "Details"],
            rows=rows,
        ),
    ]

    # Urgency alerts
    if days_to_pif < 0:
        components.append(
            Alert(
                message="PIF deadline has PASSED. Contact CGS immediately to discuss options.",
                variant="error",
                title="PIF Overdue",
            )
        )
    elif days_to_pif <= 5:
        components.append(
            Alert(
                message=f"PIF deadline is in {days_to_pif} days! Submit the Proposal Initiation Form to CGS ASAP.",
                variant="warning",
                title="PIF Due Soon",
            )
        )

    if days_to_ospa < 0:
        components.append(
            Alert(
                message="OSPA 3-day deadline has PASSED. VPR Late Policy may apply. Contact OSPA immediately.",
                variant="error",
                title="OSPA Deadline Overdue",
            )
        )

    if college:
        components.append(
            Alert(
                message=f"College '{college}' — check with your department for the exact college-level IAF deadline (typically 5-14 business days before OSPA deadline).",
                variant="info",
                title="College-Specific Deadline",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "sponsor_deadline": parsed.isoformat(),
            "pif_deadline": pif_deadline.isoformat(),
            "ospa_deadline": ospa_deadline.isoformat(),
            "days_to_sponsor": days_to_sponsor,
            "days_to_pif": days_to_pif,
            "days_to_ospa": days_to_ospa,
        },
    }


# ── Tool 12: Get Institutional Info ────────────────────────────────────

def get_institutional_info(
    info_type: str = "all",
    **kwargs,
) -> Dict[str, Any]:
    """
    Quick lookup for UKy institutional boilerplate: identifiers (DUNS, UEI, EIN),
    F&A rates, address, authorized representative info, Cayuse details, etc.
    The stuff you always need for proposals but can never find quickly.

    info_type: identifiers, f_and_a, address, cayuse, all
    """
    info_type = info_type.lower()
    components = []

    if info_type in ("all", "identifiers"):
        components.append(
            Card(
                title="Institutional Identifiers",
                content=[
                    Table(
                        headers=["Field", "Value"],
                        rows=[
                            ["Legal Name", INSTITUTIONAL_INFO["legal_name"]],
                            ["UEI (SAM)", INSTITUTIONAL_INFO["uei_number"]],
                            ["DUNS", INSTITUTIONAL_INFO["duns_number"]],
                            ["EIN", INSTITUTIONAL_INFO["ein"]],
                            ["CAGE Code", INSTITUTIONAL_INFO["cage_code"]],
                            ["SAM Status", INSTITUTIONAL_INFO["sam_status"]],
                            ["Congressional District", INSTITUTIONAL_INFO["congressional_district"]],
                            ["Institution Type", INSTITUTIONAL_INFO["institution_type"]],
                            ["Fiscal Year", INSTITUTIONAL_INFO["fiscal_year"]],
                        ],
                    ),
                ],
            )
        )

    if info_type in ("all", "address"):
        addr = INSTITUTIONAL_INFO["address"]
        components.append(
            Card(
                title="Institutional Address",
                content=[
                    Text(content=INSTITUTIONAL_INFO["legal_name"], variant="h3"),
                    Text(content=addr["street"]),
                    Text(content=f"{addr['city']}, {addr['state']} {addr['zip']}"),
                    Text(content=addr["country"]),
                ],
            )
        )
        aor = INSTITUTIONAL_INFO["authorized_organizational_representative"]
        components.append(
            Alert(
                message=aor["note"],
                variant="warning",
                title="Authorized Organizational Representative (AOR)",
            )
        )

    if info_type in ("all", "f_and_a"):
        fa_rates = INSTITUTIONAL_INFO["f_and_a_rates"]
        rate_rows = []
        for activity, info in fa_rates.items():
            if isinstance(info, dict) and "rate" in info:
                rate_rows.append([
                    activity.replace("_", " ").title(),
                    f"{info['rate']:.0%}",
                    info["description"],
                ])
        components.append(
            Card(
                title="F&A (Indirect Cost) Rates",
                content=[
                    Table(
                        headers=["Activity", "Rate", "Description"],
                        rows=rate_rows,
                    ),
                    Text(content=f"Base: {fa_rates.get('base', 'MTDC')}", variant="caption"),
                    Alert(
                        message=fa_rates.get("note", ""),
                        variant="info",
                        title="Note",
                    ),
                ],
            )
        )
        cog = INSTITUTIONAL_INFO["cognizant_agency"]
        components.append(
            Text(
                content=f"Cognizant Agency: {cog['agency']} — {cog['description']}",
                variant="caption",
            )
        )

    if info_type in ("all", "cayuse"):
        cay = INSTITUTIONAL_INFO["cayuse_info"]
        components.append(
            Card(
                title="Cayuse (Electronic Submission System)",
                content=[
                    Text(content=cay["description"]),
                    Alert(
                        message=cay["access_note"],
                        variant="warning",
                        title="Access Note",
                    ),
                ],
            )
        )

    if not components:
        components.append(
            Alert(
                message=f"Unknown info_type '{info_type}'. Use: identifiers, f_and_a, address, cayuse, or all.",
                variant="warning",
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"info_type": info_type},
    }


# ── Tool 13: Lookup Forms & Templates ─────────────────────────────────

def lookup_forms_templates(
    query: str = "",
    office: str = "all",
    **kwargs,
) -> Dict[str, Any]:
    """
    Find specific forms, templates, and resources from OSPA, CGS, and PDO.
    Answers: 'Where is the IAF form?' 'What templates does CGS have?'
    """
    office_filter = office.upper() if office.lower() != "all" else None
    query_lower = query.lower().strip() if query else ""

    filtered = []
    for form in FORMS_AND_TEMPLATES:
        if office_filter and office_filter not in form["office"].upper():
            continue

        if query_lower:
            # Match against name, purpose, tags
            searchable = (
                form["name"].lower() + " " +
                form["purpose"].lower() + " " +
                " ".join(form.get("tags", []))
            )
            if not any(word in searchable for word in query_lower.split() if len(word) >= 3):
                continue

        filtered.append(form)

    if not filtered:
        return create_ui_response([
            Alert(
                message=f"No forms found matching '{query}' (office={office}). Try a broader search.",
                variant="warning",
            ),
            Card(
                title="Available Form Categories",
                content=[
                    List_(items=[
                        "Pre-award: IAF, PIF, IP waivers, Safe Work Plan",
                        "Post-award: Request for Action, Cost Transfer, Closeout",
                        "Templates: Budget, Contract, Clinical Trial, SBIR/STTR",
                        "PDO: Data Management Plan, Facilities Description, Funding Search",
                    ]),
                ],
            ),
        ])

    rows = []
    for form in filtered:
        url_text = form.get("url", "Contact office")
        deadline = form.get("deadline_rule", "—")
        rows.append([
            form["name"],
            form["office"],
            form["purpose"][:100] + ("..." if len(form["purpose"]) > 100 else ""),
            deadline[:60] if deadline != "—" else "—",
        ])

    components = [
        Alert(
            message=f"Found {len(filtered)} form(s)/template(s)" + (f" matching '{query}'" if query else ""),
            variant="success",
        ),
        Table(
            headers=["Form/Template", "Office", "Purpose", "Deadline/Rule"],
            rows=rows,
        ),
    ]

    # Add detail cards for forms with URLs
    forms_with_urls = [f for f in filtered if f.get("url")]
    if forms_with_urls:
        components.append(
            Collapsible(
                title="Direct Links",
                content=[
                    List_(items=[
                        f"{f['name']} ({f['office']}): {f['url']}"
                        for f in forms_with_urls
                    ]),
                ],
                default_open=True,
            )
        )

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "query": query,
            "result_count": len(filtered),
            "forms": [{"name": f["name"], "office": f["office"]} for f in filtered],
        },
    }


# ── Tool Registry ─────────────────────────────────────────────────────

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "analyze_cover_letter": {
        "function": analyze_cover_letter,
        "description": (
            "Securely analyze a grant cover letter to extract budget-relevant "
            "signals. Identifies personnel needs, equipment, travel, computing, "
            "participant support, and subcontract indicators. Cover letter is "
            "processed in-memory only and never stored."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cover_letter_text": {
                    "type": "string",
                    "description": "The full text of the grant cover letter to analyze.",
                },
                "agency": {
                    "type": "string",
                    "description": "Target funding agency: NSF, NIH, DOE, DOD.",
                    "default": "NSF",
                },
                "duration_years": {
                    "type": "integer",
                    "description": "Project duration in years.",
                    "default": 3,
                },
            },
            "required": ["cover_letter_text"],
        },
    },
    "suggest_budget_items": {
        "function": suggest_budget_items,
        "description": (
            "Suggest categorized budget line items based on project parameters. "
            "Returns items organized by CGS/PAPPG categories (A-J) with typical "
            "cost ranges and agency-specific notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_type": {
                    "type": "string",
                    "description": "Type of project: research, training, infrastructure, center.",
                    "default": "research",
                },
                "agency": {
                    "type": "string",
                    "description": "Target agency: NSF, NIH, DOE, DOD.",
                    "default": "NSF",
                },
                "duration_years": {
                    "type": "integer",
                    "description": "Project duration in years.",
                    "default": 3,
                },
                "personnel_count": {
                    "type": "integer",
                    "description": "Total number of personnel on the project.",
                    "default": 4,
                },
                "includes_travel": {
                    "type": "boolean",
                    "description": "Whether the project includes travel.",
                    "default": True,
                },
                "includes_equipment": {
                    "type": "boolean",
                    "description": "Whether the project includes equipment purchases.",
                    "default": False,
                },
                "includes_participants": {
                    "type": "boolean",
                    "description": "Whether the project has participant support costs.",
                    "default": False,
                },
                "includes_subcontracts": {
                    "type": "boolean",
                    "description": "Whether the project includes subawards/subcontracts.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    "calculate_salary_fte": {
        "function": calculate_salary_fte,
        "description": (
            "Calculate salary and FTE costs for project personnel. Handles "
            "academic-year (9-month) and calendar-year (12-month) appointments, "
            "applies role-appropriate fringe rates, and flags NIH salary cap issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "personnel": {
                    "type": "array",
                    "description": (
                        "List of personnel objects. Each should have: name (str), "
                        "role (str: PI/Co-PI/Postdoc/GRA/Staff), base_salary (float), "
                        "fte_percent (float: e.g. 10 for 10%), months (int, optional), "
                        "is_academic_year (bool, default false)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "base_salary": {"type": "number"},
                            "fte_percent": {"type": "number"},
                            "months": {"type": "integer"},
                            "is_academic_year": {"type": "boolean", "default": False},
                        },
                    },
                },
                "fringe_rate": {
                    "type": "number",
                    "description": "Default fringe rate if role-specific rate not available.",
                    "default": 0.30,
                },
            },
            "required": [],
        },
    },
    "calculate_travel_costs": {
        "function": calculate_travel_costs,
        "description": (
            "Estimate travel costs for a grant budget. Calculates per-trip costs "
            "using airfare estimates and GSA per diem rates (defaults provided). "
            "Supports domestic and international travel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "trips": {
                    "type": "array",
                    "description": (
                        "List of trip objects. Each: description (str), "
                        "destination_type (domestic/international), travelers (int), "
                        "days (int), per_diem_rate (float, optional), "
                        "airfare_estimate (float, optional)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "destination_type": {"type": "string", "default": "domestic"},
                            "travelers": {"type": "integer", "default": 1},
                            "days": {"type": "integer", "default": 3},
                            "per_diem_rate": {"type": "number"},
                            "airfare_estimate": {"type": "number"},
                        },
                    },
                },
                "include_defaults": {
                    "type": "boolean",
                    "description": "If true and no trips provided, use example trips.",
                    "default": True,
                },
            },
            "required": [],
        },
    },
    "estimate_equipment_costs": {
        "function": estimate_equipment_costs,
        "description": (
            "Estimate and classify equipment vs. supply costs. Items at or above "
            "the federal threshold ($5,000) are classified as equipment and "
            "excluded from the F&A (MTDC) base."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": (
                        "List of item objects. Each: description (str), "
                        "unit_cost (float), quantity (int)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "unit_cost": {"type": "number"},
                            "quantity": {"type": "integer", "default": 1},
                        },
                    },
                },
                "equipment_threshold": {
                    "type": "number",
                    "description": "Dollar threshold for equipment classification.",
                    "default": 5000.0,
                },
            },
            "required": [],
        },
    },
    "calculate_fa_costs": {
        "function": calculate_fa_costs,
        "description": (
            "Calculate Facilities & Administrative (indirect) costs on the MTDC base. "
            "Automatically excludes equipment, participant support, tuition, and "
            "subaward amounts over $25K per the federal rules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direct_costs": {
                    "type": "object",
                    "description": (
                        "Dict of cost category to dollar amount. Keys: salary, fringe, "
                        "equipment, travel, participant_support, other_direct, subawards, tuition."
                    ),
                },
                "fa_rate": {
                    "type": "number",
                    "description": "F&A rate as a decimal (e.g. 0.56 for 56%).",
                    "default": 0.56,
                },
                "fa_base": {
                    "type": "string",
                    "description": "F&A base type: MTDC or TDC.",
                    "default": "MTDC",
                },
                "excluded_categories": {
                    "type": "array",
                    "description": "Categories excluded from MTDC base.",
                    "items": {"type": "string"},
                },
            },
            "required": [],
        },
    },
    "generate_cgs_budget": {
        "function": generate_cgs_budget,
        "description": (
            "Generate a full CGS-templated budget with year-by-year breakdown "
            "and cumulative totals. Outputs standard budget categories A-J with "
            "automatic F&A calculation, annual escalation, and budget distribution chart."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_title": {
                    "type": "string",
                    "description": "Title of the project.",
                    "default": "Research Project",
                },
                "pi_name": {
                    "type": "string",
                    "description": "Name of the Principal Investigator.",
                    "default": "PI Name",
                },
                "agency": {
                    "type": "string",
                    "description": "Funding agency: NSF, NIH, DOE, DOD.",
                    "default": "NSF",
                },
                "duration_years": {
                    "type": "integer",
                    "description": "Project duration in years.",
                    "default": 3,
                },
                "budget_items": {
                    "type": "object",
                    "description": (
                        "Budget data with keys: senior_personnel (list), "
                        "other_personnel (list), equipment (list with year field), "
                        "travel (float/year), participant_support (float/year), "
                        "other_direct (dict of item:cost/year), subawards (float/year), "
                        "tuition (float/year), fa_rate (float), annual_escalation (float)."
                    ),
                },
            },
            "required": [],
        },
    },
    "get_budget_guidelines": {
        "function": get_budget_guidelines,
        "description": (
            "Return budget rules and guidelines from the knowledge base. "
            "Covers NSF PAPPG rules, NIH salary caps/modular budgets, "
            "F&A/MTDC rules, fringe rates, travel requirements, and CGS categories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agency": {
                    "type": "string",
                    "description": "Agency to get guidelines for: NSF, NIH, or ALL.",
                    "default": "NSF",
                },
                "topic": {
                    "type": "string",
                    "description": (
                        "Specific topic: fringe, travel, equipment, fa_rates, "
                        "salary_caps, participant_support, or all."
                    ),
                    "default": "all",
                },
            },
            "required": [],
        },
    },

    # ── UKy Research Admin Tools ──────────────────────────────────────

    "search_research_admin": {
        "function": search_research_admin,
        "description": (
            "Search across UKy OSPA, CGS, and PDO policies, forms, processes, "
            "and institutional information. The primary Q&A tool for UKy research "
            "administration — answers questions and cites sources with direct links."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query — e.g., 'cost transfer', 'IAF deadline', "
                        "'export control', 'funding search', 'F&A rate'."
                    ),
                },
                "office": {
                    "type": "string",
                    "description": "Filter by office: OSPA, CGS, PDO, or all.",
                    "default": "all",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by type: office, form, policy, process, rate, institutional, or all.",
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    },
    "find_office_contact": {
        "function": find_office_contact,
        "description": (
            "Route a research admin question to the correct UKy office (OSPA, CGS, or PDO). "
            "Answers: 'Who do I contact about budget development?' → CGS. "
            "'Who submits my proposal?' → OSPA. 'Who reviews my narrative?' → PDO."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "The topic or question — e.g., 'submit proposal', 'budget help', "
                        "'funding search', 'cost transfer', 'clinical trial'."
                    ),
                },
            },
            "required": ["topic"],
        },
    },
    "calculate_submission_deadlines": {
        "function": calculate_submission_deadlines,
        "description": (
            "Calculate cascading internal deadlines given a sponsor submission deadline. "
            "Computes PIF (30 business days), college IAF (5-14 business days before OSPA), "
            "and OSPA 3-business-day deadlines with urgency alerts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sponsor_deadline": {
                    "type": "string",
                    "description": "Sponsor submission deadline date (YYYY-MM-DD or MM/DD/YYYY).",
                },
                "college": {
                    "type": "string",
                    "description": "Optional college name to help estimate college-specific IAF deadline.",
                    "default": "",
                },
            },
            "required": ["sponsor_deadline"],
        },
    },
    "get_institutional_info": {
        "function": get_institutional_info,
        "description": (
            "Quick lookup for UKy institutional boilerplate: DUNS, UEI, EIN, CAGE code, "
            "F&A rates, institutional address, AOR info, Cayuse details. "
            "The stuff you always need for proposals but can never find."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "info_type": {
                    "type": "string",
                    "description": "Type of info: identifiers, f_and_a, address, cayuse, or all.",
                    "default": "all",
                },
            },
            "required": [],
        },
    },
    "lookup_forms_templates": {
        "function": lookup_forms_templates,
        "description": (
            "Find specific forms, templates, and resources from UKy OSPA, CGS, and PDO. "
            "Search by keyword or filter by office. Returns form names, purposes, "
            "deadline rules, and direct links."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword — e.g., 'IAF', 'budget', 'contract', 'data management'.",
                    "default": "",
                },
                "office": {
                    "type": "string",
                    "description": "Filter by office: OSPA, CGS, PDO, or all.",
                    "default": "all",
                },
            },
            "required": [],
        },
    },
}
