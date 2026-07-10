#!/bin/bash
set -e

# Feature 026: no separate frontend static server. The orchestrator serves the
# server-driven web UI (shell + static assets) directly on port 8001.
echo "Starting AstralDeep Backend Services on port 8001..."
# Orchestrator consolidated FastAPI app will run on 8001
export ORCHESTRATOR_PORT=8001

# Force UTF-8 encoding
export PYTHONIOENCODING=utf-8

cd /app/backend

# Wait for PostgreSQL to be ready (belt-and-suspenders with docker healthcheck)
echo "Waiting for PostgreSQL..."
PG_URL="postgresql://${DB_USER:-astral}:${DB_PASSWORD:-astral_dev}@${DB_HOST:-localhost}:${DB_PORT:-5432}/${DB_NAME:-astraldeep}"
until python3 -c "import psycopg2; psycopg2.connect('$PG_URL')" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

# ── SQLite → PostgreSQL data migration (one-time) ──────────────────────
SQLITE_MAIN="/app/backend/data/astral.db"
SQLITE_AUDIT="/app/backend/data/test_audit.db"
MIGRATION_MARKER="/app/backend/data/.sqlite_migrated"

if [ -f "$SQLITE_MAIN" ] || [ -f "$SQLITE_AUDIT" ]; then
    if [ ! -f "$MIGRATION_MARKER" ]; then
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  SQLite databases detected — running one-time migration…"
        echo "════════════════════════════════════════════════════════════"
        if python3 -m scripts.migrate_sqlite_to_postgres; then
            touch "$MIGRATION_MARKER"
            echo ""
            echo "════════════════════════════════════════════════════════════"
            echo "  ✓ Migration complete!"
            echo ""
            echo "  It is now safe to delete the old SQLite files:"
            echo "    - backend/data/astral.db"
            echo "    - backend/data/test_audit.db"
            echo "════════════════════════════════════════════════════════════"
            echo ""
        else
            echo ""
            echo "  ⚠ SQLite migration encountered errors."
            echo "  The system will continue starting with PostgreSQL."
            echo "  You can retry manually with:"
            echo "    docker compose exec astraldeep python -m scripts.migrate_sqlite_to_postgres"
            echo ""
        fi
    else
        echo "SQLite migration already completed (marker found). Skipping."
    fi
else
    echo "No SQLite databases found. Nothing to migrate."
fi

# Run agent ownership migration in the background after services start.
# Probes the ungated /healthz endpoint with python (the slim image has no
# curl — the previous curl probe never succeeded, and its mock bearer token
# would be refused under real auth anyway).
(
    echo "Waiting for orchestrator to start before running migrations..."
    for i in $(seq 1 30); do
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz', timeout=3)" > /dev/null 2>&1; then
            sleep 5  # give auto-started agents a moment to register
            echo "Running agent ownership migration..."
            python3 -m scripts.migrate_agent_ownership || true
            break
        fi
        sleep 2
    done
) &

exec python start.py
