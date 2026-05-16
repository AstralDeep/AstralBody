"""REST API for the onboarding subsystem (feature 005-tooltips-tutorial).

Two routers:

* ``onboarding_user_router`` — per-user state read/write and the
  ``GET /api/tutorial/steps`` step list. ``actor_user_id`` is exclusively
  derived from the validated JWT (mirrors feature 003's strict per-user
  policy). Any request that includes a user-override query parameter is
  rejected with HTTP 400.
* ``onboarding_admin_router`` — admin-gated step CRUD, archive/restore,
  and revision history. Gated by the existing ``verify_admin`` dependency
  from :mod:`backend.orchestrator.auth`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response

from orchestrator.auth import (
    get_current_user_payload,
    require_user_id,
    verify_admin,
    _extract_roles,  # type: ignore[attr-defined]
)

from .recorder import (
    record_onboarding_completed,
    record_onboarding_replayed,
    record_onboarding_skipped,
    record_onboarding_started,
    record_tutorial_step_edited,
)
from .repository import (
    DuplicateSlug,
    OnboardingRepository,
    StepNotFound,
)
from .schemas import (
    AdminTutorialStepCreateRequest,
    AdminTutorialStepListResponse,
    AdminTutorialStepUpdateRequest,
    OnboardingStateResponse,
    OnboardingStateUpdateRequest,
    RevisionListResponse,
    TutorialStepDTO,
    TutorialStepListResponse,
)

logger = logging.getLogger("Onboarding.API")

onboarding_user_router = APIRouter(tags=["Onboarding"])
onboarding_admin_router = APIRouter(prefix="/api/admin/tutorial", tags=["Onboarding Admin"])


# Query/path parameters that must NEVER be honored as a user-id override.
# Feature 003 / FR-007 / FR-019 — the owning user is exclusively the JWT subject.
_FORBIDDEN_QUERY_PARAMS = frozenset(
    {"actor_user_id", "user_id", "user", "sub", "as_user", "owner_id"}
)


def _reject_user_overrides(request: Request) -> None:
    """Raise 400 if the caller includes any user-id override parameter."""
    for key in request.query_params.keys():
        if key.lower() in _FORBIDDEN_QUERY_PARAMS:
            raise HTTPException(
                status_code=400,
                detail=f"parameter {key!r} is not allowed; user is derived from the JWT",
            )


def _orchestrator(request: Request):
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        root_app = getattr(request.app, "_root_app", None) or request.app
        orch = getattr(root_app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orch


def _repo(request: Request) -> OnboardingRepository:
    orch = _orchestrator(request)
    repo = getattr(orch, "onboarding_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Onboarding subsystem not initialized")
    return repo


def _principal_of(payload: dict) -> str:
    return payload.get("preferred_username") or payload.get("sub") or "unknown"


def _is_admin(payload: dict) -> bool:
    if not payload:
        return False
    roles = _extract_roles(payload)
    return "admin" in roles


# ---------------------------------------------------------------------------
# User-side endpoints
# ---------------------------------------------------------------------------

@onboarding_user_router.get(
    "/api/onboarding/state",
    response_model=OnboardingStateResponse,
    summary="Get the authenticated user's onboarding state",
)
async def get_onboarding_state(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    _reject_user_overrides(request)
    return _repo(request).get_state(user_id)


@onboarding_user_router.put(
    "/api/onboarding/state",
    response_model=OnboardingStateResponse,
    summary="Update the authenticated user's onboarding state",
)
async def put_onboarding_state(
    body: OnboardingStateUpdateRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    _reject_user_overrides(request)
    repo = _repo(request)
    is_admin_caller = _is_admin(payload)

    # Validate last_step_id, if supplied: it must reference a non-archived
    # step the caller is allowed to see.
    if body.last_step_id is not None:
        audience = repo.get_step_audience(body.last_step_id)
        if audience is None:
            raise HTTPException(
                status_code=400,
                detail="last_step_id does not reference a visible step",
            )
        if audience == "admin" and not is_admin_caller:
            raise HTTPException(
                status_code=400,
                detail="last_step_id references an admin-only step",
            )

    # Reject the disallowed terminal → in_progress transition (FR-001).
    prior = repo.get_state(user_id)
    if (
        body.status == "in_progress"
        and prior.status in ("completed", "skipped")
    ):
        raise HTTPException(
            status_code=409,
            detail="cannot transition from terminal state to in_progress; use /replay instead",
        )

    new_state, prior_status = repo.upsert_state(
        user_id=user_id, status=body.status, last_step_id=body.last_step_id,
    )

    # Audit emission — *after* the DB write succeeds, so a queued audit
    # always reflects a real persisted state change.
    auth_principal = _principal_of(payload)
    last_slug = new_state.last_step_slug
    if (prior_status is None or prior_status == "not_started") and body.status == "in_progress":
        await record_onboarding_started(
            actor_user_id=user_id, auth_principal=auth_principal, step_slug=last_slug,
        )
    if body.status == "completed" and prior_status != "completed":
        await record_onboarding_completed(
            actor_user_id=user_id, auth_principal=auth_principal, last_step_slug=last_slug,
        )
    if body.status == "skipped" and prior_status != "skipped":
        await record_onboarding_skipped(
            actor_user_id=user_id, auth_principal=auth_principal, last_step_slug=last_slug,
        )

    return new_state


@onboarding_user_router.post(
    "/api/onboarding/replay",
    status_code=204,
    summary="Record that the authenticated user activated the replay affordance",
)
async def post_onboarding_replay(
    request: Request,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    _reject_user_overrides(request)
    repo = _repo(request)
    state = repo.get_state(user_id)
    await record_onboarding_replayed(
        actor_user_id=user_id,
        auth_principal=_principal_of(payload),
        prior_status=state.status,
    )
    return Response(status_code=204)


@onboarding_user_router.post(
    "/api/onboarding/dismiss",
    response_model=OnboardingStateResponse,
    summary="Record a 'not now' dismissal — cooldown before prompting again",
)
async def post_dismiss_onboarding(
    request: Request,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    """
    US-17: Record a soft dismissal. After 2 dismissals the tour is permanently skipped.
    Until then, the tour will re-prompt after a 24-hour cooldown (enforced by the frontend).
    """
    _reject_user_overrides(request)
    repo = _repo(request)
    new_state = repo.record_dismissal(user_id, max_dismissals=2)
    logger.info(
        "User %s dismissed tutorial (count=%d, status=%s)",
        user_id, new_state.dismiss_count, new_state.status,
    )
    return new_state


@onboarding_user_router.get(
    "/api/tutorial/steps",
    response_model=TutorialStepListResponse,
    summary="List the tutorial steps applicable to the authenticated user",
)
async def list_tutorial_steps(
    request: Request,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    _reject_user_overrides(request)
    repo = _repo(request)
    include_admin = _is_admin(payload)
    steps = repo.list_steps_for_user(include_admin=include_admin)
    # User view strips admin-only fields (archived_at, updated_at).
    return JSONResponse(
        content={"steps": [s.to_user_view() for s in steps]},
    )


# ---------------------------------------------------------------------------
# Admin-side endpoints
# ---------------------------------------------------------------------------

@onboarding_admin_router.get(
    "/steps",
    response_model=AdminTutorialStepListResponse,
    summary="List every tutorial step (admin)",
)
async def list_steps_admin(
    request: Request,
    include_archived: bool = Query(True),
    _admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    steps = repo.list_all_steps(include_archived=include_archived)
    return AdminTutorialStepListResponse(steps=steps)


@onboarding_admin_router.post(
    "/steps",
    response_model=TutorialStepDTO,
    status_code=201,
    summary="Create a new tutorial step (admin)",
)
async def create_step_admin(
    body: AdminTutorialStepCreateRequest,
    request: Request,
    admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    actor = admin.get("sub") or "admin"
    try:
        dto = repo.create_step(
            editor_user_id=actor,
            slug=body.slug,
            audience=body.audience,
            display_order=body.display_order,
            target_kind=body.target_kind,
            target_key=body.target_key,
            title=body.title,
            body=body.body,
        )
    except DuplicateSlug:
        raise HTTPException(status_code=409, detail="DUPLICATE_SLUG")

    await record_tutorial_step_edited(
        actor_user_id=actor,
        auth_principal=_principal_of(admin),
        step_id=dto.id,
        step_slug=dto.slug,
        change_kind="create",
        changed_fields=[
            "slug", "audience", "display_order", "target_kind", "target_key",
            "title", "body",
        ],
    )
    return dto


@onboarding_admin_router.put(
    "/steps/{step_id}",
    response_model=TutorialStepDTO,
    summary="Update a tutorial step (partial; admin)",
)
async def update_step_admin(
    step_id: int,
    body: AdminTutorialStepUpdateRequest,
    request: Request,
    admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    actor = admin.get("sub") or "admin"

    # Build the patch dict from fields the caller actually set.
    patch: Dict[str, Any] = {}
    if "audience" in body.model_fields_set:
        patch["audience"] = body.audience
    if "display_order" in body.model_fields_set:
        patch["display_order"] = body.display_order
    if "target_kind" in body.model_fields_set:
        patch["target_kind"] = body.target_kind
    if "target_key" in body.model_fields_set:
        patch["target_key"] = body.target_key
    if "title" in body.model_fields_set:
        patch["title"] = body.title
    if "body" in body.model_fields_set:
        patch["body"] = body.body

    # Cross-field validation: target_kind / target_key consistency must hold
    # *after* the patch is applied. Fetch current row to validate the merged shape.
    current = repo.get_step(step_id)
    if current is None:
        raise HTTPException(status_code=404, detail="not found")

    merged_kind = patch.get("target_kind", current.target_kind)
    merged_key = patch.get("target_key", current.target_key)
    if merged_kind == "none" and merged_key is not None:
        raise HTTPException(
            status_code=400,
            detail="target_kind='none' requires target_key=null",
        )
    if merged_kind in ("static", "sdui") and not (merged_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail=f"target_kind='{merged_kind}' requires a non-empty target_key",
        )

    try:
        dto, changed = repo.update_step(
            step_id=step_id, editor_user_id=actor, partial=patch,
        )
    except StepNotFound:
        raise HTTPException(status_code=404, detail="not found")

    if changed:
        await record_tutorial_step_edited(
            actor_user_id=actor,
            auth_principal=_principal_of(admin),
            step_id=dto.id,
            step_slug=dto.slug,
            change_kind="update",
            changed_fields=changed,
        )
    return dto


@onboarding_admin_router.post(
    "/steps/{step_id}/archive",
    response_model=TutorialStepDTO,
    summary="Archive (soft-delete) a tutorial step (admin)",
)
async def archive_step_admin(
    step_id: int,
    request: Request,
    admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    actor = admin.get("sub") or "admin"
    try:
        dto = repo.archive_step(step_id=step_id, editor_user_id=actor)
    except StepNotFound:
        raise HTTPException(status_code=404, detail="not found")
    await record_tutorial_step_edited(
        actor_user_id=actor,
        auth_principal=_principal_of(admin),
        step_id=dto.id,
        step_slug=dto.slug,
        change_kind="archive",
        changed_fields=["archived_at"],
    )
    return dto


@onboarding_admin_router.post(
    "/steps/{step_id}/restore",
    response_model=TutorialStepDTO,
    summary="Restore a previously archived tutorial step (admin)",
)
async def restore_step_admin(
    step_id: int,
    request: Request,
    admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    actor = admin.get("sub") or "admin"
    try:
        dto = repo.restore_step(step_id=step_id, editor_user_id=actor)
    except StepNotFound:
        raise HTTPException(status_code=404, detail="not found")
    await record_tutorial_step_edited(
        actor_user_id=actor,
        auth_principal=_principal_of(admin),
        step_id=dto.id,
        step_slug=dto.slug,
        change_kind="restore",
        changed_fields=["archived_at"],
    )
    return dto


@onboarding_admin_router.get(
    "/steps/{step_id}/revisions",
    response_model=RevisionListResponse,
    summary="List the revision history for a tutorial step (admin)",
)
async def list_revisions_admin(
    step_id: int,
    request: Request,
    _admin: dict = Depends(verify_admin),
):
    repo = _repo(request)
    if repo.get_step(step_id) is None:
        raise HTTPException(status_code=404, detail="not found")
    revisions = repo.list_revisions(step_id)
    return RevisionListResponse(revisions=revisions)
