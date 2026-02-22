# Dockerfile for AstralBody Multi-Agent System

# ==========================================
# Stage 1: Build Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy .env to BOTH parent (for Vite envDir: '../') and current dir (as fallback)
COPY .env /app/.env
COPY .env ./.env

# Copy frontend source
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Sanitize all .env files to remove Windows line endings (\r)
RUN find /app -name ".env" -exec sed -i 's/\r$//' {} +

# Source .env before build to ensure Vite sees the variables
RUN set -a && . /app/.env && set +a && npm run build

# ==========================================
# Stage 2: Final Image (Backend + Nginx)
# ==========================================
FROM python:3.11-slim
WORKDIR /app

# Install requirements
RUN apt-get update && apt-get install -y && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy .env into backend where start.py expects it
COPY .env ./backend/.env
RUN sed -i 's/\r$//' ./backend/.env

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Setup entrypoint script
COPY backend/start-docker.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-docker.sh

# Expose ports
# 8001: Orchestrator Gateway (WS + Auth API)
# 5173: Static Frontend
EXPOSE 8001 5173

CMD ["/usr/local/bin/start-docker.sh"]
