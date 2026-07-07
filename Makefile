.DEFAULT_GOAL := help

# Path translation for Docker volume mounts under Cygwin / Git Bash / native.
# Docker CLI on Windows wants Y:/... not /cygdrive/y/... — cygpath -m and `pwd -W`
# both yield that form; native shells fall through to $(CURDIR).
HOST_PWD := $(shell cygpath -m "$(CURDIR)" 2>/dev/null || pwd -W 2>/dev/null || echo "$(CURDIR)")

.PHONY: help up down restart build ps logs logs-db shell psql \
        sync sync-backend \
        test test-backend lint lint-backend

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

sync-backend: ## Tar backend source via an alpine container, copy into astralbody, restart
	docker run --rm -v "$(HOST_PWD)/backend:/src:ro" alpine:3 tar \
	  --exclude='.venv' --exclude='__pycache__' --exclude='data' --exclude='tmp' \
	  --exclude='*.pyc' -C /src -cf - . \
	  | docker cp - astralbody:/app/backend/
	docker compose restart astralbody

sync: sync-backend ## Sync backend source into the running container

## ---------- Tests ----------

test-backend: ## Run pytest inside the astralbody container
	docker exec astralbody bash -c "cd /app/backend && python -m pytest -q"

test: test-backend ## Run all tests

## ---------- Lint ----------

lint-backend: ## Run ruff from the repo root (ruff is NOT in the image; ruff.toml lives here — matches ci.yml)
	ruff check .

lint: lint-backend ## Run all linters

## ---------- Help ----------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
