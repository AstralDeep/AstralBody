.DEFAULT_GOAL := help

# Path translation for Docker volume mounts under Cygwin / Git Bash / native.
# Docker CLI on Windows wants Y:/... not /cygdrive/y/... — cygpath -m and `pwd -W`
# both yield that form; native shells fall through to $(CURDIR).
HOST_PWD := $(shell cygpath -m "$(CURDIR)" 2>/dev/null || pwd -W 2>/dev/null || echo "$(CURDIR)")

# One-off node container used for any operation that needs npm/node.
# A named volume caches node_modules across runs.
NODE_RUN := docker run --rm \
  -v "$(HOST_PWD)/frontend:/app/frontend" \
  -v "$(HOST_PWD)/.env:/app/.env" \
  -v astralbody_node_modules:/app/frontend/node_modules \
  -w /app/frontend \
  -e NODE_OPTIONS=--max-old-space-size=4096 \
  node:20-alpine

.PHONY: help up down restart build ps logs logs-db shell psql \
        sync sync-frontend sync-backend \
        test test-backend test-frontend lint lint-backend lint-frontend

## ---------- Lifecycle ----------

up: ## Build images and start all containers in the background
	docker compose up -d --build

down: ## Stop containers (volumes preserved)
	docker compose down

restart: ## Restart the astralbody app container
	docker compose restart astralbody

build: ## Build images without starting containers
	docker compose build

ps: ## Show container status
	docker compose ps

## ---------- Observability ----------

logs: ## Follow logs for the astralbody container
	docker compose logs -f astralbody

logs-db: ## Follow logs for the postgres container
	docker compose logs -f postgres

## ---------- Shells ----------

shell: ## Open a bash shell inside the astralbody container
	docker exec -it astralbody bash

psql: ## Open psql against the postgres container (uses DB_USER/DB_NAME from .env)
	docker exec -it astralbody-postgres psql -U $$DB_USER -d $$DB_NAME

## ---------- Sync (no host toolchain; everything runs in containers) ----------

sync-frontend: ## Build frontend in a node:20-alpine container, copy dist into astralbody
	$(NODE_RUN) sh -c "npm install --no-audit --no-fund && npm run build"
	docker cp frontend/dist/. astralbody:/app/frontend/dist/

sync-backend: ## Tar backend source via an alpine container, copy into astralbody, restart
	docker run --rm -v "$(HOST_PWD)/backend:/src:ro" alpine:3 tar \
	  --exclude='.venv' --exclude='__pycache__' --exclude='data' --exclude='tmp' \
	  --exclude='*.pyc' -C /src -cf - . \
	  | docker cp - astralbody:/app/backend/
	docker compose restart astralbody

sync: sync-frontend sync-backend ## Sync both frontend and backend

## ---------- Tests ----------

test-frontend: ## Run Vitest in a node:20-alpine container
	$(NODE_RUN) sh -c "npm install --no-audit --no-fund && npm run test:run"

test-backend: ## Run pytest inside the astralbody container
	docker exec astralbody bash -c "cd /app/backend && python -m pytest -q"

test: test-backend test-frontend ## Run all tests

## ---------- Lint ----------

lint-frontend: ## Run ESLint in a node:20-alpine container
	$(NODE_RUN) sh -c "npm install --no-audit --no-fund && npm run lint"

lint-backend: ## Run ruff inside the astralbody container
	docker exec astralbody bash -c "cd /app/backend && ruff check ."

lint: lint-backend lint-frontend ## Run all linters

## ---------- Help ----------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
