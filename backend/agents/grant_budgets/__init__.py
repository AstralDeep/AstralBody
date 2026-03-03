"""
Grant Budgets Agent package for AstralBody system.

Financial specialist for grant budget estimation, informed by
CGS documentation, NSF/NIH PAPPG, and institutional rate structures.
Also provides UKy research administration Q&A for OSPA, CGS, and PDO.
"""

from agents.grant_budgets.grant_budgets_agent import GrantBudgetsAgent
from agents.grant_budgets.mcp_server import MCPServer
from agents.grant_budgets.mcp_tools import (
    analyze_cover_letter,
    suggest_budget_items,
    calculate_salary_fte,
    calculate_travel_costs,
    estimate_equipment_costs,
    calculate_fa_costs,
    generate_cgs_budget,
    get_budget_guidelines,
    search_research_admin,
    find_office_contact,
    calculate_submission_deadlines,
    get_institutional_info,
    lookup_forms_templates,
    TOOL_REGISTRY,
)

__all__ = [
    'GrantBudgetsAgent',
    'MCPServer',
    'analyze_cover_letter',
    'suggest_budget_items',
    'calculate_salary_fte',
    'calculate_travel_costs',
    'estimate_equipment_costs',
    'calculate_fa_costs',
    'generate_cgs_budget',
    'get_budget_guidelines',
    'search_research_admin',
    'find_office_contact',
    'calculate_submission_deadlines',
    'get_institutional_info',
    'lookup_forms_templates',
    'TOOL_REGISTRY',
]

__version__ = '1.1.0'
