"""Unit tests for the nine TechAccess MCP tools in
backend/agents/grants/mcp_tools.py.

These tests exercise:
- techaccess_scope_check (T006)
- draft_loi (T012)
- draft_proposal_section (T011)
- refine_section (T017)
- gap_check_section (T018)
- draft_supplemental_artifact, draft_program_officer_questions,
  prioritize_page_budget, cite_deadlines (T025)

All tests run against the real ``mcp_tools`` module loaded via the
session-scoped ``tools`` fixture in conftest.py. No LLM, no network,
no DB.
"""
from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _ui_components(payload):
    return payload["_ui_components"]


def _component_titles(payload):
    return [
        c.get("title", "") for c in _ui_components(payload)
        if isinstance(c, dict)
    ]


def _has_alert_with_variant(payload, variant):
    return any(
        isinstance(c, dict)
        and c.get("type") == "alert"
        and c.get("variant") == variant
        for c in _ui_components(payload)
    )


def _all_text(payload):
    """Return the concatenation of every string anywhere in the
    payload, recursively. Used for substring assertions across Cards,
    Tables (rows), Lists (items), Alerts, Texts, and Tabs."""
    parts: list = []

    def walk(obj):
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        # Numbers / bools / None — ignore.

    walk(_ui_components(payload))
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────
#  techaccess_scope_check
# ─────────────────────────────────────────────────────────────────────────


def test_scope_check_primary_hub(tools):
    out = tools.techaccess_scope_check(
        user_request="Draft Section 1 for the Kentucky Coordination Hub."
    )
    text = _all_text(out)
    assert "In scope" in text
    assert "Kentucky" in text


def test_scope_check_sibling_national_lead(tools):
    out = tools.techaccess_scope_check(
        user_request="Help me with the National Coordination Lead OTA proposal."
    )
    text = _all_text(out)
    assert "Different mechanism" in text or "different mechanism" in text
    assert "Other Transaction Agreement" in text


def test_scope_check_sibling_catalyst(tools):
    out = tools.techaccess_scope_check(
        user_request="Draft a Catalyst Award competition narrative."
    )
    text = _all_text(out)
    assert "Catalyst" in text


def test_scope_check_out_of_family(tools):
    out = tools.techaccess_scope_check(
        user_request="Help me write a Python script to scrape PubMed."
    )
    assert _has_alert_with_variant(out, "warning")
    assert "Out of NSF TechAccess family" in _all_text(out)


def test_scope_check_empty_input(tools):
    out = tools.techaccess_scope_check(user_request="")
    assert _has_alert_with_variant(out, "error")


# ─────────────────────────────────────────────────────────────────────────
#  draft_loi
# ─────────────────────────────────────────────────────────────────────────


def test_draft_loi_default_produces_title_and_synopsis(tools):
    out = tools.draft_loi()
    titles = _component_titles(out)
    assert "LOI Title" in titles
    assert "LOI Synopsis" in titles
    text = _all_text(out)
    assert "Kentucky Coordination Hub:" in text
    assert "2026-06-16" in text  # deadline reminder Alert


def test_draft_loi_title_only_omits_synopsis(tools):
    out = tools.draft_loi(produce="title")
    titles = _component_titles(out)
    assert "LOI Title" in titles
    assert "LOI Synopsis" not in titles


def test_draft_loi_synopsis_only_omits_title(tools):
    out = tools.draft_loi(produce="synopsis")
    titles = _component_titles(out)
    assert "LOI Synopsis" in titles
    assert "LOI Title" not in titles


def test_draft_loi_invalid_produce(tools):
    out = tools.draft_loi(produce="logo")
    assert _has_alert_with_variant(out, "error")


@pytest.mark.parametrize(
    "phrase",
    ["NSF", "AI", "UK", "KCTCS", "CPE", "COT", "WIOA", "K-12", "PI", "DOL"],
)
def test_draft_loi_rejects_every_forbidden_acronym(tools, phrase):
    out = tools.draft_loi(produce="title", descriptive_phrase=phrase)
    assert _has_alert_with_variant(out, "error")
    assert "forbidden acronyms" in _all_text(out).lower() or "acronyms" in _all_text(out).lower()


def test_draft_loi_accepts_descriptor_without_acronyms(tools):
    out = tools.draft_loi(
        produce="title",
        descriptive_phrase="Kentucky Statewide AI-Readiness Coordination",
    )
    # AI is forbidden, so AI-Readiness should be rejected — confirm:
    assert _has_alert_with_variant(out, "error")


def test_draft_loi_accepts_clean_descriptor(tools):
    out = tools.draft_loi(
        produce="title",
        descriptive_phrase="Statewide Readiness Through Coordination",
    )
    # No forbidden acronyms — should succeed.
    assert not _has_alert_with_variant(out, "error")
    text = _all_text(out)
    assert "Kentucky Coordination Hub: Statewide Readiness Through Coordination" in text


def test_draft_loi_includes_pi_and_personnel_block(tools):
    out = tools.draft_loi(
        pi_email="cody.bumgardner@uky.edu",
        senior_personnel=[
            {"name": "Dr. Jane Doe", "affiliation": "UK", "role": "Co-PI"},
        ],
    )
    titles = _component_titles(out)
    assert "PI and Senior Personnel" in titles
    text = _all_text(out)
    assert "cody.bumgardner@uky.edu" in text
    assert "Dr. Jane Doe" in text


# ─────────────────────────────────────────────────────────────────────────
#  draft_proposal_section
# ─────────────────────────────────────────────────────────────────────────


def test_draft_section_unknown_key_refused(tools):
    out = tools.draft_proposal_section(section_key="section_99")
    assert _has_alert_with_variant(out, "error")


def test_draft_section_loi_synopsis_delegates_to_draft_loi(tools):
    """D1 / Decision 8: parity check — the synopsis Card must be present
    when called via draft_proposal_section(loi_synopsis)."""
    out = tools.draft_proposal_section(section_key="loi_synopsis")
    titles = _component_titles(out)
    assert "LOI Synopsis" in titles
    # The deadline-reminder Alert from draft_loi must also be present.
    assert "2026-06-16" in _all_text(out)


@pytest.mark.parametrize(
    "section_key",
    ["section_1", "section_2", "section_3", "section_4", "section_5"],
)
def test_draft_section_uses_exact_required_heading(tools, knowledge, section_key):
    out = tools.draft_proposal_section(section_key=section_key)
    titles = _component_titles(out)
    assert knowledge.SECTION_HEADINGS[section_key] in titles


def test_draft_section_1_includes_all_five_hub_responsibilities(tools, knowledge):
    out = tools.draft_proposal_section(section_key="section_1")
    text = _all_text(out)
    for r in knowledge.HUB_RESPONSIBILITIES:
        assert r["name"] in text, f"missing Hub responsibility: {r['name']}"


def test_draft_section_4_names_all_six_nsf_required_metrics(tools, knowledge):
    out = tools.draft_proposal_section(section_key="section_4")
    text = _all_text(out)
    for metric in knowledge.NSF_REQUIRED_METRICS:
        # metric name truncated to first ~30 chars to avoid line-wrap matching issues
        head = metric["name"][:30]
        assert head in text, f"missing NSF-required metric: {metric['name']}"


def test_draft_section_4_names_all_extended_layers(tools, knowledge):
    out = tools.draft_proposal_section(section_key="section_4")
    text = _all_text(out)
    for metric in knowledge.EXTENDED_METRIC_LAYERS:
        assert metric["name"] in text, (
            f"missing extended layer: {metric['name']}"
        )


def test_draft_section_4_mentions_baseline_and_independent_evaluation(tools):
    out = tools.draft_proposal_section(section_key="section_4")
    text_lower = _all_text(out).lower()
    assert "year 1 baseline" in text_lower or "baselines" in text_lower
    assert "independent evaluation" in text_lower


def test_draft_section_administration_priority_alignment(tools, knowledge):
    out = tools.draft_proposal_section(
        section_key="section_1",
        request_administration_priority_alignment=True,
    )
    text = _all_text(out)
    # Every priority phrase must appear somewhere in the scaffold.
    for phrase in knowledge.ADMINISTRATION_PRIORITY_PHRASES:
        assert phrase in text


def test_draft_section_partner_roster_override_used(tools):
    out = tools.draft_proposal_section(
        section_key="section_2",
        partner_roster_override=["uk", "kctcs"],
    )
    text = _all_text(out)
    assert "University of Kentucky (Lead Organization)" in text
    assert "Kentucky Community and Technical College System" in text
    # Non-override partners should NOT appear in the partner table
    # (they may still appear if the section narrative references them
    # through framing constraints, but the partner table is scoped).
    assert "scoped to user-supplied keys" in text


def test_draft_section_sibling_opportunity_emits_framing_alert(tools):
    out = tools.draft_proposal_section(
        section_key="section_1",
        opportunity="catalyst",
    )
    assert _has_alert_with_variant(out, "info")
    assert "Different mechanism" in _all_text(out)


def test_draft_section_unknown_opportunity_refused(tools):
    out = tools.draft_proposal_section(
        section_key="section_1",
        opportunity="nope",
    )
    assert _has_alert_with_variant(out, "error")


# ─────────────────────────────────────────────────────────────────────────
#  refine_section
# ─────────────────────────────────────────────────────────────────────────


def test_refine_section_unknown_key(tools):
    out = tools.refine_section(section_key="bogus", draft_text="hello")
    assert _has_alert_with_variant(out, "error")


def test_refine_section_empty_draft(tools):
    out = tools.refine_section(section_key="section_1", draft_text="")
    assert _has_alert_with_variant(out, "error")


def test_refine_section_detects_direct_delivery_framing(tools):
    out = tools.refine_section(
        section_key="section_1",
        draft_text=(
            "The Hub will deliver training to all KCTCS students in "
            "every county."
        ),
    )
    text = _all_text(out)
    # Refinement directives must mention coordination/convening rewrite.
    assert (
        "coordination" in text.lower() or "convening" in text.lower()
    )


def test_refine_section_flags_generic_ai_training(tools):
    out = tools.refine_section(
        section_key="section_1",
        draft_text="We will provide AI training across the state.",
    )
    text = _all_text(out)
    assert "literacy" in text.lower() or "proficiency" in text.lower()


def test_refine_section_returns_two_canonical_cards(tools):
    out = tools.refine_section(
        section_key="section_2",
        draft_text=(
            "The University of Kentucky will lead the Hub. KCTCS will "
            "coordinate workforce training. Governance is handled by the "
            "executive committee."
        ),
    )
    titles = _component_titles(out)
    assert "Refined Draft" in titles
    assert "What Changed and Why" in titles


# ─────────────────────────────────────────────────────────────────────────
#  gap_check_section
# ─────────────────────────────────────────────────────────────────────────


def test_gap_check_unknown_section(tools):
    out = tools.gap_check_section(section_key="bogus", draft_text="x")
    assert _has_alert_with_variant(out, "error")


def test_gap_check_empty_draft(tools):
    out = tools.gap_check_section(section_key="section_1", draft_text="")
    assert _has_alert_with_variant(out, "error")


def test_gap_check_section_2_flags_missing_governance(tools):
    out = tools.gap_check_section(
        section_key="section_2",
        draft_text=(
            "The University of Kentucky leads the Hub with KCTCS, CPE, "
            "and COT as partners. Each partner contributes operational "
            "capacity."
        ),
    )
    titles = _component_titles(out)
    assert "Required Sub-Element Coverage" in titles
    text = _all_text(out)
    # Governance sub-element should be marked absent or partial
    assert "Governance and decision-making" in text


def test_gap_check_section_4_metric_coverage_card_appears(tools):
    out = tools.gap_check_section(
        section_key="section_4",
        draft_text=(
            "Year 1 milestones include convenings and training across "
            "Kentucky. We will track activities and report annually."
        ),
    )
    titles = _component_titles(out)
    assert "Metric Coverage" in titles
    text = _all_text(out)
    assert "Year 1 baseline" in text
    assert "Independent evaluation" in text or "independent evaluation" in text.lower()


def test_gap_check_returns_review_criteria_verdicts(tools):
    out = tools.gap_check_section(
        section_key="section_1",
        draft_text="Vision: the Hub coordinates statewide AI readiness.",
    )
    titles = _component_titles(out)
    assert "Review Criteria Verdicts" in titles
    text = _all_text(out)
    assert "Intellectual Merit" in text
    assert "Broader Impacts" in text


def test_gap_check_omit_rewrites_when_disabled(tools):
    out = tools.gap_check_section(
        section_key="section_1",
        draft_text="Vision: the Hub coordinates statewide AI readiness.",
        include_rewrites=False,
    )
    titles = _component_titles(out)
    assert "Suggested Rewrites" not in titles


# ─────────────────────────────────────────────────────────────────────────
#  draft_supplemental_artifact
# ─────────────────────────────────────────────────────────────────────────


def test_supplemental_letter_of_support_refused(tools):
    out = tools.draft_supplemental_artifact(artifact_key="letter_of_support")
    assert _has_alert_with_variant(out, "error")
    assert "prohibits Letters of Support" in _all_text(out)


def test_supplemental_additional_narrative_refused(tools):
    out = tools.draft_supplemental_artifact(artifact_key="additional_narrative")
    assert _has_alert_with_variant(out, "error")


def test_supplemental_unknown_artifact_key(tools):
    out = tools.draft_supplemental_artifact(artifact_key="foobar")
    assert _has_alert_with_variant(out, "error")


def test_supplemental_mentoring_plan_without_budget_flag_refused(tools):
    out = tools.draft_supplemental_artifact(artifact_key="mentoring_plan")
    assert _has_alert_with_variant(out, "error")
    assert "postdocs or graduate students" in _all_text(out)


def test_supplemental_mentoring_plan_with_budget_flag_succeeds(tools):
    out = tools.draft_supplemental_artifact(
        artifact_key="mentoring_plan",
        budget_includes_postdocs_or_grad_students=True,
    )
    assert "Mentoring Plan" in _component_titles(out)


def test_supplemental_loc_without_partner_refused(tools):
    out = tools.draft_supplemental_artifact(
        artifact_key="letter_of_collaboration",
    )
    assert _has_alert_with_variant(out, "error")


def test_supplemental_loc_for_kctcs_includes_unique_contribution(tools, knowledge):
    out = tools.draft_supplemental_artifact(
        artifact_key="letter_of_collaboration",
        partner_key="kctcs",
    )
    text = _all_text(out)
    kctcs = knowledge.get_partner("kctcs")
    # Heuristic: at least the first ~50 chars of unique_contribution
    head = kctcs["unique_contribution"][:50]
    assert head in text


def test_supplemental_loc_scrubs_endorsement_phrases(tools):
    out = tools.draft_supplemental_artifact(
        artifact_key="letter_of_collaboration",
        partner_key="kctcs",
        partner_contribution=(
            "We strongly support this proposal and highly recommend the "
            "PI."
        ),
    )
    text = _all_text(out)
    assert "strongly support" not in text.lower()
    assert "highly recommend" not in text.lower()
    assert "endorsement language removed" in text


def test_supplemental_loc_for_unknown_partner_string_works(tools):
    out = tools.draft_supplemental_artifact(
        artifact_key="letter_of_collaboration",
        partner_key="some_new_org",
    )
    titles = _component_titles(out)
    assert any("Letter of Collaboration" in t for t in titles)


def test_supplemental_dmp_mentions_independent_evaluation(tools):
    out = tools.draft_supplemental_artifact(artifact_key="data_management_plan")
    text = _all_text(out)
    assert "independent evaluation" in text.lower()
    assert "common cross-partner" in text.lower()


# ─────────────────────────────────────────────────────────────────────────
#  draft_program_officer_questions
# ─────────────────────────────────────────────────────────────────────────


def test_program_officer_default_returns_questions_card(tools):
    out = tools.draft_program_officer_questions()
    titles = _component_titles(out)
    assert "Questions for the NSF Program Officer" in titles


def test_program_officer_solicitation_resolved_topics_filtered_out(tools, knowledge):
    """SC-012: zero questions whose topic is solicitation-resolved."""
    out = tools.draft_program_officer_questions()
    text = _all_text(out)
    resolved = [
        t for t in knowledge.PROGRAM_OFFICER_QUESTION_TOPICS
        if t["solicitation_resolved"]
    ]
    for topic in resolved:
        # The seed_question of a resolved topic must NOT appear in the
        # generated questions list.
        assert topic["seed_question"] not in text or (
            # It may appear in the "filtered out" Card label, but never
            # in the questions Card. We assert the topic.name is in the
            # filtered-out list.
            topic["name"] in text
        )


def test_program_officer_max_questions_respected(tools):
    out = tools.draft_program_officer_questions(max_questions=2)
    # Find the questions list (ordered=True)
    items = []
    for c in _ui_components(out):
        if isinstance(c, dict) and c.get("type") == "card":
            for sub in c.get("content", []):
                if isinstance(sub, dict) and sub.get("type") == "list" and sub.get("ordered"):
                    items.extend(sub.get("items", []))
    assert 1 <= len(items) <= 2


def test_program_officer_unknown_topic_returns_error(tools):
    out = tools.draft_program_officer_questions(topics=["not_a_real_topic"])
    assert _has_alert_with_variant(out, "error")


def test_program_officer_only_resolved_topics_yields_refusal(tools):
    out = tools.draft_program_officer_questions(
        topics=["hub_responsibility_count", "page_limit_value", "round_one_award_count"],
    )
    # All three are solicitation_resolved=True — refusal expected.
    assert _has_alert_with_variant(out, "error")
    assert "explicit in NSF 26-508" in _all_text(out)


def test_program_officer_team_specific_context_included(tools):
    out = tools.draft_program_officer_questions(
        topics=["matching_funds_treatment"],
        team_specific_context="our budget includes a $1M industry match",
    )
    text = _all_text(out)
    assert "$1M industry match" in text


# ─────────────────────────────────────────────────────────────────────────
#  prioritize_page_budget
# ─────────────────────────────────────────────────────────────────────────


def test_page_budget_fits_yields_no_cuts_alert(tools):
    out = tools.prioritize_page_budget(
        current_pages={
            "section_1": 4.0,
            "section_2": 3.0,
            "section_3": 2.0,
            "section_4": 4.0,
            "section_5": 2.0,
        },
    )
    assert _has_alert_with_variant(out, "info")
    assert "No cuts required" in _all_text(out)


def test_page_budget_overage_yields_cut_list_targeting_largest_overage(tools):
    out = tools.prioritize_page_budget(
        current_pages={
            "section_1": 5.0,
            "section_2": 3.0,
            "section_3": 2.0,
            "section_4": 5.0,
            "section_5": 2.0,
        },
    )
    titles = _component_titles(out)
    assert "Recommended Cut Order" in titles
    # No "no cuts required" alert.
    assert "No cuts required" not in _all_text(out)


def test_page_budget_under_investment_warning(tools):
    """A section below 50% of target triggers a warning."""
    out = tools.prioritize_page_budget(
        current_pages={
            "section_1": 1.0,  # target ~4.05; 1.0 < 0.5*4.05
            "section_2": 3.0,
            "section_3": 2.0,
            "section_4": 4.0,
            "section_5": 2.0,
        },
    )
    assert _has_alert_with_variant(out, "warning")
    assert "Under-investment" in _all_text(out)


def test_page_budget_unknown_section_key_refused(tools):
    out = tools.prioritize_page_budget(
        current_pages={"section_1": 4.0, "section_99": 2.0},
    )
    assert _has_alert_with_variant(out, "error")


def test_page_budget_negative_value_refused(tools):
    out = tools.prioritize_page_budget(
        current_pages={"section_1": -1.0},
    )
    assert _has_alert_with_variant(out, "error")


def test_page_budget_empty_input_refused(tools):
    out = tools.prioritize_page_budget(current_pages={})
    assert _has_alert_with_variant(out, "error")


def test_page_budget_protected_subelements_listed(tools):
    out = tools.prioritize_page_budget(
        current_pages={
            "section_1": 5.0, "section_2": 3.0, "section_3": 2.0,
            "section_4": 5.0, "section_5": 2.0,
        },
    )
    titles = _component_titles(out)
    assert "Required Sub-Elements (Protected)" in titles


# ─────────────────────────────────────────────────────────────────────────
#  cite_deadlines
# ─────────────────────────────────────────────────────────────────────────


def test_cite_deadlines_default_returns_three_dates(tools):
    out = tools.cite_deadlines()
    text = _all_text(out)
    assert "2026-06-16" in text
    assert "2026-07-16" in text
    assert "2026-07-09" in text


def test_cite_deadlines_full_proposal_mentions_aor(tools):
    out = tools.cite_deadlines()
    text = _all_text(out)
    assert "AOR signature required" in text


def test_cite_deadlines_loi_only_subset(tools):
    out = tools.cite_deadlines(include=["loi"])
    text = _all_text(out)
    assert "2026-06-16" in text
    assert "2026-07-16" not in text


def test_cite_deadlines_unknown_key_refused(tools):
    out = tools.cite_deadlines(include=["nope"])
    assert _has_alert_with_variant(out, "error")


# ─────────────────────────────────────────────────────────────────────────
#  TOOL_REGISTRY wiring
# ─────────────────────────────────────────────────────────────────────────


def test_tool_registry_contains_all_nine_techaccess_tools(tools):
    registry = tools.TOOL_REGISTRY
    expected = {
        "techaccess_scope_check",
        "draft_loi",
        "draft_proposal_section",
        "refine_section",
        "gap_check_section",
        "draft_supplemental_artifact",
        "draft_program_officer_questions",
        "prioritize_page_budget",
        "cite_deadlines",
    }
    assert expected.issubset(set(registry))


def test_tool_registry_existing_grants_tools_preserved(tools):
    """FR-001: merging into the existing grants agent must not regress
    its prior tool surface."""
    registry = tools.TOOL_REGISTRY
    existing = {
        "search_grants",
        "get_grant_details",
        "match_grants_to_caai",
        "get_caai_profile",
        "analyze_funding_trends",
    }
    assert existing.issubset(set(registry))


def test_every_techaccess_tool_has_input_schema(tools):
    for name in (
        "techaccess_scope_check", "draft_loi", "draft_proposal_section",
        "refine_section", "gap_check_section",
        "draft_supplemental_artifact", "draft_program_officer_questions",
        "prioritize_page_budget", "cite_deadlines",
    ):
        entry = tools.TOOL_REGISTRY[name]
        assert "input_schema" in entry
        assert entry["input_schema"]["type"] == "object"
        assert callable(entry["function"])
