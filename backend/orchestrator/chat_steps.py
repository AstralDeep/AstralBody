"""Persistent step recorder for in-chat progress notifications.

Feature 014-progress-notifications, US2 / FR-007 through FR-013, FR-020/021.

The recorder is created once per active chat turn and given the WebSocket the
turn arrived on. It exposes a small lifecycle API:

* :meth:`start` — register a step (tool call / agent hand-off / orchestrator
  phase), persist an ``in_progress`` row, emit a ``chat_step`` event, and
  return a stable ``step_id`` the caller uses for completion/error.
* :meth:`complete` — mark a step ``completed`` with its truncated result.
* :meth:`error` — mark a step ``errored`` with a redacted message.
* :meth:`cancel_all_in_flight` — invoked by the cancel_task handler; marks
  every in-progress step ``cancelled`` (FR-020/021).
* :meth:`is_terminal` — used by the orchestrator to drop late-arriving
  results from cancelled steps (R6 best-effort discard policy).

All payloads pass through :func:`shared.phi_redactor.redact` before being
persisted or transmitted (FR-009b, defense-in-depth at the write boundary).
The recorder never raises into the caller — failures are structured-logged
and the caller's lifecycle continues unaffected.

See also:

* contracts/chat_step_event.md for the wire shape.
* data-model.md for the ``chat_steps`` schema.
* research.md R1, R4, R5, R6 for design rationale.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from shared.phi_redactor import redact

logger = logging.getLogger("Orchestrator.ChatSteps")

KIND_TOOL_CALL = "tool_call"
KIND_AGENT_HANDOFF = "agent_handoff"
KIND_PHASE = "phase"

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_ERRORED = "errored"
STATUS_CANCELLED = "cancelled"
STATUS_INTERRUPTED = "interrupted"

_TERMINAL_STATUSES = frozenset({
    STATUS_COMPLETED,
    STATUS_ERRORED,
    STATUS_CANCELLED,
    STATUS_INTERRUPTED,
})


def _now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_step(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a DB row into the wire shape consumers expect."""
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "turn_message_id": row.get("turn_message_id"),
        "kind": row["kind"],
        "name": row["name"],
        "status": row["status"],
        "args_truncated": row.get("args_truncated"),
        "args_was_truncated": bool(row.get("args_was_truncated", False)),
        "result_summary": row.get("result_summary"),
        "result_was_truncated": bool(row.get("result_was_truncated", False)),
        "error_message": row.get("error_message"),
        "started_at": row["started_at"],
        "ended_at": row.get("ended_at"),
    }


class ChatStepRecorder:
    """Records lifecycle events for one chat turn's persistent step trail.

    A new recorder is constructed per active turn so it can hold per-turn
    state (the in-flight set used by ``cancel_all_in_flight``) without a
    shared registry. The recorder is safe to construct with ``websocket=None``
    or ``safe_send=None`` — persistence still happens; the WebSocket emit is
    skipped silently.
    """

    def __init__(
        self,
        *,
        db,
        websocket=None,
        safe_send=None,
        chat_id: str,
        user_id: str,
        turn_message_id: Optional[int] = None,
    ):
        self.db = db
        self.websocket = websocket
        self.safe_send = safe_send
        self.chat_id = chat_id
        self.user_id = user_id
        self.turn_message_id = turn_message_id
        self._in_flight: Dict[str, str] = {}
        # Cache the terminal status for late-arriving result discard checks.
        self._statuses: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle entry points
    # ------------------------------------------------------------------
    async def start(self, kind: str, name: str, args: Any = None) -> str:
        """Register a new in-progress step. Returns its ``step_id``."""
        step_id = uuid.uuid4().hex
        args_text, args_trunc = redact(args, kind="args")
        started = _now_ms()
        try:
            self.db.execute(
                """
                INSERT INTO chat_steps (
                    id, chat_id, user_id, turn_message_id,
                    kind, name, status,
                    args_truncated, args_was_truncated,
                    started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    self.chat_id,
                    self.user_id,
                    self.turn_message_id,
                    kind,
                    name,
                    STATUS_IN_PROGRESS,
                    args_text,
                    args_trunc,
                    started,
                ),
            )
            self._bump_step_count()
        except Exception as exc:  # pragma: no cover — defensive
            logger.error(
                "chat_steps.start_persist_failed",
                extra={"chat_id": self.chat_id, "kind": kind, "name": name, "error": str(exc)},
            )

        self._in_flight[step_id] = name
        self._statuses[step_id] = STATUS_IN_PROGRESS

        await self._emit({
            "id": step_id,
            "chat_id": self.chat_id,
            "turn_message_id": self.turn_message_id,
            "kind": kind,
            "name": name,
            "status": STATUS_IN_PROGRESS,
            "args_truncated": args_text,
            "args_was_truncated": args_trunc,
            "result_summary": None,
            "result_was_truncated": False,
            "error_message": None,
            "started_at": started,
            "ended_at": None,
        })
        logger.info(
            "chat_steps.started",
            extra={"step_id": step_id, "chat_id": self.chat_id, "kind": kind, "name": name},
        )
        return step_id

    async def complete(self, step_id: str, result: Any = None) -> None:
        """Mark a step ``completed`` with its truncated result summary."""
        if self._statuses.get(step_id) in _TERMINAL_STATUSES:
            # Late completion after cancel — drop per R6.
            logger.info(
                "chat_steps.late_complete_dropped",
                extra={"step_id": step_id, "chat_id": self.chat_id},
            )
            return
        result_text, result_trunc = redact(result, kind="result")
        await self._terminate(
            step_id,
            status=STATUS_COMPLETED,
            result_summary=result_text,
            result_was_truncated=result_trunc,
            error_message=None,
        )

    async def error(self, step_id: str, exc) -> None:
        """Mark a step ``errored``. ``exc`` may be an Exception or a string."""
        if self._statuses.get(step_id) in _TERMINAL_STATUSES:
            logger.info(
                "chat_steps.late_error_dropped",
                extra={"step_id": step_id, "chat_id": self.chat_id},
            )
            return
        msg = str(exc) if exc is not None else "Unknown error"
        err_text, _ = redact(msg, kind="error")
        await self._terminate(
            step_id,
            status=STATUS_ERRORED,
            result_summary=None,
            result_was_truncated=False,
            error_message=err_text,
        )

    async def cancel_all_in_flight(self) -> None:
        """Mark every still-in-progress step as ``cancelled`` (FR-020/021).

        Defensive: each candidate is re-checked against the DB before being
        flipped to ``cancelled``. A row that already reached a terminal
        state in the DB (e.g. ``complete()`` raced ahead and updated the
        row before this code observed it) is skipped — we never overwrite
        a real terminal state with a cancellation marker.
        """
        # Snapshot first — _terminate mutates _in_flight.
        snapshot = list(self._in_flight.keys())
        for step_id in snapshot:
            # Re-check the DB. If the row is already in a terminal state,
            # respect that and clear the in-memory entry without emitting
            # a contradictory cancelled event.
            try:
                row = self.db.fetch_one(
                    "SELECT status FROM chat_steps WHERE id = ?", (step_id,)
                )
                if row is not None and row.get("status") in _TERMINAL_STATUSES:
                    self._in_flight.pop(step_id, None)
                    self._statuses[step_id] = row["status"]
                    logger.info(
                        "chat_steps.cancel_skipped_already_terminal",
                        extra={"step_id": step_id, "status": row["status"]},
                    )
                    continue
            except Exception:  # pragma: no cover — defensive
                pass
            await self._terminate(
                step_id,
                status=STATUS_CANCELLED,
                result_summary=None,
                result_was_truncated=False,
                error_message=None,
            )

    def is_terminal(self, step_id: str) -> bool:
        """True once a step has reached any terminal state.

        Used by the orchestrator before integrating a tool result so
        late-arriving responses from cancelled steps are dropped per R6.
        """
        return self._statuses.get(step_id) in _TERMINAL_STATUSES

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _terminate(
        self,
        step_id: str,
        *,
        status: str,
        result_summary: Optional[str],
        result_was_truncated: bool,
        error_message: Optional[str],
    ) -> None:
        ended = _now_ms()
        try:
            self.db.execute(
                """
                UPDATE chat_steps
                   SET status = ?, ended_at = ?,
                       result_summary = ?, result_was_truncated = ?,
                       error_message = ?
                 WHERE id = ?
                """,
                (
                    status,
                    ended,
                    result_summary,
                    result_was_truncated,
                    error_message,
                    step_id,
                ),
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error(
                "chat_steps.terminate_persist_failed",
                extra={"step_id": step_id, "status": status, "error": str(exc)},
            )

        self._in_flight.pop(step_id, None)
        self._statuses[step_id] = status

        # Re-fetch the row so the emit carries the canonical persisted state
        # (and matches what the REST endpoint would return on rehydrate).
        try:
            row = self.db.fetch_one(
                "SELECT * FROM chat_steps WHERE id = ?",
                (step_id,),
            )
            payload = _row_to_step(dict(row)) if row else {
                "id": step_id,
                "chat_id": self.chat_id,
                "turn_message_id": self.turn_message_id,
                "kind": KIND_TOOL_CALL,
                "name": self._in_flight.get(step_id, "unknown"),
                "status": status,
                "args_truncated": None,
                "args_was_truncated": False,
                "result_summary": result_summary,
                "result_was_truncated": result_was_truncated,
                "error_message": error_message,
                "started_at": ended,
                "ended_at": ended,
            }
        except Exception:  # pragma: no cover — defensive
            payload = {
                "id": step_id,
                "chat_id": self.chat_id,
                "turn_message_id": self.turn_message_id,
                "kind": KIND_TOOL_CALL,
                "name": "unknown",
                "status": status,
                "args_truncated": None,
                "args_was_truncated": False,
                "result_summary": result_summary,
                "result_was_truncated": result_was_truncated,
                "error_message": error_message,
                "started_at": ended,
                "ended_at": ended,
            }

        await self._emit(payload)
        logger.info(
            "chat_steps.terminated",
            extra={"step_id": step_id, "status": status, "chat_id": self.chat_id},
        )

    def _bump_step_count(self) -> None:
        if self.turn_message_id is None:
            return
        try:
            self.db.execute(
                "UPDATE messages SET step_count = step_count + 1 WHERE id = ?",
                (self.turn_message_id,),
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "chat_steps.step_count_bump_failed",
                extra={"turn_message_id": self.turn_message_id, "error": str(exc)},
            )

    async def _emit(self, step_payload: Dict[str, Any]) -> None:
        if self.websocket is None or self.safe_send is None:
            return
        try:
            envelope = {
                "type": "chat_step",
                "chat_id": self.chat_id,
                "step": step_payload,
            }
            sent = self.safe_send(self.websocket, json.dumps(envelope, default=str))
            if asyncio.iscoroutine(sent):
                await sent
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "chat_steps.emit_failed",
                extra={"chat_id": self.chat_id, "error": str(exc)},
            )
