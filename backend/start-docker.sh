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
exec python start.py
