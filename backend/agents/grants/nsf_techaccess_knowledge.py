#!/usr/bin/env python3
"""NSF TechAccess: AI-Ready America (NSF 26-508) knowledge base.

Encodes the solicitation rules, exact required section headings, the five
Hub responsibilities, NSF-required performance metrics, the AI literacy
continuum, the Kentucky partnership architecture, supplemental-material
allow/deny rules, and Administration-priority phrases for the
TechAccess specialization of the ``grants`` agent.

This module is pure-data: every export is a module-level ``dict`` or
``list`` of dicts. It mirrors the ``caai_knowledge`` module's shape so
that future maintainers see the same pattern twice.

The TechAccess scope spans the full NSF 26-508 family — the State /
Territory Coordination Hub (the Kentucky Coordination Hub proposal that
is the primary use case), the National Coordination Lead (selected
separately via Other Transaction Agreement), and the AI-Ready Catalyst
Award Competitions (announced separately).
"""
from __future__ import annotations

from typing import Any, Dict, List


# ── Solicitation Metadata ───────────────────────────────────────────────

SOLICITATION_META: Dict[str, Any] = {
    "id": "NSF 26-508",
    "name": "TechAccess: AI-Ready America",
    "subtitle": "State/Territory Coordination Hub",
    "loi_due": "2026-06-16",
    "full_proposal_due": "2026-07-16",
    "internal_deadline": "2026-07-09",
    "narrative_page_limit": 15,
    "loi_synopsis_page_limit": 1,
    "award_size_per_year": 1_000_000,
    "award_years": 3,
    "possible_extension_year": 4,
    "max_awards": 56,
    "rounds": 3,
    "round_1_awards": 10,
    "round_2_awards": 20,
    "funders": [
        "NSF TIP",
        "NSF CISE",
        "NSF EDU",
        "USDA-NIFA",
        "Department of Labor",
        "Small Business Administration",
    ],
}


# ── Opportunity Family (Clarifications Q4) ──────────────────────────────

OPPORTUNITY_FAMILY: List[Dict[str, Any]] = [
    {
        "key": "hub",
        "name": "State/Territory Coordination Hub",
        "mechanism": "Cooperative Agreement",
        "is_primary": True,
        "framing_notes": (
            "Primary scope. The Kentucky Coordination Hub proposal. "
            "Cooperative-agreement mechanism, $1M/year for 3 years "
            "(possible 4th), one award per state/DC/territory."
        ),
    },
    {
        "key": "national_lead",
        "name": "National Coordination Lead",
        "mechanism": "Other Transaction Agreement",
        "is_primary": False,
        "framing_notes": (
            "Sibling opportunity, different mechanism (Other Transaction "
            "Agreement). Selected separately. Different rules, different "
            "deadlines. Do not reuse Hub-specific language verbatim — "
            "ask the user which opportunity they are drafting for."
        ),
    },
    {
        "key": "catalyst",
        "name": "AI-Ready Catalyst Award Competitions",
        "mechanism": "Award Competition",
        "is_primary": False,
        "framing_notes": (
            "Sibling opportunity, announced separately. Different rules, "
            "different deadlines. Do not reuse Hub-specific language "
            "verbatim — ask the user which opportunity they are drafting "
            "for."
        ),
    },
]


# ── Required Section Headings (exact strings — non-negotiable) ──────────

SECTION_HEADINGS: Dict[str, str] = {
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


# ── Required sub-elements per section (FR-003) ──────────────────────────

SECTION_REQUIREMENTS: Dict[str, List[str]] = {
    "loi_synopsis": [
        "Compressed Section 1 content (vision, approach, all five Hub responsibilities)",
        "Compressed Section 2 content (lead organization, partners, governance)",
        "Working title beginning 'Kentucky Coordination Hub:'",
        "Identification of PI, co-PIs, senior personnel, sub-awardees",
        "List of all participating organizations and community partners",
    ],
    "section_1": [
        "How the Hub executes all five Hub responsibilities",
        "Strategies for statewide coordination and scaling",
        "Evidence of prior experience with similar statewide / multi-sector initiatives",
        "Strategies for supporting small-scale local pilots",
    ],
    "section_2": [
        "Lead organization's statewide convening power and operational capacity",
        "Team qualifications and roles",
        "Partnership rationale — why each partner was selected and what they uniquely contribute",
        "Governance and decision-making structure",
        "Advisory Board",
        "Known partnership gaps and plans to fill them",
    ],
    "section_3": [
        "Existing Kentucky AI readiness efforts and stakeholders",
        "What is working and where gaps exist",
        "How the Hub accelerates progress beyond what is already happening",
    ],
    "section_4": [
        "Major milestones and timelines for each Hub responsibility area",
        "Performance metrics for national dashboards",
        "Data collection and reporting mechanisms",
        "All NSF-required performance metrics by name",
        "Reach, depth, and system-change metric layers",
        "Year 1 baseline statement",
        "Common cross-partner data-collection instrument",
        "Independent evaluation component",
    ],
    "section_5": [
        "Plans for additional financial support from industry, philanthropy, state agencies",
        "Plans for additional in-kind support",
        "How additional resources expand reach",
        "How additional resources enable self-sustainment beyond NSF funding",
    ],
}


# ── Section ordering / page-budget metadata ─────────────────────────────

SECTIONS: List[Dict[str, Any]] = [
    {
        "key": "loi_synopsis",
        "heading": SECTION_HEADINGS["loi_synopsis"],
        "required_subelements": SECTION_REQUIREMENTS["loi_synopsis"],
        "target_page_share": 0.0,  # LOI synopsis is outside the 15-page limit
        "applies_to_loi": True,
    },
    {
        "key": "section_1",
        "heading": SECTION_HEADINGS["section_1"],
        "required_subelements": SECTION_REQUIREMENTS["section_1"],
        "target_page_share": 0.27,  # ~4 pages
        "applies_to_loi": False,
    },
    {
        "key": "section_2",
        "heading": SECTION_HEADINGS["section_2"],
        "required_subelements": SECTION_REQUIREMENTS["section_2"],
        "target_page_share": 0.20,  # ~3 pages
        "applies_to_loi": False,
    },
    {
        "key": "section_3",
        "heading": SECTION_HEADINGS["section_3"],
        "required_subelements": SECTION_REQUIREMENTS["section_3"],
        "target_page_share": 0.13,  # ~2 pages
        "applies_to_loi": False,
    },
    {
        "key": "section_4",
        "heading": SECTION_HEADINGS["section_4"],
        "required_subelements": SECTION_REQUIREMENTS["section_4"],
        "target_page_share": 0.27,  # ~4 pages
        "applies_to_loi": False,
    },
    {
        "key": "section_5",
        "heading": SECTION_HEADINGS["section_5"],
        "required_subelements": SECTION_REQUIREMENTS["section_5"],
        "target_page_share": 0.13,  # ~2 pages
        "applies_to_loi": False,
    },
]


# ── Hub Responsibilities (FR-004) ───────────────────────────────────────

HUB_RESPONSIBILITIES: List[Dict[str, Any]] = [
    {
        "key": "resource_navigator",
        "name": "AI Learning and Resource Navigator",
        "framing_constraint": (
            "Build a publicly accessible inventory of Kentucky AI resources "
            "(training programs, infrastructure, support services). The Hub "
            "curates and connects; it does not deliver the underlying "
            "services."
        ),
        "cross_section_relevance": ["section_1", "section_4"],
    },
    {
        "key": "strategic_plan",
        "name": "State/Territory AI Readiness Strategic Plan",
        "framing_constraint": (
            "Lead a collaborative strategic plan with data collection and "
            "evaluation built in. Convene stakeholders; do not author the "
            "plan in isolation."
        ),
        "cross_section_relevance": ["section_1", "section_3", "section_4"],
    },
    {
        "key": "deployment_support",
        "name": "AI Deployment Support",
        "framing_constraint": (
            "Provide hands-on assistance for AI adoption by local "
            "governments, small businesses, and organizations. May include "
            "an AI Deployment Corps of credentialed practitioners. The "
            "Corps is a Hub-coordinated network — credentialing relies on "
            "existing programs."
        ),
        "cross_section_relevance": ["section_1", "section_4"],
    },
    {
        "key": "training_capacity",
        "name": "AI Readiness Training and Capacity Building",
        "framing_constraint": (
            "Backbone coordination of K-16 and workforce training systems "
            "— NOT direct delivery. Align with the DOL AI Literacy "
            "Framework, WIOA, and Perkins V. Include micro-credentials, "
            "badges, and experiential learning. The phrase 'rather than "
            "delivering training directly' is the load-bearing constraint."
        ),
        "cross_section_relevance": ["section_1", "section_4"],
    },
    {
        "key": "sector_coordination",
        "name": "Coordination Within Priority Sectors",
        "framing_constraint": (
            "Convene stakeholders in sectors critical to Kentucky's "
            "economy (healthcare, agriculture, manufacturing, energy, "
            "education). Complement, don't duplicate, existing "
            "coordination."
        ),
        "cross_section_relevance": ["section_1", "section_4"],
    },
]


# ── NSF-Required Performance Metrics (FR-007) ───────────────────────────

NSF_REQUIRED_METRICS: List[Dict[str, Any]] = [
    {
        "key": "individuals_trained_by_category",
        "name": "Number of individuals trained, by category",
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Report by category — educators, workforce, small business owners.",
    },
    {
        "key": "small_businesses_and_government_assisted",
        "name": (
            "Number of small businesses and government entities "
            "assisted; hours or dollars saved through AI adoption"
        ),
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Both the count and the savings figure must be reported.",
    },
    {
        "key": "statewide_convenings_held",
        "name": (
            "Number of statewide convenings held and guidance facilitated"
        ),
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Distinguish convenings from one-off meetings.",
    },
    {
        "key": "national_repository_contributions",
        "name": (
            "Contributions to national best-practice repositories and "
            "sector coordination activities"
        ),
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Track artifacts contributed and uptake by other Hubs.",
    },
    {
        "key": "deployment_corps_individuals",
        "name": (
            "Number of individuals trained for the AI Deployment Corps "
            "and actively providing assistance"
        ),
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Both 'trained' and 'actively providing' counts required.",
    },
    {
        "key": "organizations_provided_technical_assistance",
        "name": (
            "Number of organizations provided technical assistance"
        ),
        "category": "nsf_required",
        "requires_baseline": True,
        "notes": "Distinct from individuals trained — count organizations.",
    },
]


# ── Extended Metric Layers (FR-008) ─────────────────────────────────────

EXTENDED_METRIC_LAYERS: List[Dict[str, Any]] = [
    {
        "key": "reach_sector",
        "name": "Reach by sector",
        "category": "reach",
        "requires_baseline": True,
        "notes": "Healthcare, agriculture, advanced manufacturing, energy, education.",
    },
    {
        "key": "reach_geography",
        "name": "Reach by geography",
        "category": "reach",
        "requires_baseline": True,
        "notes": "County-level rollup; explicit eastern Kentucky reporting.",
    },
    {
        "key": "reach_demographics",
        "name": "Reach by demographics",
        "category": "reach",
        "requires_baseline": True,
        "notes": (
            "First-generation / adult learners, minority-owned small "
            "businesses, underserved school districts."
        ),
    },
    {
        "key": "reach_prior_ai_exposure",
        "name": "Reach by prior AI exposure",
        "category": "reach",
        "requires_baseline": True,
        "notes": "Stratify outcomes against starting AI-readiness level.",
    },
    {
        "key": "depth_pre_post_literacy",
        "name": "Pre/post AI-literacy assessments",
        "category": "depth",
        "requires_baseline": True,
        "notes": (
            "Common instrument across partners; map to "
            "literacy → proficiency → fluency."
        ),
    },
    {
        "key": "depth_credentials",
        "name": "Credential completions",
        "category": "depth",
        "requires_baseline": True,
        "notes": "Micro-credentials, badges, certifications.",
    },
    {
        "key": "depth_tool_adoption",
        "name": "AI tool adoption rates",
        "category": "depth",
        "requires_baseline": True,
        "notes": "Track adoption among assisted businesses and government entities.",
    },
    {
        "key": "depth_business_roi",
        "name": "ROI for assisted businesses",
        "category": "depth",
        "requires_baseline": True,
        "notes": "Hours or dollars saved attributable to AI adoption.",
    },
    {
        "key": "system_partnerships",
        "name": "New partnerships formed",
        "category": "system_change",
        "requires_baseline": True,
        "notes": "Cross-sector and cross-institution.",
    },
    {
        "key": "system_curriculum",
        "name": "Curriculum changes adopted",
        "category": "system_change",
        "requires_baseline": True,
        "notes": "K-16 and workforce-training curricula.",
    },
    {
        "key": "system_policy",
        "name": "Policy changes influenced",
        "category": "system_change",
        "requires_baseline": True,
        "notes": "State agency policy, district policy, board-of-trustees actions.",
    },
    {
        "key": "system_leveraged_funding",
        "name": "Leveraged funding secured",
        "category": "system_change",
        "requires_baseline": True,
        "notes": "Industry, philanthropy, state agencies, federal pass-through.",
    },
]

ALL_METRICS: List[Dict[str, Any]] = NSF_REQUIRED_METRICS + EXTENDED_METRIC_LAYERS


# ── Kentucky Partner Architecture (FR-009 + G3 from /speckit.analyze) ───

KY_PARTNERS: List[Dict[str, Any]] = [
    {
        "key": "uk_caai",
        "name": "University of Kentucky Center for Applied AI (CAAI)",
        "unique_contribution": (
            "AI research lab providing technical credibility, evaluation "
            "methodology, and research-to-practice translation. Serves as "
            "the Hub's independent evaluation component, designing the "
            "common cross-partner data-collection instrument and the pre/"
            "post AI-literacy assessment."
        ),
        "trusted_messenger_for": ["first_gen_adult"],
        "priority_sectors": ["healthcare", "agriculture", "education"],
    },
    {
        "key": "uk",
        "name": "University of Kentucky (Lead Organization)",
        "unique_contribution": (
            "Land-grant institution with statewide reach via Cooperative "
            "Extension. Lead applicant; provides operational backbone, "
            "fiscal management, and statewide convening authority."
        ),
        "trusted_messenger_for": ["rural_urban", "agricultural"],
        "priority_sectors": [
            "healthcare", "agriculture", "advanced_manufacturing",
            "energy", "education",
        ],
    },
    {
        "key": "cooperative_extension",
        "name": "UK Cooperative Extension Service",
        "unique_contribution": (
            "Statewide trusted-messenger network with offices in every "
            "Kentucky county. Reaches rural and agricultural communities "
            "that no other partner can reach at the same density."
        ),
        "trusted_messenger_for": [
            "rural_urban", "eastern_ky", "agricultural",
        ],
        "priority_sectors": ["agriculture"],
    },
    {
        "key": "kctcs",
        "name": "Kentucky Community and Technical College System (KCTCS)",
        "unique_contribution": (
            "16 colleges reaching all 120 Kentucky counties. The workforce-"
            "training spine for the Hub: micro-credentials, badges, dual-"
            "enrollment with K-12, and adult-learner pathways."
        ),
        "trusted_messenger_for": [
            "rural_urban", "first_gen_adult", "underserved_districts",
        ],
        "priority_sectors": [
            "advanced_manufacturing", "healthcare", "education",
        ],
    },
    {
        "key": "cpe",
        "name": "Kentucky Council on Postsecondary Education (CPE)",
        "unique_contribution": (
            "Statutory coordination role across all public postsecondary "
            "institutions. Provides policy levers for credential alignment, "
            "transfer pathways, and KCTCS coordination."
        ),
        "trusted_messenger_for": ["first_gen_adult"],
        "priority_sectors": ["education"],
    },
    {
        "key": "cot",
        "name": "Kentucky Governor's Office of Technology (COT)",
        "unique_contribution": (
            "Cross-agency relationships enabling state-government AI "
            "adoption. Convenes other cabinets and provides the "
            "government-AI-deployment use cases for the AI Deployment "
            "Corps."
        ),
        "trusted_messenger_for": [],
        "priority_sectors": ["energy", "education"],
    },
    {
        "key": "kced",
        "name": "Kentucky Cabinet for Economic Development",
        "unique_contribution": (
            "Industry and employer relationships, particularly with "
            "manufacturers and energy-sector firms. Provides the "
            "private-sector convening surface for sector coordination."
        ),
        "trusted_messenger_for": ["minority_owned_smb"],
        "priority_sectors": [
            "advanced_manufacturing", "energy",
        ],
    },
    {
        "key": "kentuckianaworks",
        "name": "KentuckianaWorks (regional workforce boards)",
        "unique_contribution": (
            "Department of Labor connection through American Job Centers; "
            "the WIOA-aligned workforce-system entry point. Reaches "
            "incumbent workers and dislocated workers Hub-wide."
        ),
        "trusted_messenger_for": [
            "first_gen_adult", "minority_owned_smb",
        ],
        "priority_sectors": ["advanced_manufacturing"],
    },
    {
        "key": "ky_sbdc",
        "name": "Kentucky Small Business Development Center (SBDC) Network",
        "unique_contribution": (
            "Statewide network reaching Kentucky small businesses, "
            "including minority-owned firms. Channel for small-business "
            "AI-deployment assistance and for measuring the 'small "
            "businesses assisted / hours-or-dollars saved' metric."
        ),
        "trusted_messenger_for": ["minority_owned_smb"],
        "priority_sectors": [
            "advanced_manufacturing", "agriculture",
        ],
    },
    {
        "key": "kde",
        "name": "Kentucky Department of Education (KDE)",
        "unique_contribution": (
            "K-12 pipeline and educator professional development. "
            "Channel for integrating AI literacy into K-12 curricula and "
            "for reaching underserved school districts."
        ),
        "trusted_messenger_for": ["underserved_districts"],
        "priority_sectors": ["education"],
    },
]


# ── Kentucky Priority Sectors (FR-009) ──────────────────────────────────

KY_PRIORITY_SECTORS: List[Dict[str, Any]] = [
    {
        "key": "healthcare",
        "name": "Healthcare",
        "notes": (
            "Largest employer in many rural counties; clinical AI use "
            "cases anchored at UK HealthCare and regional hospital "
            "systems."
        ),
    },
    {
        "key": "agriculture",
        "name": "Agriculture",
        "notes": (
            "Land-grant strength via Cooperative Extension; precision-"
            "agriculture and ag-AI use cases reach rural Kentucky."
        ),
    },
    {
        "key": "advanced_manufacturing",
        "name": "Advanced Manufacturing",
        "notes": (
            "Auto, aerospace, and chemical manufacturing concentrated "
            "around the Bluegrass and Western Kentucky."
        ),
    },
    {
        "key": "energy",
        "name": "Energy",
        "notes": (
            "Coal-region transition and grid-modernization use cases "
            "in eastern Kentucky."
        ),
    },
    {
        "key": "education",
        "name": "Education",
        "notes": (
            "K-16 + workforce-training pipeline; KCTCS and KDE are the "
            "primary channels."
        ),
    },
]


# ── Equity Lenses (FR-010) ──────────────────────────────────────────────

KY_EQUITY_LENSES: List[Dict[str, Any]] = [
    {
        "key": "rural_urban",
        "name": "Rural vs. urban access gaps",
        "connected_partners": ["uk", "cooperative_extension", "kctcs"],
    },
    {
        "key": "eastern_ky",
        "name": "Eastern Kentucky (Appalachia)",
        "connected_partners": ["cooperative_extension", "kctcs"],
    },
    {
        "key": "first_gen_adult",
        "name": "First-generation and adult learners",
        "connected_partners": ["kctcs", "cpe", "kentuckianaworks"],
    },
    {
        "key": "minority_owned_smb",
        "name": "Minority-owned small businesses",
        "connected_partners": ["ky_sbdc", "kced", "kentuckianaworks"],
    },
    {
        "key": "underserved_districts",
        "name": "Underserved school districts",
        "connected_partners": ["kde", "kctcs"],
    },
    {
        "key": "agricultural",
        "name": "Agricultural communities",
        "connected_partners": ["uk", "cooperative_extension", "ky_sbdc"],
    },
]


# ── AI Literacy Continuum (FR-006) ──────────────────────────────────────

AI_LITERACY_LEVELS: List[Dict[str, Any]] = [
    {
        "key": "literacy",
        "name": "Literacy",
        "definition": (
            "Understanding 'Why AI?' and 'When AI?'. The lowest rung — "
            "what AI is, what it can and cannot do, when to use it."
        ),
        "audience_examples": [
            "small business owners",
            "frontline workforce",
            "K-12 educators",
            "government program staff",
        ],
    },
    {
        "key": "proficiency",
        "name": "Proficiency",
        "definition": (
            "Ability to apply AI to one's own work — using existing AI "
            "tools effectively for domain tasks."
        ),
        "audience_examples": [
            "incumbent workforce",
            "community-college students",
            "small-business operators with deployed AI tools",
        ],
    },
    {
        "key": "fluency",
        "name": "Fluency",
        "definition": (
            "Ability to create with AI — building, fine-tuning, or "
            "adapting AI systems for new problems."
        ),
        "audience_examples": [
            "advanced learners",
            "AI Deployment Corps practitioners",
            "researchers and engineers",
        ],
    },
]


# ── LOI Rules (FR-013, FR-014, Decision 9 / A2) ─────────────────────────

LOI_RULES: Dict[str, Any] = {
    "title_prefix": "Kentucky Coordination Hub:",
    "title_forbids_acronyms": True,
    "synopsis_page_limit": 1,
    "synopsis_word_budget": 600,
    "synopsis_must_cover": ["section_1_compressed", "section_2_compressed"],
    # Decision 9 / A2: location pinned to this module.
    # Acronym disallow-list is non-exhaustive; substring match is
    # case-sensitive and word-bounded at call time.
    "forbidden_acronyms": [
        "NSF", "AI", "UK", "KCTCS", "CPE", "COT", "KY", "KDE",
        "SBDC", "WIOA", "KCEW", "OTA", "LOI", "PI", "DOL",
        "USDA", "SBA", "NIFA", "TIP", "CISE", "EDU",
        "K-12", "K-16", "CAAI", "IBI", "DARPA", "ARPA-H",
    ],
}


# ── Supplemental Material Rules (FR-012) ────────────────────────────────

SUPPLEMENTAL_RULES: Dict[str, Dict[str, Any]] = {
    "letter_of_collaboration": {
        "key": "letter_of_collaboration",
        "is_allowed": True,
        "condition": None,
        "format_rule": "PAPPG format",
        "refusal_message": None,
    },
    "data_management_plan": {
        "key": "data_management_plan",
        "is_allowed": True,
        "condition": None,
        "format_rule": "NSF Data Management Plan format",
        "refusal_message": None,
    },
    "mentoring_plan": {
        "key": "mentoring_plan",
        "is_allowed": True,
        "condition": "budget_includes_postdocs_or_grad_students",
        "format_rule": "NSF Mentoring Plan format",
        "refusal_message": (
            "A Mentoring Plan is required only if the budget includes "
            "postdocs or graduate students. Confirm the budget structure "
            "before generating one."
        ),
    },
    "letter_of_support": {
        "key": "letter_of_support",
        "is_allowed": False,
        "condition": None,
        "format_rule": None,
        "refusal_message": (
            "The NSF 26-508 solicitation prohibits Letters of Support. "
            "Only Letters of Collaboration (PAPPG format), a Data "
            "Management Plan, and — if the budget includes postdocs or "
            "graduate students — a Mentoring Plan are permitted as "
            "supplemental materials."
        ),
    },
    "additional_narrative": {
        "key": "additional_narrative",
        "is_allowed": False,
        "condition": None,
        "format_rule": None,
        "refusal_message": (
            "The NSF 26-508 solicitation prohibits additional narrative "
            "supplements beyond the 15-page Project Description. The only "
            "permitted supplemental materials are Letters of "
            "Collaboration, a Data Management Plan, and (conditionally) a "
            "Mentoring Plan."
        ),
    },
}


# ── Framing Rules (FR-005, FR-017, FR-018) ──────────────────────────────

FRAMING_RULES: List[Dict[str, Any]] = [
    {
        "key": "coordinator_not_builder",
        "description": (
            "The Hub is a coordinator and convener, not a direct service "
            "provider. Emphasize backbone coordination and leveraging "
            "existing resources."
        ),
        "applies_to": [
            "loi_synopsis", "section_1", "section_2", "section_3",
            "section_4", "section_5",
        ],
        "violation_pattern_hints": [
            "we will deliver training",
            "we will train",
            "the Hub will train",
            "the Hub provides training to",
            "we provide training directly",
            "the Hub directly serves",
            "the Hub directly delivers",
            "we will offer courses",
            "we will teach",
        ],
    },
    {
        "key": "no_overpromise_innovation_or_econ_dev",
        "description": (
            "Avoid overpromising on innovation outcomes or economic "
            "development figures that exceed what coordination can "
            "credibly deliver."
        ),
        "applies_to": [
            "section_1", "section_4", "section_5",
        ],
        "violation_pattern_hints": [
            "innovation will",
            "this initiative will create thousands of jobs",
            "billions in economic impact",
            "transform the economy",
            "spawn an industry",
            "groundbreaking innovation",
        ],
    },
    {
        "key": "sustainability_year_4_plus",
        "description": (
            "Section 5 must emphasize sustainability beyond Year 3, "
            "including credible self-sustainment plans."
        ),
        "applies_to": ["section_5"],
        "violation_pattern_hints": [],
    },
    {
        "key": "baseline_before_progress",
        "description": (
            "Year 1 establishes baselines; Years 2-3 track against "
            "baselines. Do not claim progress without a baseline."
        ),
        "applies_to": ["section_4"],
        "violation_pattern_hints": [],
    },
    {
        "key": "common_instrument_across_partners",
        "description": (
            "Use a common cross-partner data-collection instrument so "
            "partner data are comparable."
        ),
        "applies_to": ["section_4"],
        "violation_pattern_hints": [],
    },
    {
        "key": "independent_evaluation_component",
        "description": (
            "Include an independent evaluation component. UK CAAI is "
            "positioned to play this role."
        ),
        "applies_to": ["section_4"],
        "violation_pattern_hints": [],
    },
    {
        "key": "prose_over_bullets",
        "description": (
            "Drafting style is clear, direct prose. Bullets only for "
            "lists where they materially improve readability."
        ),
        "applies_to": [
            "loi_synopsis", "section_1", "section_2", "section_3",
            "section_4", "section_5",
        ],
        "violation_pattern_hints": [],
    },
]


# ── Administration Priorities (FR-019 / A1) ─────────────────────────────

ADMINISTRATION_PRIORITIES: List[Dict[str, Any]] = [
    {
        "key": "white_house_ai_action_plan",
        "name": "White House AI Action Plan",
        "framing_phrase": "the White House AI Action Plan",
    },
    {
        "key": "americas_talent_strategy",
        "name": "America's Talent Strategy",
        "framing_phrase": "America's Talent Strategy",
    },
    {
        "key": "eo_ai_literacy",
        "name": "Executive Order on AI Literacy",
        "framing_phrase": "the executive order on AI literacy",
    },
    {
        "key": "eo_remove_ai_barriers",
        "name": "Executive Order on Removing Barriers to AI Leadership",
        "framing_phrase": "removing barriers to AI leadership",
    },
]

ADMINISTRATION_PRIORITY_PHRASES: List[str] = [
    p["framing_phrase"] for p in ADMINISTRATION_PRIORITIES
]


# ── Program Officer Question Topics (FR-015 / SC-012) ───────────────────

PROGRAM_OFFICER_QUESTION_TOPICS: List[Dict[str, Any]] = [
    {
        "key": "hub_to_hub_coordination",
        "name": "Hub-to-Hub coordination expectations",
        "seed_question": (
            "How does NSF expect State Coordination Hubs to coordinate "
            "with one another, particularly when neighboring Hubs share "
            "regional sectors (e.g., Appalachian energy, "
            "Midwest manufacturing)?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "deployment_corps_credentialing",
        "name": "AI Deployment Corps credentialing standard",
        "seed_question": (
            "What credentialing standard does NSF expect for AI "
            "Deployment Corps practitioners, and is alignment with an "
            "existing professional credential acceptable?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "shared_evaluation_instrument",
        "name": "Shared evaluation instrument across Hubs",
        "seed_question": (
            "Will the National Coordination Lead provide a shared "
            "cross-Hub evaluation instrument, or are State Hubs expected "
            "to develop their own and harmonize during execution?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "sub_award_mechanics",
        "name": "Sub-award mechanics and partner budgets",
        "seed_question": (
            "Are sub-awards to community-college and K-12 partners the "
            "expected mechanism for moving training-coordination dollars, "
            "or does NSF prefer pass-through participant-support costs?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "matching_funds_treatment",
        "name": "Matching funds and resource leveraging",
        "seed_question": (
            "How are leveraged funds (industry, philanthropy, state "
            "agency) reported in the work plan, and what level of "
            "commitment letter is expected for in-kind resources at the "
            "proposal stage versus during the cooperative-agreement "
            "negotiation stage?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "hub_responsibility_count",
        "name": "Number of Hub responsibilities required",
        "seed_question": (
            "How many of the five Hub responsibilities must be "
            "addressed in the proposal?"
        ),
        # The solicitation explicitly requires all five — so this question
        # is filtered out by the tool.
        "solicitation_resolved": True,
    },
    {
        "key": "page_limit_value",
        "name": "Page limit for the Project Description",
        "seed_question": (
            "What is the page limit for the Project Description?"
        ),
        # The solicitation specifies 15 pages — filtered out.
        "solicitation_resolved": True,
    },
    {
        "key": "round_one_award_count",
        "name": "Round 1 award count",
        "seed_question": (
            "How many awards will be made in Round 1?"
        ),
        # The solicitation specifies 10 in Round 1 — filtered out.
        "solicitation_resolved": True,
    },
    {
        "key": "catalyst_separate_competition",
        "name": "Catalyst Award timing",
        "seed_question": (
            "When will the AI-Ready Catalyst Award Competitions be "
            "announced relative to the Hub awards, and may a Hub "
            "applicant also submit to Catalyst?"
        ),
        "solicitation_resolved": False,
    },
    {
        "key": "national_lead_relationship",
        "name": "Working relationship with the National Coordination Lead",
        "seed_question": (
            "What is the operating cadence between State Coordination "
            "Hubs and the National Coordination Lead, and what "
            "deliverables are owed to the National Lead?"
        ),
        "solicitation_resolved": False,
    },
]

# Canonical solicitation phrases the agent should never echo back
# verbatim in program-officer questions (the question would be a
# tautology).
SOLICITATION_VERBATIM_PHRASES: List[str] = [
    "rather than delivering training directly",
    "leverage existing resources",
    "publicly accessible inventory",
    "AI Deployment Corps of credentialed practitioners",
    "complement, don't duplicate",
]


# ── Page Budget (FR-016 / SC-013) ───────────────────────────────────────

PAGE_BUDGET: Dict[str, Dict[str, Any]] = {
    "section_1": {
        "section_key": "section_1",
        "target_share": 0.27,
        "target_pages": round(15 * 0.27, 1),
        "protected_subelement_keys": SECTION_REQUIREMENTS["section_1"],
    },
    "section_2": {
        "section_key": "section_2",
        "target_share": 0.20,
        "target_pages": round(15 * 0.20, 1),
        "protected_subelement_keys": SECTION_REQUIREMENTS["section_2"],
    },
    "section_3": {
        "section_key": "section_3",
        "target_share": 0.13,
        "target_pages": round(15 * 0.13, 1),
        "protected_subelement_keys": SECTION_REQUIREMENTS["section_3"],
    },
    "section_4": {
        "section_key": "section_4",
        "target_share": 0.27,
        "target_pages": round(15 * 0.27, 1),
        "protected_subelement_keys": SECTION_REQUIREMENTS["section_4"],
    },
    "section_5": {
        "section_key": "section_5",
        "target_share": 0.13,
        "target_pages": round(15 * 0.13, 1),
        "protected_subelement_keys": SECTION_REQUIREMENTS["section_5"],
    },
}


# ── Critical Deadlines (FR-020 / SC-014) ────────────────────────────────

DEADLINES: Dict[str, Dict[str, Any]] = {
    "loi": {
        "key": "loi",
        "date_iso": "2026-06-16",
        "submission_path": "Research.gov",
        "display_label": "Letter of Intent (LOI)",
    },
    "full_proposal": {
        "key": "full_proposal",
        "date_iso": "2026-07-16",
        "submission_path": (
            "Research.gov or Grants.gov; AOR signature required"
        ),
        "display_label": "Full Proposal",
    },
    "internal": {
        "key": "internal",
        "date_iso": "2026-07-09",
        "submission_path": (
            "University of Kentucky Office of Sponsored Projects"
        ),
        "display_label": "Internal Institutional Deadline (approx.)",
    },
}


# ── Lookup Helpers ──────────────────────────────────────────────────────

def get_section(section_key: str) -> Dict[str, Any]:
    """Return the SECTIONS entry for ``section_key``.

    Args:
        section_key: One of ``loi_synopsis``, ``section_1`` … ``section_5``.

    Returns:
        The matching dict from ``SECTIONS``.

    Raises:
        KeyError: If ``section_key`` is not recognized.
    """
    for section in SECTIONS:
        if section["key"] == section_key:
            return section
    raise KeyError(f"Unknown section_key: {section_key!r}")


def get_partner(partner_key: str) -> Dict[str, Any]:
    """Return the KY_PARTNERS entry for ``partner_key``.

    Raises:
        KeyError: If ``partner_key`` is not recognized.
    """
    for partner in KY_PARTNERS:
        if partner["key"] == partner_key:
            return partner
    raise KeyError(f"Unknown partner_key: {partner_key!r}")


def get_hub_responsibilities_for_section(section_key: str) -> List[Dict[str, Any]]:
    """Return Hub responsibilities whose ``cross_section_relevance``
    includes ``section_key``."""
    return [
        r for r in HUB_RESPONSIBILITIES
        if section_key in r["cross_section_relevance"]
    ]


def get_framing_rules_for_section(section_key: str) -> List[Dict[str, Any]]:
    """Return framing rules that apply to ``section_key``."""
    return [
        r for r in FRAMING_RULES
        if section_key in r["applies_to"]
    ]


def is_acronym_forbidden_in_loi_title(token: str) -> bool:
    """True iff ``token`` matches a forbidden-acronym entry exactly
    (case-sensitive) or as a whitespace-bounded substring of a longer
    multi-token entry."""
    forbidden = LOI_RULES["forbidden_acronyms"]
    if token in forbidden:
        return True
    # Multi-token forbidden entries (e.g., "K-12") are matched by
    # whole-token equality only; the caller is responsible for
    # tokenization.
    return False


__all__ = [
    "SOLICITATION_META",
    "OPPORTUNITY_FAMILY",
    "SECTIONS",
    "SECTION_HEADINGS",
    "SECTION_REQUIREMENTS",
    "HUB_RESPONSIBILITIES",
    "NSF_REQUIRED_METRICS",
    "EXTENDED_METRIC_LAYERS",
    "ALL_METRICS",
    "KY_PARTNERS",
    "KY_PRIORITY_SECTORS",
    "KY_EQUITY_LENSES",
    "AI_LITERACY_LEVELS",
    "LOI_RULES",
    "SUPPLEMENTAL_RULES",
    "FRAMING_RULES",
    "ADMINISTRATION_PRIORITIES",
    "ADMINISTRATION_PRIORITY_PHRASES",
    "PROGRAM_OFFICER_QUESTION_TOPICS",
    "SOLICITATION_VERBATIM_PHRASES",
    "PAGE_BUDGET",
    "DEADLINES",
    "get_section",
    "get_partner",
    "get_hub_responsibilities_for_section",
    "get_framing_rules_for_section",
    "is_acronym_forbidden_in_loi_title",
]
