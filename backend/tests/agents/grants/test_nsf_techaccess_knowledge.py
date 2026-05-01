"""Structural unit tests for backend/agents/grants/nsf_techaccess_knowledge.py.

These tests assert that the knowledge module's invariants — the ones the
TechAccess tools rely on — are present and correctly shaped. They run
without any LLM, network, or DB dependency.
"""
from __future__ import annotations


# ── SECTION_HEADINGS ────────────────────────────────────────────────────

EXPECTED_SECTION_HEADINGS = {
    "loi_synopsis": "LOI Synopsis",
    "section_1": "Section 1 — Vision and Approach to Responsibilities",
    "section_2": (
        "Section 2 — Organizational Background, Team Expertise, "
        "and Partnership Rationale"
    ),
    "section_3": "Section 3 — Current State of AI Planning and Coordination",
    "section_4": (
        "Section 4 — Work Plan, Milestones, and Performance Metrics"
    ),
    "section_5": (
        "Section 5 — Resource Mobilization and Leveraging Additional Support"
    ),
}


def test_section_headings_exact_strings(knowledge):
    assert knowledge.SECTION_HEADINGS == EXPECTED_SECTION_HEADINGS


def test_section_requirements_cover_every_section(knowledge):
    for key in EXPECTED_SECTION_HEADINGS:
        assert key in knowledge.SECTION_REQUIREMENTS, (
            f"missing required-sub-element list for {key}"
        )
        assert knowledge.SECTION_REQUIREMENTS[key], (
            f"empty required-sub-element list for {key}"
        )


def test_sections_ordering_matches_headings(knowledge):
    assert [s["key"] for s in knowledge.SECTIONS] == [
        "loi_synopsis", "section_1", "section_2",
        "section_3", "section_4", "section_5",
    ]


# ── HUB_RESPONSIBILITIES ────────────────────────────────────────────────

def test_all_five_hub_responsibilities_present(knowledge):
    keys = {r["key"] for r in knowledge.HUB_RESPONSIBILITIES}
    assert keys == {
        "resource_navigator",
        "strategic_plan",
        "deployment_support",
        "training_capacity",
        "sector_coordination",
    }


def test_training_capacity_framing_constraint_says_not_direct_delivery(knowledge):
    training = next(
        r for r in knowledge.HUB_RESPONSIBILITIES
        if r["key"] == "training_capacity"
    )
    constraint_lower = training["framing_constraint"].lower()
    assert "not direct delivery" in constraint_lower or (
        "rather than delivering training directly" in constraint_lower
    )


# ── NSF-Required Metrics ────────────────────────────────────────────────

def test_six_nsf_required_metrics_present(knowledge):
    assert len(knowledge.NSF_REQUIRED_METRICS) == 6
    keys = {m["key"] for m in knowledge.NSF_REQUIRED_METRICS}
    assert keys == {
        "individuals_trained_by_category",
        "small_businesses_and_government_assisted",
        "statewide_convenings_held",
        "national_repository_contributions",
        "deployment_corps_individuals",
        "organizations_provided_technical_assistance",
    }


def test_extended_metric_layers_have_three_categories(knowledge):
    cats = {m["category"] for m in knowledge.EXTENDED_METRIC_LAYERS}
    assert cats == {"reach", "depth", "system_change"}


def test_all_metrics_require_baseline(knowledge):
    for metric in knowledge.ALL_METRICS:
        assert metric["requires_baseline"] is True, metric["key"]


# ── KY_PARTNERS ─────────────────────────────────────────────────────────

def test_every_ky_partner_has_unique_contribution(knowledge):
    for partner in knowledge.KY_PARTNERS:
        assert partner["unique_contribution"].strip(), (
            f"{partner['key']} has empty unique_contribution"
        )


def test_uk_caai_partner_present_with_independent_evaluation(knowledge):
    """G3 from /speckit.analyze: AI research lab must appear and own
    the independent-evaluation role."""
    caai = knowledge.get_partner("uk_caai")
    assert "independent evaluation" in caai["unique_contribution"].lower(), (
        "uk_caai partner must explicitly carry the independent-"
        "evaluation role"
    )


def test_get_partner_raises_keyerror_on_unknown(knowledge):
    import pytest as _pytest
    with _pytest.raises(KeyError):
        knowledge.get_partner("not_a_real_partner")


# ── LOI Rules ──────────────────────────────────────────────────────────

def test_loi_title_prefix_is_exact(knowledge):
    assert knowledge.LOI_RULES["title_prefix"] == "Kentucky Coordination Hub:"


def test_loi_forbidden_acronyms_includes_required_set(knowledge):
    forbidden = set(knowledge.LOI_RULES["forbidden_acronyms"])
    required_subset = {"NSF", "AI", "UK", "KCTCS", "CPE", "COT", "KY",
                       "KDE", "SBDC", "WIOA"}
    assert required_subset.issubset(forbidden)


def test_loi_synopsis_page_limit_is_one(knowledge):
    assert knowledge.LOI_RULES["synopsis_page_limit"] == 1


# ── Supplemental Rules ─────────────────────────────────────────────────

def test_supplemental_rules_allow_loc_dmp_mentoring(knowledge):
    rules = knowledge.SUPPLEMENTAL_RULES
    assert rules["letter_of_collaboration"]["is_allowed"] is True
    assert rules["data_management_plan"]["is_allowed"] is True
    assert rules["mentoring_plan"]["is_allowed"] is True


def test_supplemental_rules_deny_los_and_additional_narrative(knowledge):
    rules = knowledge.SUPPLEMENTAL_RULES
    assert rules["letter_of_support"]["is_allowed"] is False
    assert rules["additional_narrative"]["is_allowed"] is False
    # And carry a refusal_message
    assert rules["letter_of_support"]["refusal_message"]
    assert rules["additional_narrative"]["refusal_message"]


def test_mentoring_plan_carries_postdoc_condition(knowledge):
    mp = knowledge.SUPPLEMENTAL_RULES["mentoring_plan"]
    assert mp["condition"] == "budget_includes_postdocs_or_grad_students"


# ── Opportunity Family ─────────────────────────────────────────────────

def test_opportunity_family_has_three_keys(knowledge):
    keys = {o["key"] for o in knowledge.OPPORTUNITY_FAMILY}
    assert keys == {"hub", "national_lead", "catalyst"}


def test_only_hub_is_primary(knowledge):
    primaries = [o for o in knowledge.OPPORTUNITY_FAMILY if o["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["key"] == "hub"


# ── Deadlines ──────────────────────────────────────────────────────────

def test_deadlines_have_three_canonical_dates(knowledge):
    assert knowledge.DEADLINES["loi"]["date_iso"] == "2026-06-16"
    assert knowledge.DEADLINES["full_proposal"]["date_iso"] == "2026-07-16"
    assert knowledge.DEADLINES["internal"]["date_iso"] == "2026-07-09"


def test_full_proposal_path_mentions_aor(knowledge):
    path = knowledge.DEADLINES["full_proposal"]["submission_path"]
    assert "AOR" in path


# ── Page Budget ────────────────────────────────────────────────────────

def test_page_budget_keys_mirror_sections(knowledge):
    assert set(knowledge.PAGE_BUDGET) == {
        "section_1", "section_2", "section_3", "section_4", "section_5",
    }


def test_page_budget_target_share_sums_to_one(knowledge):
    total = sum(v["target_share"] for v in knowledge.PAGE_BUDGET.values())
    # Floats; allow small rounding window.
    assert 0.99 <= total <= 1.01


# ── AI Literacy Continuum ──────────────────────────────────────────────

def test_three_ai_readiness_levels(knowledge):
    keys = {lvl["key"] for lvl in knowledge.AI_LITERACY_LEVELS}
    assert keys == {"literacy", "proficiency", "fluency"}


# ── Program Officer Topics ─────────────────────────────────────────────

def test_program_officer_topics_have_unresolved_entries(knowledge):
    topics = knowledge.PROGRAM_OFFICER_QUESTION_TOPICS
    assert topics, "must be non-empty"
    unresolved = [t for t in topics if not t["solicitation_resolved"]]
    assert unresolved, "must have at least one unresolved topic"


def test_program_officer_topics_have_resolved_entries_for_filter_test(knowledge):
    topics = knowledge.PROGRAM_OFFICER_QUESTION_TOPICS
    resolved = [t for t in topics if t["solicitation_resolved"]]
    assert resolved, (
        "must have at least one solicitation-resolved topic so the "
        "filter behavior is testable"
    )


# ── Administration Priorities ──────────────────────────────────────────

def test_administration_priority_phrases_match_priorities(knowledge):
    expected = [p["framing_phrase"] for p in knowledge.ADMINISTRATION_PRIORITIES]
    assert knowledge.ADMINISTRATION_PRIORITY_PHRASES == expected


# ── Helper: get_section ────────────────────────────────────────────────

def test_get_section_returns_canonical_entry(knowledge):
    s = knowledge.get_section("section_4")
    assert s["heading"] == knowledge.SECTION_HEADINGS["section_4"]


def test_get_section_raises_on_unknown(knowledge):
    import pytest as _pytest
    with _pytest.raises(KeyError):
        knowledge.get_section("section_99")


# ── Helper: get_hub_responsibilities_for_section ───────────────────────

def test_section_1_gets_all_five_responsibilities(knowledge):
    rs = knowledge.get_hub_responsibilities_for_section("section_1")
    assert len(rs) == 5


# ── Helper: get_framing_rules_for_section ──────────────────────────────

def test_section_5_gets_sustainability_framing_rule(knowledge):
    rules = knowledge.get_framing_rules_for_section("section_5")
    keys = {r["key"] for r in rules}
    assert "sustainability_year_4_plus" in keys
    assert "no_overpromise_innovation_or_econ_dev" in keys
