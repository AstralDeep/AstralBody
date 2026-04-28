"""psycopg2 access layer for the onboarding subsystem (feature 005).

Every query that touches ``onboarding_state``, ``tutorial_step``, or
``tutorial_step_revision`` lives here. The router and recorder NEVER
write SQL inline — they go through this module.

Design notes:

* User-scoped operations (``get_state``, ``upsert_state``,
  ``list_steps_for_user``) take ``actor_user_id`` / ``include_admin`` as
  explicit parameters so the API layer cannot accidentally widen the
  scope. There is no "list all" helper for ``onboarding_state`` because
  no caller has a legitimate cross-user use case (mirrors feature 003's
  audit-repository policy).
* Admin write operations (``create_step``, ``update_step``,
  ``archive_step``, ``restore_step``) bundle the canonical-table mutation
  with the matching ``tutorial_step_revision`` row inside a single DB
  transaction. The audit-log emit happens at the recorder layer, after
  the transaction commits, so a partial DB failure cannot leak an audit
  row that doesn't reflect a real change.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.errors

from .schemas import (
    OnboardingStateResponse,
    RevisionDTO,
    TutorialStepDTO,
)

logger = logging.getLogger("Onboarding.Repository")


class StepNotFound(Exception):
    """Raised when an admin write targets a non-existent step."""


class DuplicateSlug(Exception):
    """Raised when an admin attempts to create a step with an in-use slug."""


class OnboardingRepository:
    """Thin façade over the three feature-005 tables."""

    def __init__(self, db: Any):
        # ``db`` is a :class:`backend.shared.database.Database` instance.
        self._db = db

    # ------------------------------------------------------------------
    # Onboarding state
    # ------------------------------------------------------------------

    def get_state(self, user_id: str) -> OnboardingStateResponse:
        """Return the user's onboarding state, defaulting to ``not_started``.

        Absence of a row maps to the implicit default; this is the only
        place we materialize that default so callers never need to.
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT s.user_id, s.status, s.last_step_id, s.started_at,
                       s.updated_at, s.completed_at, s.skipped_at,
                       t.slug AS last_step_slug
                FROM onboarding_state s
                LEFT JOIN tutorial_step t ON t.id = s.last_step_id
                WHERE s.user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return OnboardingStateResponse(status="not_started")
            return OnboardingStateResponse(
                status=row["status"],
                last_step_id=row["last_step_id"],
                last_step_slug=row["last_step_slug"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                skipped_at=row["skipped_at"],
            )
        finally:
            conn.close()

    def upsert_state(
        self,
        user_id: str,
        status: str,
        last_step_id: Optional[int],
    ) -> Tuple[OnboardingStateResponse, Optional[str]]:
        """Insert or update the user's row.

        Returns ``(new_state, prior_status)`` where ``prior_status`` is
        ``None`` when no row existed before this call. The caller (the
        recorder) uses ``prior_status`` to decide which audit event to
        record.
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT status FROM onboarding_state WHERE user_id = %s FOR UPDATE",
                (user_id,),
            )
            existing = cur.fetchone()
            prior_status = existing["status"] if existing else None

            if existing is None:
                cur.execute(
                    """
                    INSERT INTO onboarding_state (
                        user_id, status, last_step_id, started_at,
                        updated_at, completed_at, skipped_at
                    )
                    VALUES (
                        %s, %s, %s, now(), now(),
                        CASE WHEN %s = 'completed' THEN now() ELSE NULL END,
                        CASE WHEN %s = 'skipped'   THEN now() ELSE NULL END
                    )
                    """,
                    (user_id, status, last_step_id, status, status),
                )
            else:
                cur.execute(
                    """
                    UPDATE onboarding_state SET
                        status = %s,
                        last_step_id = %s,
                        updated_at = now(),
                        completed_at = CASE
                            WHEN %s = 'completed' AND completed_at IS NULL THEN now()
                            ELSE completed_at
                        END,
                        skipped_at = CASE
                            WHEN %s = 'skipped' AND skipped_at IS NULL THEN now()
                            ELSE skipped_at
                        END
                    WHERE user_id = %s
                    """,
                    (status, last_step_id, status, status, user_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_state(user_id), prior_status

    # ------------------------------------------------------------------
    # Tutorial steps — read paths
    # ------------------------------------------------------------------

    def list_steps_for_user(self, *, include_admin: bool) -> List[TutorialStepDTO]:
        """Return the ordered, non-archived steps the caller can see.

        The caller passes ``include_admin=True`` only after verifying the
        admin role in the API layer.
        """
        if include_admin:
            audiences = ("user", "admin")
        else:
            audiences = ("user",)
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, slug, audience, display_order, target_kind, target_key,
                       title, body, archived_at, updated_at
                FROM tutorial_step
                WHERE archived_at IS NULL AND audience = ANY(%s)
                ORDER BY display_order ASC, id ASC
                """,
                (list(audiences),),
            )
            return [_row_to_step_dto(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_all_steps(self, include_archived: bool = True) -> List[TutorialStepDTO]:
        """Admin read: returns every step, optionally including archived ones."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            if include_archived:
                cur.execute(
                    """
                    SELECT id, slug, audience, display_order, target_kind, target_key,
                           title, body, archived_at, updated_at
                    FROM tutorial_step
                    ORDER BY display_order ASC, id ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, slug, audience, display_order, target_kind, target_key,
                           title, body, archived_at, updated_at
                    FROM tutorial_step
                    WHERE archived_at IS NULL
                    ORDER BY display_order ASC, id ASC
                    """
                )
            return [_row_to_step_dto(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_step(self, step_id: int) -> Optional[TutorialStepDTO]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, slug, audience, display_order, target_kind, target_key,
                       title, body, archived_at, updated_at
                FROM tutorial_step
                WHERE id = %s
                """,
                (step_id,),
            )
            row = cur.fetchone()
            return _row_to_step_dto(row) if row else None
        finally:
            conn.close()

    def get_step_audience(self, step_id: int) -> Optional[str]:
        """Return just the audience for a step. Used for cheap validation."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT audience, archived_at FROM tutorial_step WHERE id = %s",
                (step_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            if row["archived_at"] is not None:
                return None
            return row["audience"]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tutorial steps — admin write paths
    # ------------------------------------------------------------------

    def create_step(
        self,
        *,
        editor_user_id: str,
        slug: str,
        audience: str,
        display_order: int,
        target_kind: str,
        target_key: Optional[str],
        title: str,
        body: str,
    ) -> TutorialStepDTO:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO tutorial_step (
                        slug, audience, display_order, target_kind, target_key,
                        title, body
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, slug, audience, display_order, target_kind, target_key,
                              title, body, archived_at, updated_at
                    """,
                    (slug, audience, display_order, target_kind, target_key, title, body),
                )
            except psycopg2.errors.UniqueViolation as exc:
                conn.rollback()
                raise DuplicateSlug(slug) from exc
            row = cur.fetchone()
            dto = _row_to_step_dto(row)
            cur.execute(
                """
                INSERT INTO tutorial_step_revision (
                    step_id, editor_user_id, previous, current, change_kind
                ) VALUES (%s, %s, NULL, %s, 'create')
                """,
                (dto.id, editor_user_id, json.dumps(_dto_to_snapshot(dto))),
            )
            conn.commit()
            return dto
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_step(
        self,
        *,
        step_id: int,
        editor_user_id: str,
        partial: Dict[str, Any],
    ) -> Tuple[TutorialStepDTO, List[str]]:
        """Apply a partial update.

        ``partial`` may contain any of: audience, display_order, target_kind,
        target_key, title, body. Only fields present in the dict (i.e.
        keys whose value is set, including ``None`` for ``target_key``)
        are written.

        Returns ``(updated_dto, changed_fields)`` where ``changed_fields``
        is the list of column names whose values actually changed (no
        false positives).
        """
        if not partial:
            existing = self.get_step(step_id)
            if existing is None:
                raise StepNotFound(step_id)
            return existing, []

        allowed = ("audience", "display_order", "target_kind", "target_key", "title", "body")
        unknown = set(partial.keys()) - set(allowed)
        if unknown:
            raise ValueError(f"cannot update unknown fields: {sorted(unknown)}")

        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, slug, audience, display_order, target_kind, target_key,
                       title, body, archived_at, updated_at
                FROM tutorial_step
                WHERE id = %s
                FOR UPDATE
                """,
                (step_id,),
            )
            row = cur.fetchone()
            if not row:
                raise StepNotFound(step_id)
            previous = _row_to_step_dto(row)

            # Compute changed_fields by comparing prior values to the patch.
            changed: List[str] = []
            patched: Dict[str, Any] = {}
            for col in allowed:
                if col not in partial:
                    continue
                new_val = partial[col]
                old_val = getattr(previous, col)
                if new_val != old_val:
                    changed.append(col)
                    patched[col] = new_val

            if not changed:
                conn.commit()
                return previous, []

            # Build SET clause dynamically — only changed cols.
            set_clauses = ", ".join(f"{c} = %s" for c in changed)
            params = [patched[c] for c in changed] + [step_id]
            cur.execute(
                f"""
                UPDATE tutorial_step
                SET {set_clauses}, updated_at = now()
                WHERE id = %s
                RETURNING id, slug, audience, display_order, target_kind, target_key,
                          title, body, archived_at, updated_at
                """,
                tuple(params),
            )
            new_row = cur.fetchone()
            new_dto = _row_to_step_dto(new_row)
            cur.execute(
                """
                INSERT INTO tutorial_step_revision (
                    step_id, editor_user_id, previous, current, change_kind
                ) VALUES (%s, %s, %s, %s, 'update')
                """,
                (
                    step_id,
                    editor_user_id,
                    json.dumps(_dto_to_snapshot(previous)),
                    json.dumps(_dto_to_snapshot(new_dto)),
                ),
            )
            conn.commit()
            return new_dto, changed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def archive_step(self, *, step_id: int, editor_user_id: str) -> TutorialStepDTO:
        return self._toggle_archive(step_id=step_id, editor_user_id=editor_user_id, archive=True)

    def restore_step(self, *, step_id: int, editor_user_id: str) -> TutorialStepDTO:
        return self._toggle_archive(step_id=step_id, editor_user_id=editor_user_id, archive=False)

    def _toggle_archive(self, *, step_id: int, editor_user_id: str, archive: bool) -> TutorialStepDTO:
        change_kind = "archive" if archive else "restore"
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, slug, audience, display_order, target_kind, target_key,
                       title, body, archived_at, updated_at
                FROM tutorial_step
                WHERE id = %s
                FOR UPDATE
                """,
                (step_id,),
            )
            row = cur.fetchone()
            if not row:
                raise StepNotFound(step_id)
            previous = _row_to_step_dto(row)
            already_in_target_state = (archive and previous.archived_at is not None) or (
                not archive and previous.archived_at is None
            )
            if already_in_target_state:
                conn.commit()
                return previous

            if archive:
                cur.execute(
                    """
                    UPDATE tutorial_step SET archived_at = now(), updated_at = now()
                    WHERE id = %s
                    RETURNING id, slug, audience, display_order, target_kind, target_key,
                              title, body, archived_at, updated_at
                    """,
                    (step_id,),
                )
            else:
                cur.execute(
                    """
                    UPDATE tutorial_step SET archived_at = NULL, updated_at = now()
                    WHERE id = %s
                    RETURNING id, slug, audience, display_order, target_kind, target_key,
                              title, body, archived_at, updated_at
                    """,
                    (step_id,),
                )
            new_dto = _row_to_step_dto(cur.fetchone())
            cur.execute(
                """
                INSERT INTO tutorial_step_revision (
                    step_id, editor_user_id, previous, current, change_kind
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    step_id,
                    editor_user_id,
                    json.dumps(_dto_to_snapshot(previous)),
                    json.dumps(_dto_to_snapshot(new_dto)),
                    change_kind,
                ),
            )
            conn.commit()
            return new_dto
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_revisions(self, step_id: int) -> List[RevisionDTO]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, step_id, editor_user_id, edited_at, previous, current, change_kind
                FROM tutorial_step_revision
                WHERE step_id = %s
                ORDER BY edited_at DESC, id DESC
                """,
                (step_id,),
            )
            return [_row_to_revision_dto(r) for r in cur.fetchall()]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers — DB row → DTO
# ---------------------------------------------------------------------------

def _row_to_step_dto(row: Optional[Dict[str, Any]]) -> Optional[TutorialStepDTO]:
    if row is None:
        return None
    return TutorialStepDTO(
        id=row["id"],
        slug=row["slug"],
        audience=row["audience"],
        display_order=row["display_order"],
        target_kind=row["target_kind"],
        target_key=row["target_key"],
        title=row["title"],
        body=row["body"],
        archived_at=row.get("archived_at"),
        updated_at=row.get("updated_at"),
    )


def _row_to_revision_dto(row: Dict[str, Any]) -> RevisionDTO:
    prev = row.get("previous")
    cur = row.get("current")
    if isinstance(prev, str):
        prev = json.loads(prev)
    if isinstance(cur, str):
        cur = json.loads(cur)
    return RevisionDTO(
        id=row["id"],
        step_id=row["step_id"],
        editor_user_id=row["editor_user_id"],
        edited_at=row["edited_at"],
        change_kind=row["change_kind"],
        previous=prev,
        current=cur,
    )


def _dto_to_snapshot(dto: TutorialStepDTO) -> Dict[str, Any]:
    """Snapshot used for the revision row's ``previous`` / ``current`` JSON."""
    return {
        "id": dto.id,
        "slug": dto.slug,
        "audience": dto.audience,
        "display_order": dto.display_order,
        "target_kind": dto.target_kind,
        "target_key": dto.target_key,
        "title": dto.title,
        "body": dto.body,
        "archived_at": dto.archived_at.isoformat() if dto.archived_at else None,
        "updated_at": dto.updated_at.isoformat() if dto.updated_at else None,
    }
