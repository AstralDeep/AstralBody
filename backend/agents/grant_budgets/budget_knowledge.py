#!/usr/bin/env python3
"""
Grant Budget Knowledge Base.

Contains CGS budget template structure, NSF/NIH PAPPG budget rules,
institutional rate defaults, salary bands, and common budget items
used by the Grant Budgets Agent for budget estimation and generation.
"""
from typing import Dict, List, Any


# ── CGS Budget Template Categories (A–J) ──────────────────────────────

CGS_BUDGET_CATEGORIES = {
    "A": {
        "code": "A",
        "name": "Senior Personnel",
        "description": "PI, Co-PIs, and other senior/key personnel.",
        "subcategories": [
            "Principal Investigator (PI)",
            "Co-Principal Investigator(s)",
            "Other Senior Personnel",
        ],
        "notes": (
            "List each person by name and role. Show person-months "
            "(calendar, academic, or summer) and requested salary."
        ),
    },
    "B": {
        "code": "B",
        "name": "Other Personnel",
        "description": "Postdocs, graduate students, undergraduate students, and other staff.",
        "subcategories": [
            "Postdoctoral Researchers",
            "Graduate Students (Research Assistants)",
            "Undergraduate Students",
            "Secretarial/Clerical",
            "Other Personnel",
        ],
        "notes": (
            "For NSF, clerical salaries are generally NOT allowed unless "
            "justified as unlike circumstances. Graduate student stipends "
            "should reflect institutional rates."
        ),
    },
    "C": {
        "code": "C",
        "name": "Fringe Benefits",
        "description": "Employee benefits calculated as a percentage of salaries.",
        "notes": (
            "Use the institution's federally negotiated fringe benefit rate. "
            "Different rates may apply to different personnel categories "
            "(e.g., faculty vs. graduate students)."
        ),
    },
    "D": {
        "code": "D",
        "name": "Equipment",
        "description": "Items costing $5,000 or more per unit with a useful life >1 year.",
        "notes": (
            "Equipment is defined as tangible personal property with an acquisition "
            "cost of $5,000 or more and a useful life of more than one year. "
            "Equipment is EXCLUDED from the F&A (MTDC) base."
        ),
    },
    "E": {
        "code": "E",
        "name": "Travel",
        "description": "Domestic and international travel for project personnel.",
        "subcategories": [
            "Domestic Travel",
            "International Travel",
        ],
        "notes": (
            "NSF requires a minimum of one domestic trip for PI to attend "
            "relevant professional conferences. International travel must be "
            "specifically justified. Use GSA per diem rates for federal grants."
        ),
    },
    "F": {
        "code": "F",
        "name": "Participant Support Costs",
        "description": "Stipends, travel, subsistence, and other costs for participants.",
        "subcategories": [
            "Participant Stipends",
            "Participant Travel",
            "Participant Subsistence",
            "Other Participant Costs",
        ],
        "notes": (
            "Participant support costs are EXCLUDED from the F&A base. "
            "These are for individuals (not employees) receiving training "
            "or services. Cannot be re-budgeted without sponsor approval."
        ),
    },
    "G": {
        "code": "G",
        "name": "Other Direct Costs",
        "description": "Materials, supplies, publication costs, computing, subawards, etc.",
        "subcategories": [
            "Materials and Supplies",
            "Publication Costs",
            "Consultant Services",
            "Computer Services / Cloud Computing",
            "Subawards / Subcontracts",
            "Tuition Remission",
            "Other",
        ],
        "notes": (
            "Subaward F&A: Only the first $25,000 of each subaward is included "
            "in the MTDC base for F&A calculation. Tuition remission for graduate "
            "students is typically excluded from F&A."
        ),
    },
    "H": {
        "code": "H",
        "name": "Total Direct Costs",
        "description": "Sum of categories A through G.",
        "notes": "Computed automatically from above categories.",
    },
    "I": {
        "code": "I",
        "name": "Facilities & Administrative (F&A) Costs",
        "description": "Indirect costs calculated on the Modified Total Direct Cost base.",
        "notes": (
            "F&A rate is applied to the MTDC base. MTDC = Total Direct Costs "
            "minus equipment, participant support, tuition remission, and "
            "subaward amounts exceeding $25,000 per subaward."
        ),
    },
    "J": {
        "code": "J",
        "name": "Total Costs",
        "description": "Total Direct Costs (H) + F&A Costs (I).",
        "notes": "This is the total amount requested from the sponsor.",
    },
}


# ── NSF PAPPG Budget Rules ─────────────────────────────────────────────

NSF_PAPPG_RULES = {
    "salary": {
        "two_month_rule": (
            "NSF limits compensation for senior project personnel to no more than "
            "two months of their regular salary in any one year across ALL NSF-funded "
            "projects. This includes both calendar-year and academic-year appointments."
        ),
        "academic_year": (
            "Faculty on 9-month academic appointments may request up to 2 months "
            "of summer salary from NSF. The 2-month cap applies across ALL active "
            "NSF awards, not per-award."
        ),
        "calendar_year": (
            "Faculty on 12-month appointments: NSF salary requests must not exceed "
            "2/12 of their annual salary across all NSF awards."
        ),
        "voluntary_committed_cost_sharing": (
            "NSF does NOT allow voluntary committed cost sharing. Do not include "
            "cost sharing unless the solicitation specifically requires it."
        ),
    },
    "equipment": {
        "threshold": 5000,
        "definition": (
            "Equipment is tangible personal property (including information "
            "technology systems) having a useful life of more than one year and "
            "a per-unit acquisition cost equaling or exceeding $5,000."
        ),
        "f_and_a": "Equipment costs are excluded from the MTDC base.",
    },
    "travel": {
        "domestic_requirement": (
            "Funds may be requested for field work, attendance at professional "
            "meetings, and similar activities. A minimum of one domestic trip "
            "per year is typical for conference attendance."
        ),
        "international": (
            "International travel must be specifically budgeted and justified. "
            "Must comply with the Fly America Act (use U.S. carriers) unless "
            "Open Skies agreement applies."
        ),
        "fly_america": (
            "Federally funded international travel must use U.S. flag carriers "
            "unless an exception applies (Open Skies agreements with EU, etc.)."
        ),
    },
    "participant_support": {
        "definition": (
            "Direct costs for participants (not employees) in conferences, "
            "workshops, or training activities: stipends, travel allowances, "
            "subsistence, registration fees, and other related costs."
        ),
        "restrictions": (
            "Participant support costs CANNOT be re-budgeted to other categories "
            "without prior NSF approval. These are excluded from the F&A base."
        ),
    },
    "subawards": {
        "f_and_a_rule": (
            "Only the first $25,000 of each subaward is included in the MTDC "
            "base for F&A purposes. Amounts exceeding $25,000 are excluded."
        ),
    },
    "general": {
        "budget_justification": (
            "A budget justification of up to five pages must accompany the budget. "
            "Each budget line item requires a clear narrative explanation."
        ),
        "cost_sharing": (
            "Voluntary committed cost sharing is prohibited in NSF proposals "
            "unless explicitly required by the solicitation."
        ),
    },
}


# ── NIH Budget Rules ───────────────────────────────────────────────────

NIH_BUDGET_RULES = {
    "salary_cap": {
        "current_cap": 221900,
        "effective_date": "January 2024",
        "description": (
            "NIH limits the direct salary (institutional base salary) that may "
            "be paid with NIH grant funds to Executive Level II of the Federal "
            "Executive Pay Scale. As of January 2024, this cap is $221,900."
        ),
    },
    "modular_budget": {
        "threshold": 250000,
        "description": (
            "NIH uses modular budgets for requests up to $250,000 per year in "
            "direct costs. Budgets are requested in $25,000 modules. Detailed "
            "categorical budgets are NOT required for modular applications."
        ),
        "module_size": 25000,
    },
    "detailed_budget": {
        "description": (
            "Required when direct costs exceed $250,000 in any single year. "
            "Must provide detailed categorical budget with itemized costs."
        ),
    },
    "r01_typical_range": {
        "min": 150000,
        "max": 500000,
        "description": "Typical R01 direct costs range: $150K-$500K/year.",
    },
    "r21_limits": {
        "max_per_year": 275000,
        "max_total": 275000,
        "duration_years": 2,
        "description": (
            "R21 (Exploratory/Developmental Research): max $275,000 in direct "
            "costs over the entire project period (usually 2 years). "
            "Combined budget for all years cannot exceed $275,000."
        ),
    },
}


# ── Default Institutional Rates ────────────────────────────────────────

DEFAULT_RATES = {
    "fringe": {
        "faculty": 0.30,
        "staff": 0.35,
        "postdoc": 0.25,
        "graduate_student": 0.05,
        "undergraduate": 0.08,
        "description": (
            "Fringe benefit rates vary by personnel category and institution. "
            "These are representative rates — always use your institution's "
            "federally negotiated rates."
        ),
    },
    "f_and_a": {
        "on_campus_research": 0.56,
        "off_campus_research": 0.26,
        "instruction": 0.50,
        "other_sponsored": 0.36,
        "base": "MTDC",
        "description": (
            "F&A (indirect cost) rates are negotiated between the institution "
            "and the federal government (cognizant agency). Rates shown are "
            "representative. MTDC = Modified Total Direct Costs."
        ),
    },
    "gsa_per_diem": {
        "domestic_lodging_avg": 107,
        "domestic_meals_avg": 64,
        "international_lodging_avg": 200,
        "international_meals_avg": 90,
        "description": (
            "GSA per diem rates vary by location. These are national averages. "
            "Check gsa.gov for specific city/county rates."
        ),
    },
    "tuition_remission": {
        "graduate_per_semester": 7500,
        "description": (
            "Graduate student tuition remission rates vary by institution. "
            "Typically excluded from the F&A base."
        ),
    },
}


# ── Salary Bands by Role ──────────────────────────────────────────────

SALARY_BANDS = {
    "principal_investigator": {
        "role": "Principal Investigator (PI)",
        "typical_range": (100000, 250000),
        "appointment": "9-month or 12-month",
        "notes": "Salary varies widely by rank, discipline, and institution.",
    },
    "co_pi": {
        "role": "Co-Principal Investigator",
        "typical_range": (90000, 220000),
        "appointment": "9-month or 12-month",
        "notes": "Same salary cap rules as PI apply.",
    },
    "postdoc": {
        "role": "Postdoctoral Researcher",
        "typical_range": (56484, 72000),
        "appointment": "12-month",
        "notes": (
            "NIH NRSA minimum stipend: $56,484 (FY2024, PGY-0). "
            "Many institutions set minimums at or above NRSA levels."
        ),
    },
    "graduate_ra": {
        "role": "Graduate Research Assistant",
        "typical_range": (24000, 38000),
        "appointment": "12-month (stipend)",
        "notes": (
            "Stipend rates set by institution/department. "
            "Tuition remission budgeted separately."
        ),
    },
    "undergraduate": {
        "role": "Undergraduate Student Worker",
        "typical_range": (12, 20),
        "appointment": "Hourly",
        "notes": "Typically 10-20 hours/week during academic year.",
    },
    "research_staff": {
        "role": "Research Staff / Lab Manager",
        "typical_range": (45000, 80000),
        "appointment": "12-month",
        "notes": "Full-time staff positions.",
    },
}


# ── Common Budget Items by Category ────────────────────────────────────

COMMON_BUDGET_ITEMS = {
    "equipment": [
        {"item": "High-Performance Computing Server (GPU)", "range": (15000, 80000)},
        {"item": "GPU Accelerator Card (e.g., A100, H100)", "range": (8000, 35000)},
        {"item": "Data Storage System (NAS/SAN)", "range": (5000, 30000)},
        {"item": "Specialized Scientific Instrument", "range": (10000, 500000)},
        {"item": "Networking Equipment (10GbE+)", "range": (5000, 15000)},
    ],
    "computing": [
        {"item": "Cloud Computing (AWS/GCP/Azure)", "range_per_year": (5000, 50000)},
        {"item": "Software Licenses", "range_per_year": (1000, 10000)},
        {"item": "HPC Cluster Time", "range_per_year": (2000, 20000)},
    ],
    "supplies": [
        {"item": "Laptop/Desktop Computer (<$5K)", "range": (1500, 4999)},
        {"item": "Lab Supplies and Consumables", "range_per_year": (2000, 15000)},
        {"item": "Office Supplies", "range_per_year": (500, 2000)},
    ],
    "travel": [
        {"item": "Domestic Conference Trip", "range_per_trip": (1500, 3000)},
        {"item": "International Conference Trip", "range_per_trip": (3000, 6000)},
        {"item": "Domestic Fieldwork/Collaboration", "range_per_trip": (800, 2000)},
    ],
    "publication": [
        {"item": "Open Access Publication Fees", "range_per_article": (1500, 5000)},
        {"item": "Page Charges", "range_per_article": (500, 2000)},
    ],
    "other": [
        {"item": "Human Subjects Incentives", "range_per_year": (1000, 10000)},
        {"item": "Printing and Copying", "range_per_year": (200, 1000)},
        {"item": "Communication Costs", "range_per_year": (500, 2000)},
    ],
}


# ── Cover Letter Analysis Keywords ─────────────────────────────────────

BUDGET_SIGNAL_KEYWORDS = {
    "personnel": [
        "hire", "recruit", "postdoc", "graduate student", "research assistant",
        "PI", "co-PI", "collaborator", "personnel", "team", "staff",
        "faculty", "student", "trainee", "technician", "programmer",
        "data scientist", "research associate", "lab manager",
    ],
    "equipment": [
        "equipment", "instrument", "server", "GPU", "compute", "hardware",
        "microscope", "sensor", "robot", "device", "machine", "cluster",
        "workstation", "storage", "infrastructure",
    ],
    "travel": [
        "travel", "conference", "workshop", "meeting", "symposium",
        "fieldwork", "field work", "site visit", "collaboration visit",
        "international", "domestic", "present results", "dissemination",
    ],
    "computing": [
        "cloud", "AWS", "GCP", "Azure", "computing", "HPC",
        "high-performance", "GPU", "computational", "data processing",
        "machine learning", "deep learning", "training runs", "inference",
    ],
    "participant_support": [
        "participant", "workshop", "training", "bootcamp", "hackathon",
        "summer school", "REU", "outreach", "K-12", "broadening participation",
        "stipend", "mentoring", "education",
    ],
    "subcontracts": [
        "subaward", "subcontract", "partner institution", "collaborating site",
        "multi-site", "consortium", "external partner", "subrecipient",
    ],
    "supplies": [
        "supplies", "materials", "consumables", "reagents", "chemicals",
        "software license", "subscription", "dataset", "data acquisition",
    ],
}


# ── F&A Exclusion Rules ───────────────────────────────────────────────

FA_EXCLUSION_RULES = {
    "always_excluded": [
        "equipment",
        "participant_support",
        "tuition_remission",
    ],
    "partially_excluded": {
        "subawards": {
            "included_amount": 25000,
            "description": (
                "Only the first $25,000 of each subaward is included in the "
                "MTDC base. Amounts above $25,000 are excluded."
            ),
        },
    },
    "description": (
        "Modified Total Direct Costs (MTDC) excludes equipment, capital "
        "expenditures, charges for patient care, rental costs, tuition "
        "remission, scholarships/fellowships, participant support costs, "
        "and the portion of each subaward exceeding $25,000."
    ),
}
