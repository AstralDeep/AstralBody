"""Audit module tests.

Run:
    cd backend && python -m pytest audit/tests/

Tests use a temporary schema in the configured Postgres so we don't
contaminate the dev DB. The protocol is: each test ensures the schema
exists, inserts under a unique ``actor_user_id`` (typically derived from
the test name), and cleans up via the retention path that holds the
``audit.allow_purge`` GUC.

These tests are explicitly INTEGRATION tests against Postgres — they
need DB_HOST/DB_PORT/etc. set (the project's standard env vars). Pure
unit tests for PII helpers are in ``test_pii.py`` and do not touch the DB.
"""
