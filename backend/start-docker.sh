#!/bin/bash
set -e

# Start simple static server for frontend on port 5173
echo "Starting Frontend Static Server on port 5173..."
python3 -m http.server 5173 --directory /app/frontend/dist &

echo "Starting AstralBody Backend Services on port 8001..."
# Orchestrator consolidated FastAPI app will run on 8001
export ORCHESTRATOR_PORT=8001

# Force UTF-8 encoding
export PYTHONIOENCODING=utf-8

cd /app/backend

# Run agent ownership migration in the background after services start
# Waits for the orchestrator API to be reachable, then assigns unowned agents
(
    echo "Waiting for orchestrator to start before running migrations..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8001/api/agents -H "Authorization: Bearer mock" > /dev/null 2>&1; then
            echo "Running agent ownership migration..."
            python3 -m scripts.migrate_agent_ownership || true
            break
        fi
        sleep 2
    done
) &

exec python start.py
