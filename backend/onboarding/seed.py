"""Idempotent loader for the canonical tutorial step seed (feature 005).

Reads ``backend/seeds/tutorial_steps_seed.sql`` on orchestrator startup
and executes it against the configured database. The SQL uses
``ON CONFLICT (slug) DO NOTHING`` so re-runs do not overwrite admin
edits.

If the seed file is missing or malformed we log and return — the system
still functions; admins can author steps directly through the admin UI.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("Onboarding.Seed")

_SEED_PATH = (
    Path(os.path.dirname(os.path.abspath(__file__))).parent / "seeds" / "tutorial_steps_seed.sql"
)


def seed_tutorial_steps(db: Any) -> int:
    """Execute the seed SQL against ``db``. Returns rows-affected best-effort."""
    if not _SEED_PATH.exists():
        logger.info("tutorial seed file %s not found; skipping seed", _SEED_PATH)
        return 0

    try:
        sql = _SEED_PATH.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("could not read tutorial seed file: %s", exc)
        return 0

    conn = db._get_connection()
    affected = 0
    try:
        cur = conn.cursor()
        cur.execute(sql)
        affected = cur.rowcount or 0
        conn.commit()
        logger.info("Tutorial seed loaded (%s rows affected on this run)", affected)
    except Exception as exc:
        conn.rollback()
        logger.warning("tutorial seed execution failed: %s", exc)
    finally:
        conn.close()
    return affected
