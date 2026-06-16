"""Driver protocol — the surface both modes implement (T010 / FR-030).

One harness core, two drivers. The in-process driver is the CI merge gate; the
external driver is the opt-in live-network surface. Both return the SAME
``CapturedEvidence`` shape so the SAME deterministic checks run against either.
"""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from verification.evidence import CapturedEvidence
from verification.isolation import Principal
from verification.scenarios import Scenario


@runtime_checkable
class Driver(Protocol):
    """Minimal driver surface consumed by the runner and the authority checks."""

    mode: str       # in_process | external
    auth_mode: str  # real_keycloak | mock_inprocess

    async def setup(self) -> None:
        """Prepare the driver (boot orchestrator / open connections)."""

    async def teardown(self) -> None:
        """Release resources and purge namespaced harness data (FR-031)."""

    async def run_scenario(self, scenario: Scenario) -> CapturedEvidence:
        """Authenticate -> upload -> query -> capture for one scenario, returning
        the evidence (messages, components, workspace, audit, chain status)."""
        ...

    # --- Authority probes (US2). Optional; in-process implements all. ---

    async def upload_as(self, principal: Principal, fixture: Any) -> Dict[str, Any]:
        """Upload a fixture as ``principal``; return the attachment metadata."""
        ...

    async def reference_attachment_as(
        self, principal: Principal, attachment_id: str, filename: str
    ) -> CapturedEvidence:
        """Send a turn as ``principal`` referencing ``attachment_id`` (which may
        belong to someone else). Used to prove cross-user refusal."""
        ...

    async def set_scope(
        self, principal: Principal, agent_id: str, scope: str, enabled: bool
    ) -> None:
        """Enable/disable a capability scope for ``principal``'s agent."""
        ...
