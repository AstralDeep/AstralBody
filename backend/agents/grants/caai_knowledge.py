#!/usr/bin/env python3
"""
UKy Center for Applied AI (CAAI) Knowledge Base.

Contains mission, expertise, project history, and matching criteria
for evaluating grant opportunity alignment.
"""
from typing import List, Dict, Any


# ── Mission & Overview ──────────────────────────────────────────────────

CAAI_MISSION = {
    "name": "Center for Applied AI",
    "full_name": "University of Kentucky Center for Applied Artificial Intelligence",
    "parent_org": "Institute for Biomedical Informatics (IBI)",
    "university": "University of Kentucky",
    "founded": 2023,
    "director": "Dr. Cody Bumgardner",
    "mission": (
        "Bridge the gap between the vast potential of Artificial Intelligence "
        "and its practical, real-world applications. Drive innovation, solve "
        "complex problems, and improve outcomes across diverse disciplines, "
        "with a significant focus on biomedical informatics, healthcare, and "
        "translational science."
    ),
    "vision": (
        "To be a leading center for applied AI research and development, "
        "transforming how AI is adopted and deployed across healthcare, "
        "agriculture, education, and public service in Kentucky and beyond."
    ),
    "stats": {
        "total_award_participation": "$80M",
        "funded_projects": 26,
        "completed_projects": 65,
        "partners": 43,
        "collaborators": 120,
        "funding_rate": ">50%",
    },
}


# ── Core Expertise Areas ────────────────────────────────────────────────

EXPERTISE_AREAS = [
    {
        "area": "Large Language Models (LLM)",
        "description": (
            "Fine-tuning, deployment, and application of LLMs for "
            "domain-specific tasks including clinical documentation, "
            "agricultural guidance, and research assistance."
        ),
        "tools_built": ["LLM Factory", "CAT-Talk"],
        "keywords": [
            "natural language processing", "NLP", "LLM", "GPT",
            "fine-tuning", "text generation", "language model",
            "transformer", "large language model", "generative AI",
            "retrieval augmented generation", "RAG",
        ],
    },
    {
        "area": "Data Science & Machine Learning",
        "description": (
            "Predictive modeling, classification, and statistical analysis "
            "across healthcare and other domains."
        ),
        "tools_built": ["CLASSify", "SmartState"],
        "keywords": [
            "machine learning", "predictive modeling", "classification",
            "data science", "statistical analysis", "deep learning",
            "neural network", "supervised learning", "unsupervised learning",
            "reinforcement learning",
        ],
    },
    {
        "area": "Computer Vision",
        "description": (
            "Image analysis, medical imaging, and visual recognition systems "
            "for healthcare and agricultural applications."
        ),
        "tools_built": [],
        "keywords": [
            "computer vision", "image analysis", "medical imaging",
            "object detection", "image classification", "segmentation",
            "convolutional neural network", "CNN",
        ],
    },
    {
        "area": "Biomedical Informatics",
        "description": (
            "AI applications in healthcare, clinical data management, "
            "EHR integration, and translational science."
        ),
        "tools_built": [],
        "keywords": [
            "biomedical", "clinical", "healthcare AI", "EHR",
            "medical informatics", "translational science",
            "precision medicine", "clinical decision support",
            "health informatics", "electronic health record",
        ],
    },
    {
        "area": "Distributed Systems & HPC",
        "description": (
            "High-performance computing infrastructure for AI workloads, "
            "GPU cluster management, and scalable model training."
        ),
        "tools_built": [],
        "keywords": [
            "distributed systems", "HPC", "high-performance computing",
            "GPU computing", "cloud computing", "infrastructure",
            "parallel computing", "cluster computing",
        ],
    },
    {
        "area": "Agricultural AI",
        "description": (
            "AI applications for agriculture, extension services, "
            "and rural communities in Kentucky and beyond."
        ),
        "tools_built": ["AgriGuide"],
        "keywords": [
            "agriculture", "farming", "crop", "extension",
            "rural", "food security", "precision agriculture",
            "agri-tech", "agricultural technology",
        ],
    },
]


# ── Key Personnel ───────────────────────────────────────────────────────

KEY_PERSONNEL = [
    {
        "name": "Dr. Cody Bumgardner",
        "title": "Director, Center for Applied AI; Assistant Dean for AI",
        "expertise": [
            "distributed systems", "high-performance computing",
            "AI in healthcare", "clinical data management",
        ],
        "years_experience": 20,
    },
    {
        "name": "Dr. Ken Calvert",
        "title": "Advisor — Research and Industry",
        "expertise": [
            "computer networking", "cybersecurity", "research strategy",
        ],
        "notable": "IEEE Fellow, former NSF Division Director ($230M research budget)",
    },
    {
        "name": "Melissa Rowe",
        "title": "Advisor — Technology Industry",
        "expertise": ["technology strategy", "business development"],
        "notable": "30 years in tech (AWS, Salesforce, Dell)",
    },
]


# ── Project History (representative funded projects) ────────────────────

PROJECT_HISTORY = [
    {
        "title": "Neonatal Ventilator Weaning Prediction",
        "domain": "Healthcare / Neonatal Care",
        "agency": "NIH",
        "keywords": [
            "machine learning", "neonatal", "ventilator",
            "predictive modeling", "clinical decision support",
        ],
        "description": (
            "ML models analyzing ventilator and oxygen monitor data "
            "to predict pre-term baby extubation readiness."
        ),
    },
    {
        "title": "Opioid Incident Forecasting",
        "domain": "Public Health",
        "agency": "NIH",
        "keywords": [
            "forecasting", "opioid", "emergency response",
            "public health", "time series",
        ],
        "description": (
            "Using ambulance and emergency data to forecast "
            "opioid-related incidents across Kentucky."
        ),
    },
    {
        "title": "AgriGuide — Agricultural AI Assistant",
        "domain": "Agriculture",
        "agency": "USDA",
        "keywords": [
            "agriculture", "NLP", "chatbot", "extension services",
            "large language model",
        ],
        "description": (
            "AI-powered assistant for Kentucky-specific "
            "agricultural guidance using LLMs."
        ),
    },
    {
        "title": "CAT-Talk Speech Transcription",
        "domain": "NLP / Healthcare",
        "agency": "NIH",
        "keywords": [
            "speech-to-text", "transcription", "NLP",
            "clinical documentation", "natural language processing",
        ],
        "description": (
            "In-house speech-to-text transcription service "
            "for clinical and research use."
        ),
    },
    {
        "title": "LLM Factory — Custom Model Fine-tuning",
        "domain": "AI Infrastructure",
        "agency": "NSF",
        "keywords": [
            "LLM", "fine-tuning", "model training",
            "AI democratization", "large language model",
        ],
        "description": (
            "Platform for fine-tuning large language models "
            "to domain-specific needs."
        ),
    },
    {
        "title": "NAIRR Pilot — Democratizing AI Training",
        "domain": "AI Infrastructure / Education",
        "agency": "NSF",
        "keywords": [
            "NAIRR", "AI training", "democratization",
            "education", "workforce", "national AI research resource",
        ],
        "description": (
            "Collaborative research project to democratize "
            "AI training and access statewide."
        ),
    },
    {
        "title": "CLASSify — ML Classifier Training",
        "domain": "Data Science",
        "agency": "Internal",
        "keywords": [
            "classification", "machine learning",
            "self-service", "training", "no-code ML",
        ],
        "description": (
            "Self-service platform for users to train "
            "machine learning classifiers without coding."
        ),
    },
    {
        "title": "SmartState — State-Level Data Analytics",
        "domain": "Government / Analytics",
        "agency": "State",
        "keywords": [
            "government", "analytics", "data visualization",
            "dashboard", "state government",
        ],
        "description": (
            "AI-driven analytics platform for state-level "
            "data analysis and reporting."
        ),
    },
]


# ── Grant Focus Preferences ────────────────────────────────────────────

GRANT_PREFERENCES = {
    "preferred_agencies": ["NSF", "NIH", "DOE", "DoD"],
    "preferred_amount_min": 500_000,
    "preferred_types": [
        "center grants",
        "research infrastructure",
        "AI institutes",
        "collaborative research",
        "training grants",
        "workforce development",
        "equipment grants",
        "planning grants for centers",
        "cooperative agreements",
    ],
    "strong_match_keywords": [
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "natural language processing",
        "computer vision",
        "large language model",
        "biomedical informatics",
        "health AI",
        "clinical AI",
        "precision medicine",
        "translational science",
        "AI workforce",
        "AI education",
        "AI infrastructure",
        "high-performance computing",
        "NAIRR",
        "agricultural AI",
        "rural AI",
        "AI for social good",
        "generative AI",
        "responsible AI",
        "trustworthy AI",
    ],
    "moderate_match_keywords": [
        "data science",
        "big data",
        "cloud computing",
        "cybersecurity",
        "networking",
        "IoT",
        "healthcare informatics",
        "electronic health records",
        "drug discovery",
        "genomics",
        "bioinformatics",
        "robotics",
        "automation",
        "smart manufacturing",
    ],
}


# ── Agency Code Mappings (for grants.gov API) ───────────────────────────

AGENCY_CODES = {
    "NSF": "NSF",
    "NIH": "HHS-NIH",
    "DOE": "DOE",
    "DOD": "DOD",
    "DARPA": "DOD-DARPA",
    "ARPA-H": "HHS-ARPA-H",
    "USDA": "USDA",
    "NASA": "NASA",
    "ED": "ED",
}


# ── Match Scoring ──────────────────────────────────────────────────────


def compute_match_score(
    grant_title: str,
    grant_description: str,
    grant_keywords: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Compute a match score (0-100) between a grant opportunity and CAAI
    capabilities.  Returns score, matching areas, and rationale.
    """
    if grant_keywords is None:
        grant_keywords = []

    title_lower = grant_title.lower()
    desc_lower = grant_description.lower()
    kw_lower = [k.lower() for k in grant_keywords]
    all_text = f"{title_lower} {desc_lower} {' '.join(kw_lower)}"

    score = 0.0
    matching_areas: List[str] = []
    strong_matches: List[str] = []
    moderate_matches: List[str] = []

    # Strong keyword matches (3 pts each)
    for kw in GRANT_PREFERENCES["strong_match_keywords"]:
        if kw.lower() in all_text:
            strong_matches.append(kw)
            score += 3

    # Moderate keyword matches (1.5 pts each)
    for kw in GRANT_PREFERENCES["moderate_match_keywords"]:
        if kw.lower() in all_text:
            moderate_matches.append(kw)
            score += 1.5

    # Expertise area alignment (5 pts per area)
    for area in EXPERTISE_AREAS:
        for kw in area["keywords"]:
            if kw.lower() in all_text:
                matching_areas.append(area["area"])
                score += 5
                break

    # Past project overlap (2 pts per matching project)
    matching_projects: List[str] = []
    for project in PROJECT_HISTORY:
        for kw in project["keywords"]:
            if kw.lower() in all_text:
                matching_projects.append(project["title"])
                score += 2
                break

    # Normalize to 0-100
    score = min(100.0, score)

    # Determine match tier
    if score >= 70:
        tier = "Excellent Match"
    elif score >= 50:
        tier = "Strong Match"
    elif score >= 30:
        tier = "Moderate Match"
    elif score >= 15:
        tier = "Possible Match"
    else:
        tier = "Low Match"

    return {
        "score": round(score, 1),
        "tier": tier,
        "matching_expertise_areas": matching_areas,
        "matching_projects": matching_projects,
        "strong_keyword_matches": strong_matches,
        "moderate_keyword_matches": moderate_matches,
    }
