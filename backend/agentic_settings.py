"""Central configuration for the agentic-soul-integration feature (025).

Values are read from the environment with safe defaults so production
configuration is explicit and nothing security-relevant is hard-coded
(Constitution Principle X). Imported by the ``personalization``,
``scheduler``, and ``dreaming`` modules.
"""
from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on missing/invalid."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- Unattended-job authorization (offline grant) -------------------------
# Symmetric key (urlsafe-base64 / Fernet) used to encrypt stored offline
# refresh tokens at rest. MUST be supplied in production. Its absence does
# NOT silently weaken security: scheduling that needs unattended authority
# fails safe (see scheduler.runner) rather than storing tokens unencrypted.
OFFLINE_GRANT_ENC_KEY: str | None = os.getenv("OFFLINE_GRANT_ENC_KEY")

# Hard maximum lifetime of an offline grant; matches the persistent-login
# (feature 016) 365-day cap (FR-024).
OFFLINE_GRANT_MAX_DAYS: int = _int("OFFLINE_GRANT_MAX_DAYS", 365)

# --- Scheduler -------------------------------------------------------------
# How often the scheduler loop wakes to dispatch due jobs (≤ 1 min keeps
# SC-007's 1-minute tolerance comfortably).
SCHEDULER_TICK_SECONDS: int = _int("SCHEDULER_TICK_SECONDS", 30)
# Per-user cap on active scheduled jobs (FR-038, multi-tenant safety).
SCHEDULE_MAX_ACTIVE_JOBS_PER_USER: int = _int("SCHEDULE_MAX_ACTIVE_JOBS_PER_USER", 25)
# Minimum recurring interval — no sub-minute recurring jobs (FR-038).
SCHEDULE_MIN_INTERVAL_SECONDS: int = _int("SCHEDULE_MIN_INTERVAL_SECONDS", 60)

# --- Dreaming (background consolidation) ----------------------------------
# Default per-user sweep cadence (cron form). Enabled by default / opt-out
# per FR-029; always honored against user_personalization.dreaming_enabled.
DREAMING_DEFAULT_CRON: str = os.getenv("DREAMING_DEFAULT_CRON", "0 3 * * *")

# --- Memory ---------------------------------------------------------------
# Minimum recall count for a short-term signal to be eligible for promotion
# into durable memory during a consolidation sweep.
MEMORY_PROMOTION_MIN_RECALLS: int = _int("MEMORY_PROMOTION_MIN_RECALLS", 2)
