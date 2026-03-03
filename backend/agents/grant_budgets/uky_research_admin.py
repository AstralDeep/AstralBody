#!/usr/bin/env python3
"""
University of Kentucky Research Administration Knowledge Base.

Contains structured information about OSPA, CGS, and PDO — the three
offices researchers interact with for sponsored project administration.
Policies, forms, contacts, deadlines, and institutional boilerplate
are organized here for searchable lookup and Q&A.

Sources:
- https://www.research.uky.edu/office-sponsored-projects-administration
- https://research.uky.edu/sponsored-project-services/about/CGS
- https://research.uky.edu/proposal-development-office
- https://research.uky.edu/sponsored-project-services
- University Administrative Regulation 7:3
"""
from typing import Dict, List, Any


# ═══════════════════════════════════════════════════════════════════════
# OFFICE PROFILES
# ═══════════════════════════════════════════════════════════════════════

OFFICES = {
    "OSPA": {
        "full_name": "Office of Sponsored Projects Administration",
        "url": "https://www.research.uky.edu/office-sponsored-projects-administration",
        "email": "ospa@uky.edu",
        "phone": "(859) 257-9420",
        "location": "Kinkead Hall, 1st Floor (West Wing), 504 Library Drive, Lexington, KY",
        "executive_director": "Kim C. Carter",
        "role_summary": (
            "Institutional authority for extramural grants and contracts. "
            "OSPA is the Authorized Organizational Representative (AOR) — "
            "the only entity that can officially submit proposals and accept "
            "awards on behalf of UK through the UK Research Foundation."
        ),
        "handles": [
            "Official proposal submission to sponsors",
            "Award negotiation and acceptance",
            "Contract and subaward execution",
            "Compliance (export control, foreign influence, E-Verify)",
            "Account setup through Research Financial Services",
            "Project closeout (non-financial reports to sponsors)",
            "Clinical trial agreements",
            "Departing investigator transfers",
            "Prior approval requests to sponsors",
        ],
        "does_not_handle": [
            "Budget development (→ CGS)",
            "Proposal writing or review (→ PDO)",
            "Day-to-day financial management (→ CGS)",
            "Funding searches (→ PDO)",
        ],
        "divisions": [
            "Proposal Services (Pre-Award) — Team 1 & Team 2",
            "Award Services (Post-Award) — Team 1 & Team 2",
            "Contracts & Subawards (including Clinical Trials)",
            "Training & Administrative Operations",
        ],
        "key_systems": ["Cayuse 424 / Cayuse Proposals (S2S)", "SAP"],
    },
    "CGS": {
        "full_name": "Collaborative Grant Services",
        "url": "https://research.uky.edu/sponsored-project-services/about/CGS",
        "email": "collaborativegrantservices@uky.edu",
        "phone": None,
        "location": "Bowman Hall (primarily remote — communicate via email, Teams, phone)",
        "role_summary": (
            "Hands-on, day-to-day research administration partner for PIs. "
            "CGS handles the practical financial and administrative work of "
            "preparing proposals and managing active awards — budgets, forms, "
            "reconciliation, cost transfers, and financial reporting."
        ),
        "handles": [
            "Budget development and budget justifications",
            "Internal Approval Form (IAF/eIAF) preparation and routing",
            "Proposal Initiation Form (PIF) processing",
            "Administrative proposal components",
            "Cost-sharing coordination and monitoring",
            "Payroll and non-payroll cost transfers",
            "Monthly expense reconciliation",
            "Subcontract monitoring and invoice review",
            "Financial forecasts and spending analysis",
            "Sponsor-required financial reporting",
            "Project closeout (financial) and carryforward",
            "Just-In-Time (JIT) materials",
            "Current & Pending documentation",
            "F&A waiver requests",
            "Off-campus effort determinations",
        ],
        "does_not_handle": [
            "Official proposal submission (→ OSPA)",
            "Contract negotiation (→ OSPA)",
            "Proposal narrative writing or review (→ PDO)",
            "Funding searches (→ PDO)",
        ],
        "hubs": {
            "Hub 1": {
                "colleges": [
                    "Agriculture, Food & Environment",
                    "Arts & Sciences",
                    "Engineering",
                ],
            },
            "Hub 2": {
                "colleges": [
                    "Medicine",
                    "Nursing",
                    "Pharmacy",
                    "Public Health",
                    "Dentistry",
                    "Health Sciences",
                ],
            },
            "Hub 3": {
                "colleges": [
                    "Business & Economics",
                    "Communication & Information",
                    "Design",
                    "Education",
                    "Law",
                    "Social Work",
                    "Graduate School",
                    "Other Programs",
                ],
            },
        },
        "response_commitment": "24-hour response to requests",
        "hours": "8am-5pm, Monday-Friday",
        "key_systems": ["Cayuse", "SAP", "Concur", "ECM", "SciENcv", "SharePoint"],
    },
    "PDO": {
        "full_name": "Proposal Development Office",
        "url": "https://research.uky.edu/proposal-development-office",
        "email": "pdo@uky.edu",
        "phone": "(859) 257-2861",
        "location": "504 M.I. King Library, Lexington, KY",
        "executive_director": "Kathy Grzech",
        "associate_director": "Barbara Duncan, PhD",
        "role_summary": (
            "Proposal quality and strategy office. PDO helps researchers "
            "find funding, build competitive proposals, identify collaborators, "
            "and improve narrative quality. They focus on the intellectual and "
            "strategic content of proposals, not budgets or submission."
        ),
        "handles": [
            "Funding searches (submit request; results in ~3 weeks)",
            "Funding alerts by keyword/research area",
            "Proposal critique and narrative review",
            "Limited submission management (internal competitions)",
            "Collaborator identification (Scholars@UK, SPIFi)",
            "Facilities description library",
            "Complex grants project management (multi-PI center grants)",
            "Award/honorific nomination support",
            "Resubmission strategy and reviewer critique analysis",
            "Training workshops (Friday High-Five sessions, bootcamps)",
            "Data management plan templates",
            "Broader impacts guidance",
        ],
        "does_not_handle": [
            "Budget development (→ CGS)",
            "Administrative forms (→ CGS)",
            "Official submission (→ OSPA)",
            "Post-award management (→ CGS/OSPA)",
        ],
        "key_resources": [
            "Pivot-RP database (funding discovery)",
            "Scholars@UK (researcher profiles/collaboration)",
            "Facilities Description Library (LinkBlue login)",
            "Data Management Planning Tool",
            "Broader Impacts & Community Outreach Resources (SharePoint)",
            "NIH Rigor and Reproducibility Resources",
        ],
        "key_systems": ["Pivot-RP", "Scholars@UK", "Qualtrics (service requests)"],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# FORMS & TEMPLATES
# ═══════════════════════════════════════════════════════════════════════

FORMS_AND_TEMPLATES = [
    {
        "name": "Internal Approval Form (IAF / eIAF)",
        "office": "CGS",
        "purpose": (
            "Required institutional approval form for all sponsored project "
            "proposals. Routes through department, college, and OSPA for "
            "compliance review before submission."
        ),
        "deadline_rule": (
            "Must reach OSPA at least 3 business days before sponsor deadline. "
            "College-specific deadlines may be 5-14 business days before OSPA deadline."
        ),
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["pre-award", "approval", "required", "routing"],
    },
    {
        "name": "Proposal Initiation Form (PIF)",
        "office": "CGS",
        "purpose": (
            "Initiates CGS engagement on a new proposal. Provides CGS with "
            "project details, sponsor info, and timeline so they can assign "
            "staff and begin budget development."
        ),
        "deadline_rule": "Due 30 business days before sponsor deadline.",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["pre-award", "initiation", "required", "timeline"],
    },
    {
        "name": "Request for Action/Revision Form",
        "office": "CGS",
        "purpose": "Request post-award modifications, budget revisions, or no-cost extensions.",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["post-award", "modification", "revision"],
    },
    {
        "name": "Off Campus Effort Worksheet",
        "office": "CGS",
        "purpose": "Document and calculate off-campus effort for F&A rate determination.",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["f&a", "effort", "off-campus"],
    },
    {
        "name": "IP Waiver Form (PI)",
        "office": "CGS",
        "purpose": "Intellectual property waiver for the principal investigator.",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["compliance", "ip", "waiver"],
    },
    {
        "name": "IP Waiver Form (Project Personnel)",
        "office": "CGS",
        "purpose": "Intellectual property waiver for project personnel (non-PI).",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["compliance", "ip", "waiver"],
    },
    {
        "name": "Childcare Reimbursement Request",
        "office": "CGS",
        "purpose": "Request reimbursement for childcare costs related to sponsored project travel.",
        "url": "https://www.research.uky.edu/collaborative-grant-services/resources-and-tools",
        "tags": ["post-award", "reimbursement", "travel"],
    },
    {
        "name": "Departing Investigator MOU",
        "office": "OSPA",
        "purpose": (
            "Memorandum of Understanding for PIs leaving UK. Covers transfer "
            "of awards, equipment, data, students, and closeout procedures. "
            "Includes 7 appendices (A-G)."
        ),
        "url": "https://www.research.uky.edu/office-sponsored-projects-administration",
        "tags": ["departure", "transfer", "mou"],
    },
    {
        "name": "Online Subagreement Request",
        "office": "OSPA",
        "purpose": "Request initiation of a new subaward/subcontract.",
        "url": "https://www.research.uky.edu/office-sponsored-projects-administration",
        "tags": ["subaward", "subcontract", "request"],
    },
    {
        "name": "Model Contractual Agreement — Fixed Price",
        "office": "CGS",
        "purpose": "Template for fixed-price contractual agreements.",
        "tags": ["contract", "template", "fixed-price"],
    },
    {
        "name": "Model Contractual Agreement — Cost Reimbursable",
        "office": "CGS",
        "purpose": "Template for cost-reimbursable contractual agreements.",
        "tags": ["contract", "template", "cost-reimbursable"],
    },
    {
        "name": "Clinical Trial Agreement Template",
        "office": "OSPA",
        "purpose": "Standard template for clinical trial agreements.",
        "tags": ["clinical-trial", "template", "contract"],
    },
    {
        "name": "SBIR/STTR Templates",
        "office": "CGS",
        "purpose": "Budget and administrative templates for Small Business Innovation Research submissions.",
        "tags": ["sbir", "sttr", "template", "small-business"],
    },
    {
        "name": "BudRule CrossWalk (Excel)",
        "office": "CGS",
        "purpose": "Maps budget categories to SAP cost objects and spending rules.",
        "tags": ["budget", "sap", "crosswalk", "rules"],
    },
    {
        "name": "Safe and Inclusive Work Plan",
        "office": "CGS",
        "purpose": "NSF-required plan for fieldwork and off-campus research safety.",
        "tags": ["nsf", "safety", "fieldwork", "required"],
    },
    {
        "name": "Investigator Quick Reference Guide",
        "office": "CGS",
        "purpose": "Quick-start guide for PIs on CGS processes, deadlines, and contacts.",
        "tags": ["reference", "guide", "quick-start"],
    },
    {
        "name": "Investigator Project Checklist",
        "office": "CGS",
        "purpose": "Checklist for PIs to track proposal and award management tasks.",
        "tags": ["checklist", "project-management"],
    },
    {
        "name": "Data Management Plan Templates",
        "office": "PDO",
        "purpose": "Templates for NSF, NIH, NEH, NOAA, GBMF, IMLS data management plans.",
        "url": "https://research.uky.edu/proposal-development-office/proposal-resources",
        "tags": ["data-management", "template", "nsf", "nih"],
    },
    {
        "name": "Facilities Description Library",
        "office": "PDO",
        "purpose": (
            "Library of standard text descriptions of UK resources, colleges, "
            "departments, and core facilities for inclusion in proposals."
        ),
        "url": "https://research.uky.edu/proposal-development-office/proposal-resources",
        "tags": ["facilities", "boilerplate", "narrative"],
        "notes": "Requires LinkBlue login.",
    },
    {
        "name": "Funding Search Request Form",
        "office": "PDO",
        "purpose": "Submit a request for PDO to conduct a personalized funding search.",
        "url": "https://research.uky.edu/proposal-development-office/funding-opportunities",
        "tags": ["funding", "search", "request"],
    },
]


# ═══════════════════════════════════════════════════════════════════════
# POLICIES & REGULATIONS
# ═══════════════════════════════════════════════════════════════════════

POLICIES = [
    {
        "name": "Administrative Regulation 7:3 (AR 7:3)",
        "office": "University / OSPA",
        "description": (
            "The governing university regulation for all sponsored projects at UK. "
            "Defines PI eligibility, proposal requirements, award acceptance authority, "
            "fiscal responsibility, IP obligations, and reporting requirements."
        ),
        "url": "https://regs.uky.edu/administrative-regulation/ar-73",
        "tags": ["regulation", "governance", "pi-eligibility", "required"],
    },
    {
        "name": "3-Business-Day Rule",
        "office": "OSPA",
        "description": (
            "A complete and final proposal with a fully approved Internal Approval "
            "Form (IAF) must reach the assigned OSPA Research Administrator at "
            "least 3 business days before the sponsor's submission deadline."
        ),
        "tags": ["deadline", "submission", "required", "ospa-rule"],
    },
    {
        "name": "VPR Late Policy",
        "office": "OSPA / VPR",
        "description": (
            "Policy governing what happens when proposals miss the 3-business-day "
            "deadline. Late submissions require VPR approval and may not be submitted."
        ),
        "tags": ["deadline", "late", "policy"],
    },
    {
        "name": "PIF 30-Day Rule",
        "office": "CGS",
        "description": (
            "The Proposal Initiation Form (PIF) must be submitted to CGS at least "
            "30 business days before the sponsor deadline to allow adequate time "
            "for budget development and administrative preparation."
        ),
        "tags": ["deadline", "pif", "required", "cgs-rule"],
    },
    {
        "name": "Federal Uniform Guidance (2 CFR 200)",
        "office": "OSPA",
        "description": (
            "Federal requirements for grants and cooperative agreements. Covers "
            "cost principles, audit requirements, and administrative requirements "
            "for all federally-funded projects."
        ),
        "url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200",
        "tags": ["federal", "compliance", "cost-principles", "audit"],
    },
    {
        "name": "Cost Sharing Policy",
        "office": "OSPA / CGS",
        "description": (
            "UK policy on committed cost sharing. Voluntary committed cost sharing "
            "is discouraged and requires college/department approval. Mandatory "
            "cost sharing (required by solicitation) must be documented and tracked."
        ),
        "tags": ["cost-sharing", "budget", "compliance"],
    },
    {
        "name": "Export Control Policy",
        "office": "OSPA",
        "description": (
            "Compliance with federal export control regulations (EAR, ITAR). "
            "Required review for projects involving controlled technology, "
            "international collaborators, or foreign nationals."
        ),
        "tags": ["export-control", "compliance", "international"],
    },
    {
        "name": "Conflict of Interest / Financial Disclosure",
        "office": "OSPA",
        "description": (
            "Requirements for disclosing significant financial interests that "
            "could affect research objectivity. Required before proposal submission "
            "and updated annually."
        ),
        "url": "https://www.research.uky.edu/office-sponsored-projects-administration",
        "tags": ["coi", "disclosure", "compliance", "required"],
    },
    {
        "name": "Data Security Compliance Program",
        "office": "OSPA",
        "description": (
            "Requirements for protecting controlled unclassified information (CUI), "
            "HIPAA data, and other sensitive research data on sponsored projects."
        ),
        "tags": ["data-security", "cui", "hipaa", "compliance"],
    },
    {
        "name": "Sub-Recipient vs. Vendor Determination",
        "office": "OSPA / CGS",
        "description": (
            "Guidelines for determining whether an external entity is a sub-recipient "
            "(performs substantive work) or a vendor (provides goods/services). "
            "Affects procurement method, F&A treatment, and monitoring requirements."
        ),
        "tags": ["subaward", "vendor", "procurement", "determination"],
    },
    {
        "name": "Mandatory Disclosure (2 CFR 200.113)",
        "office": "OSPA",
        "description": (
            "Requirement to disclose violations of federal criminal law involving "
            "fraud, bribery, or gratuity related to federal awards."
        ),
        "tags": ["disclosure", "compliance", "federal"],
    },
]


# ═══════════════════════════════════════════════════════════════════════
# INSTITUTIONAL INFORMATION (BOILERPLATE)
# ═══════════════════════════════════════════════════════════════════════

INSTITUTIONAL_INFO = {
    "legal_name": "University of Kentucky Research Foundation",
    "duns_number": "939017877",
    "uei_number": "H1HYA8V1GD15",
    "ein": "61-6033693",
    "cage_code": "3DMD3",
    "sam_status": "Active",
    "congressional_district": "KY-06",
    "institution_type": "Public, R1 Research University",
    "address": {
        "street": "500 South Limestone",
        "city": "Lexington",
        "state": "KY",
        "zip": "40506-0001",
        "country": "USA",
    },
    "authorized_organizational_representative": {
        "office": "OSPA",
        "note": (
            "Only OSPA can officially submit proposals and accept awards. "
            "Individual PIs are NOT authorized to sign on behalf of UK."
        ),
    },
    "cognizant_agency": {
        "agency": "Department of Health and Human Services (DHHS)",
        "description": "Federal agency responsible for negotiating UK's F&A rates.",
    },
    "f_and_a_rates": {
        "on_campus_research": {
            "rate": 0.56,
            "description": "56% of MTDC for on-campus organized research",
        },
        "off_campus_research": {
            "rate": 0.26,
            "description": "26% of MTDC for off-campus organized research",
        },
        "instruction": {
            "rate": 0.50,
            "description": "50% of MTDC for instruction/training",
        },
        "other_sponsored": {
            "rate": 0.36,
            "description": "36% of MTDC for other sponsored activities",
        },
        "base": "MTDC (Modified Total Direct Costs)",
        "note": (
            "Rates are periodically renegotiated with DHHS. Always verify "
            "current rates with OSPA before proposal submission."
        ),
    },
    "fringe_rates": {
        "note": (
            "Fringe benefit rates are published annually by UK. Rates vary "
            "by employee category. Check the OSPA Frequently Needed Information "
            "page for current rates."
        ),
        "url": "https://www.research.uky.edu/office-sponsored-projects-administration",
    },
    "fiscal_year": "July 1 – June 30",
    "cayuse_info": {
        "description": (
            "Cayuse 424 / Cayuse Proposals (S2S) is UK's electronic proposal "
            "preparation and submission platform. Requires LinkBlue login."
        ),
        "access_note": (
            "Not all personnel are auto-provisioned. Students, some postdocs, "
            "and new employees may need manual addition — contact ospa@uky.edu."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════
# PROJECT LIFECYCLE (7 STEPS)
# ═══════════════════════════════════════════════════════════════════════

PROJECT_LIFECYCLE = [
    {
        "step": 1,
        "name": "Develop Idea & Find Funding",
        "description": "Identify research questions and locate appropriate funding opportunities.",
        "primary_office": "PDO",
        "pi_responsibilities": [
            "Define research scope and objectives",
            "Request PDO funding search or browse Pivot-RP",
            "Subscribe to PDO funding alerts",
        ],
        "office_support": {
            "PDO": "Funding searches, Pivot-RP access, funding alerts, collaborator identification",
        },
    },
    {
        "step": 2,
        "name": "Pre-Proposal Activities",
        "description": "Interpret solicitation, assess eligibility, plan proposal.",
        "primary_office": "PDO / CGS",
        "pi_responsibilities": [
            "Review solicitation requirements",
            "Submit PIF to CGS (30 days before deadline)",
            "Identify collaborators and sub-recipients",
        ],
        "office_support": {
            "PDO": "Interpret guidelines, advise on competitiveness, limited submission management",
            "CGS": "Discuss timelines, begin administrative planning",
        },
    },
    {
        "step": 3,
        "name": "Draft Proposal",
        "description": "Write narrative, develop budget, prepare required documents.",
        "primary_office": "PDO (narrative) / CGS (budget)",
        "pi_responsibilities": [
            "Write technical narrative and specific aims",
            "Provide personnel info and effort levels for budget",
            "Obtain letters of support/collaboration",
        ],
        "office_support": {
            "PDO": "Critique narratives, review biosketches, facilities descriptions",
            "CGS": "Develop budget and justification, complete admin components, coordinate subs",
        },
    },
    {
        "step": 4,
        "name": "Prepare & Submit Proposal",
        "description": "Finalize, obtain approvals, submit to sponsor.",
        "primary_office": "CGS → OSPA",
        "pi_responsibilities": [
            "Review and approve final budget and narrative",
            "Sign/approve IAF",
            "Ensure all documents meet sponsor requirements",
        ],
        "office_support": {
            "CGS": "Prepare and route IAF, compile all documents, verify completeness",
            "OSPA": "Final compliance review, official submission to sponsor",
        },
        "key_deadlines": {
            "IAF to OSPA": "3 business days before sponsor deadline",
            "College-specific": "5-14 business days before OSPA deadline (varies by college)",
        },
    },
    {
        "step": 5,
        "name": "Follow-up for Pending Award",
        "description": "Monitor status, respond to agency requests.",
        "primary_office": "OSPA / CGS",
        "pi_responsibilities": [
            "Respond to agency questions or requests for additional info",
            "Prepare Just-In-Time (JIT) materials if requested",
            "Update Current & Pending support",
        ],
        "office_support": {
            "CGS": "Prepare JIT materials, update C&P documentation",
            "OSPA": "Monitor status, communicate with program officers",
        },
    },
    {
        "step": 6,
        "name": "Activate Award",
        "description": "Accept award, set up accounts, begin work.",
        "primary_office": "OSPA",
        "pi_responsibilities": [
            "Review award terms and conditions",
            "Provide account setup information",
            "Begin hiring and procurement",
        ],
        "office_support": {
            "OSPA": "Negotiate and accept award, establish account number",
            "CGS": "Support setup documentation, verify budget alignment",
        },
    },
    {
        "step": 7,
        "name": "Manage Award",
        "description": "Monitor spending, report progress, manage modifications.",
        "primary_office": "CGS / OSPA",
        "pi_responsibilities": [
            "Monitor spending against budget",
            "Submit technical progress reports",
            "Request modifications as needed",
            "Prepare for closeout",
        ],
        "office_support": {
            "CGS": (
                "Monthly reconciliation, cost transfers, financial reporting, "
                "subcontract monitoring, carryforward, closeout"
            ),
            "OSPA": "Contract modifications, prior approvals, compliance, closeout reports",
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════
# QUESTION ROUTING — Maps topics to the right office
# ═══════════════════════════════════════════════════════════════════════

QUESTION_ROUTING = {
    # OSPA topics
    "submit proposal": {"office": "OSPA", "detail": "OSPA is the only office that can officially submit proposals to sponsors."},
    "proposal submission": {"office": "OSPA", "detail": "OSPA handles official submission after compliance review."},
    "accept award": {"office": "OSPA", "detail": "OSPA negotiates and formally accepts all awards."},
    "award acceptance": {"office": "OSPA", "detail": "Only OSPA can accept awards on behalf of UK."},
    "contract": {"office": "OSPA", "detail": "OSPA Contracts & Subawards team handles all contract negotiations."},
    "subaward": {"office": "OSPA", "detail": "OSPA handles subaward/subcontract execution. CGS handles monitoring."},
    "subcontract": {"office": "OSPA", "detail": "OSPA executes subcontracts. Use the Online Subagreement Request."},
    "compliance": {"office": "OSPA", "detail": "OSPA handles compliance: export control, COI, foreign influence, data security."},
    "export control": {"office": "OSPA", "detail": "OSPA manages export control compliance reviews."},
    "conflict of interest": {"office": "OSPA", "detail": "Financial disclosure/COI managed by OSPA."},
    "clinical trial": {"office": "OSPA", "detail": "Clinical trial agreements handled by OSPA Contracts team."},
    "departing investigator": {"office": "OSPA", "detail": "OSPA manages departing PI MOUs and award transfers."},
    "account setup": {"office": "OSPA", "detail": "OSPA establishes account numbers through Research Financial Services."},
    "cayuse": {"office": "OSPA", "detail": "Cayuse access issues → contact ospa@uky.edu."},

    # CGS topics
    "budget": {"office": "CGS", "detail": "CGS develops budgets and budget justifications in consultation with PIs."},
    "iaf": {"office": "CGS", "detail": "CGS prepares and routes the Internal Approval Form (IAF/eIAF)."},
    "internal approval": {"office": "CGS", "detail": "CGS handles the IAF process. Route through your CGS hub."},
    "pif": {"office": "CGS", "detail": "Submit the Proposal Initiation Form to CGS 30 days before deadline."},
    "cost transfer": {"office": "CGS", "detail": "CGS processes payroll and non-payroll cost transfers."},
    "reconciliation": {"office": "CGS", "detail": "CGS handles monthly expense reconciliation on active awards."},
    "financial report": {"office": "CGS", "detail": "CGS prepares sponsor-required financial reports."},
    "no-cost extension": {"office": "CGS", "detail": "Request through CGS using the Request for Action/Revision Form."},
    "budget revision": {"office": "CGS", "detail": "CGS handles budget modifications and re-budgeting."},
    "cost sharing": {"office": "CGS", "detail": "CGS monitors and documents cost-sharing commitments."},
    "f&a waiver": {"office": "CGS", "detail": "F&A waiver requests coordinated through CGS."},
    "closeout": {"office": "CGS/OSPA", "detail": "Financial closeout → CGS. Non-financial reports/final deliverables → OSPA."},
    "carryforward": {"office": "CGS", "detail": "CGS handles carryforward procedures for unspent funds."},
    "spending": {"office": "CGS", "detail": "CGS provides financial forecasts and spending analysis."},
    "effort reporting": {"office": "CGS", "detail": "CGS assists with effort certification and off-campus determinations."},
    "just in time": {"office": "CGS", "detail": "CGS prepares Just-In-Time (JIT) materials when requested by agency."},
    "jit": {"office": "CGS", "detail": "CGS prepares Just-In-Time (JIT) materials."},

    # PDO topics
    "funding search": {"office": "PDO", "detail": "Submit a funding search request form to PDO. Results in ~3 weeks."},
    "find funding": {"office": "PDO", "detail": "PDO conducts personalized funding searches and manages Pivot-RP access."},
    "pivot": {"office": "PDO", "detail": "PDO manages Pivot-RP database access for funding discovery."},
    "proposal review": {"office": "PDO", "detail": "PDO reviews proposal narratives for clarity and competitiveness."},
    "proposal critique": {"office": "PDO", "detail": "PDO offers free proposal critique services."},
    "limited submission": {"office": "PDO", "detail": "PDO manages internal competitions when sponsors limit applications per institution."},
    "facilities description": {"office": "PDO", "detail": "PDO maintains a library of UK facilities descriptions (LinkBlue login required)."},
    "collaborator": {"office": "PDO", "detail": "PDO uses Scholars@UK and SPIFi to identify potential collaborators."},
    "resubmission": {"office": "PDO", "detail": "PDO advises on resubmission strategy and reviewer critique analysis."},
    "broader impacts": {"office": "PDO", "detail": "PDO provides broader impacts resources and guidance."},
    "data management plan": {"office": "PDO", "detail": "PDO has DMP templates for NSF, NIH, NEH, NOAA, and more."},
    "biosketch": {"office": "PDO", "detail": "PDO reviews biosketches. Use SciENcv for preparation."},
    "training": {"office": "PDO", "detail": "PDO offers workshops, Friday High-Five sessions, and bootcamps."},
    "workshop": {"office": "PDO", "detail": "PDO training includes Friday High-Five 45-min virtual sessions."},
}


# ═══════════════════════════════════════════════════════════════════════
# DEADLINE RULES
# ═══════════════════════════════════════════════════════════════════════

DEADLINE_RULES = {
    "pif_to_cgs": {
        "name": "PIF Submission to CGS",
        "business_days_before_sponsor": 30,
        "description": "Proposal Initiation Form due to CGS 30 business days before sponsor deadline.",
    },
    "iaf_to_ospa": {
        "name": "IAF to OSPA",
        "business_days_before_sponsor": 3,
        "description": "Approved IAF and complete proposal due to OSPA 3 business days before sponsor deadline.",
    },
    "college_iaf": {
        "name": "College-Level IAF Deadline",
        "business_days_before_ospa": "5-14 (varies by college)",
        "description": (
            "Most colleges require the IAF 5-14 business days before the OSPA "
            "deadline. Check with your department/college for specific requirements."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════
# SEARCH HELPER — Builds a flat searchable index
# ═══════════════════════════════════════════════════════════════════════

def build_search_index() -> List[Dict[str, Any]]:
    """
    Build a flat list of searchable entries from all knowledge base sections.
    Each entry has: category, title, content, office, tags, url (optional).
    """
    entries = []

    # Office profiles
    for abbr, office in OFFICES.items():
        handles_text = "; ".join(office["handles"])
        entries.append({
            "category": "office",
            "title": f"{abbr} — {office['full_name']}",
            "content": f"{office['role_summary']} Handles: {handles_text}",
            "office": abbr,
            "tags": [abbr.lower(), "office", "contact"],
            "url": office.get("url"),
            "email": office.get("email"),
            "phone": office.get("phone"),
        })

    # Forms
    for form in FORMS_AND_TEMPLATES:
        entries.append({
            "category": "form",
            "title": form["name"],
            "content": form["purpose"] + (f" Deadline: {form.get('deadline_rule', '')}" if form.get("deadline_rule") else ""),
            "office": form["office"],
            "tags": form.get("tags", []) + ["form", "template"],
            "url": form.get("url"),
        })

    # Policies
    for policy in POLICIES:
        entries.append({
            "category": "policy",
            "title": policy["name"],
            "content": policy["description"],
            "office": policy["office"],
            "tags": policy.get("tags", []) + ["policy", "regulation"],
            "url": policy.get("url"),
        })

    # Lifecycle steps
    for step in PROJECT_LIFECYCLE:
        support_text = "; ".join(f"{k}: {v}" for k, v in step["office_support"].items())
        entries.append({
            "category": "process",
            "title": f"Step {step['step']}: {step['name']}",
            "content": f"{step['description']} {support_text}",
            "office": step["primary_office"],
            "tags": ["lifecycle", "process", f"step-{step['step']}"],
        })

    # Institutional info
    entries.append({
        "category": "institutional",
        "title": "UK Institutional Identifiers",
        "content": (
            f"Legal Name: {INSTITUTIONAL_INFO['legal_name']}; "
            f"UEI: {INSTITUTIONAL_INFO['uei_number']}; "
            f"DUNS: {INSTITUTIONAL_INFO['duns_number']}; "
            f"EIN: {INSTITUTIONAL_INFO['ein']}; "
            f"CAGE: {INSTITUTIONAL_INFO['cage_code']}; "
            f"Congressional District: {INSTITUTIONAL_INFO['congressional_district']}"
        ),
        "office": "OSPA",
        "tags": ["institutional", "identifiers", "boilerplate", "duns", "uei", "ein"],
    })

    # F&A rates
    for activity, info in INSTITUTIONAL_INFO["f_and_a_rates"].items():
        if isinstance(info, dict) and "rate" in info:
            entries.append({
                "category": "rate",
                "title": f"F&A Rate — {activity.replace('_', ' ').title()}",
                "content": info["description"],
                "office": "OSPA",
                "tags": ["f&a", "rate", "indirect-cost", activity],
            })

    return entries


# Pre-build the search index at import time
SEARCH_INDEX = build_search_index()
