"""Shared pytest fixtures for the onboarding test suite (feature 005)."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# Ensure the test process can import backend modules
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("AUDIT_HMAC_SECRET", "pytest-audit-secret")
os.environ.setdefault("AUDIT_HMAC_KEY_ID", "k1")


@pytest.fixture(scope="session")
def database():
    """Real Postgres-backed Database; schema initialised lazily."""
    from shared.database import Database
    return Database()


@pytest.fixture
def audit_repo(database):
    from audit.repository import AuditRepository
    return AuditRepository(database)


@pytest.fixture
def onboarding_repo(database):
    from onboarding.repository import OnboardingRepository
    return OnboardingRepository(database)


@pytest.fixture
def unique_user(request):
    return f"pytest-{request.node.name}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session", autouse=True)
def _final_pytest_cleanup(database):
    yield
    try:
        conn = database._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM onboarding_state WHERE user_id LIKE 'pytest-%'")
        cur.execute("DELETE FROM tutorial_step_revision WHERE editor_user_id LIKE 'pytest-%'")
        cur.execute("DELETE FROM tutorial_step WHERE slug LIKE 'pytest-%'")
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _isolate_onboarding_state(database, request):
    """Clean any onboarding rows left behind by a prior test for the same user.

    The fixture-level isolation here is name-spaced by test name so concurrent
    tests do not stomp on each other (test names are part of ``unique_user``).
    """
    yield
    try:
        conn = database._get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM onboarding_state WHERE user_id LIKE %s",
            (f"pytest-{request.node.name}-%",),
        )
        cur.execute(
            "DELETE FROM tutorial_step_revision WHERE editor_user_id LIKE %s",
            (f"pytest-{request.node.name}-%",),
        )
        # Test-created steps use slugs prefixed with the test name
        cur.execute(
            "DELETE FROM tutorial_step WHERE slug LIKE %s",
            (f"pytest-{request.node.name}-%",),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
