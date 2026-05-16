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
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# Sanitize all .env files to remove Windows line endings (\r)
RUN find /app -name ".env" -exec sed -i 's/\r$//' {} +

# Set memory limit for Node to prevent swap thrashing during Vite build
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Extract only VITE_* vars from .env and export them for the build.
# Using a temp script avoids shell issues with special characters in
# non-VITE values (passwords, secrets, etc.)
RUN grep '^VITE_' /app/.env > /tmp/vite-env.sh && \
    sed -i 's/^/export /' /tmp/vite-env.sh && \
    . /tmp/vite-env.sh && \
    npm run build

# ==========================================
# Stage 2: Final Image (Backend + Nginx)
# ==========================================
FROM python:3.11-slim
WORKDIR /app

# System packages required by file-upload parsing (feature 002-file-uploads):
#   poppler-utils  - PDF rendering used by pdf2image (image-only PDFs are
#                    handed to the vision model)
#   libmagic1      - libmagic bindings used by python-magic for content-type sniffing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel/setuptools first to ensure binary wheels are downloaded
# instead of compiling heavy packages like pandas from source, saving lots of time and memory.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

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
