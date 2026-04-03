# Dockerfile for AstralBody Multi-Agent System

# ==========================================
# Single Stage: Backend Only
# ==========================================
# Frontend is now a Flutter native app (built/distributed separately)
FROM python:3.11-slim
WORKDIR /app

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

# Setup entrypoint script
COPY backend/start-docker.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-docker.sh

# Expose ports
# 8001: Orchestrator Gateway (WS + Auth API)
EXPOSE 8001

CMD ["/usr/local/bin/start-docker.sh"]
