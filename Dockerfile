# Dockerfile for AstralDeep Multi-Agent System
#
# Feature 026: single backend image. The orchestrator serves the server-driven
# web UI (astralprims primitives rendered by webrender, adapted by ROTE) directly
# on port 8001 — there is no separate React/Vite frontend build or static server.

FROM python:3.11-slim
WORKDIR /app

# System packages.
#
# Runtime (file-upload parsing, feature 002-file-uploads):
#   poppler-utils  - PDF rendering used by pdf2image (image-only PDFs are
#                    handed to the vision model)
#   libmagic1      - libmagic bindings used by python-magic for content-type sniffing
#
# Build toolchain (build-essential + cmake + git):
#   Required to compile source-only wheels. On linux/arm64 — which Docker Desktop
#   builds by default on Apple Silicon Macs — some medical-imaging deps publish no
#   prebuilt wheel and build from source. aicspylibczi in particular uses a
#   CMake/pybind11 build that (a) fails with "No such file or directory: 'cmake'"
#   without cmake, and (b) fetches its vendored libCZI sources over git, so git is
#   needed too (verified: build-essential+cmake+git compiles aicspylibczi 3.3.1 on
#   arm64). On amd64 (typical Linux/Windows CI + prod) a prebuilt wheel is used and
#   this toolchain is never invoked. Installing it keeps `docker compose build`
#   green on every architecture — Mac, Windows, and Linux alike.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        libmagic1 \
        build-essential \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel/setuptools first to ensure binary wheels are downloaded
# instead of compiling heavy packages like pandas from source, saving lots of time and memory.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Download the spaCy model used by Presidio for PHI detection at build time
# (feature 025-agentic-soul-integration) so no model is fetched over the network at runtime.
RUN python -m spacy download en_core_web_lg

# Copy backend source
COPY backend/ ./backend/

# NOTE: configuration is intentionally NOT baked into the image. Secrets in
# image layers survive `docker rmi` in registry caches and leak via `docker
# history`. Supply configuration at runtime instead:
#   docker compose:  env_file: .env   (already wired in docker-compose.yml)
#   docker run:      --env-file .env
# load_dotenv(override=False) in start.py tolerates the absent file.

# Setup entrypoint script
COPY backend/start-docker.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-docker.sh

# Expose ports
# 8001: Orchestrator Gateway — serves WS, REST API, and the server-driven web UI
EXPOSE 8001

CMD ["/usr/local/bin/start-docker.sh"]
