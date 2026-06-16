"""Scenario catalogue (T009 / T016).

A ``Scenario`` is one persona-conditioned flow: a file, a query, the acting
principal, the run mode, and the properties expected to hold. It is the atomic
unit the runner plans, drives, and verifies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from verification.isolation import Principal, make_principal
from verification.personas import Persona, all_personas

# Property keys (match Check.property).
TANGIBLE_UI = "tangible_ui"
DELEGATED_AUTHORITY = "delegated_authority"
BACKEND_ONLY_UI = "backend_only_ui"


@dataclass
class Scenario:
    """One persona-conditioned verification flow."""

    scenario_id: str
    persona: Persona
    principal: Principal
    auth_mode: str  # real_keycloak | mock_inprocess
    expected_properties: List[str] = field(default_factory=list)
    warrants_ui: bool = True

    @property
    def query(self) -> str:
        return self.persona.query


def build_scenarios(
    run_id: str,
    auth_mode: str,
    persona_keys: Optional[List[str]] = None,
    properties: Optional[List[str]] = None,
) -> List[Scenario]:
    """Build one scenario per persona (US1's per-persona coverage).

    Args:
        run_id: Run namespace (for principal ids).
        auth_mode: ``real_keycloak`` or ``mock_inprocess``.
        persona_keys: Restrict to these personas (None = all).
        properties: Properties expected to hold (default: all three).
    """
    props = properties or [TANGIBLE_UI, BACKEND_ONLY_UI]
    out: List[Scenario] = []
    for persona in all_personas(persona_keys):
        principal = make_principal(run_id, persona.key, role="primary",
                                   roles=list(persona.roles))
        out.append(
            Scenario(
                scenario_id=f"{persona.key}:primary",
                persona=persona,
                principal=principal,
                auth_mode=auth_mode,
                expected_properties=list(props),
                warrants_ui=persona.warrants_ui,
            )
        )
    return out
