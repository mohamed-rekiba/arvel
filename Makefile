SHELL := /bin/sh
UV ?= uv
COMPOSE ?= docker compose
COMPOSE_ENV ?= --env-file .env.docker
TEST_ENV_FILE ?= .env.testing

.DEFAULT_GOAL := help

.PHONY: help install setup run test test-unit test-docker test-integration coverage \
	lint format format-check typecheck verify pre-commit \
	migrate seed fresh \
	compose-up compose-down compose-logs compose-ps compose-build compose-restart clean \
	docs docs-serve docs-build docs-test docs-clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ──── Setup ────

install: ## Install project + dev + all extras
	$(UV) sync --all-extras

setup: install compose-up ## Full setup: install deps, start Docker, configure Keycloak
	@echo "Waiting for all services to be healthy..."
	@for i in $$(seq 1 60); do \
		UNHEALTHY=$$($(COMPOSE) ps --format '{{.Health}}' 2>/dev/null | grep -cv healthy); \
		if [ "$$UNHEALTHY" -eq 0 ]; then echo "All services healthy."; break; fi; \
		sleep 5; \
	done
	$(COMPOSE) up keycloak-setup

run: ## Start Arvel dev server locally
	$(UV) run arvel serve --host 0.0.0.0 --port 8000

# ──── Docker Compose ────

compose-up: ## Start Docker services
	$(COMPOSE) $(COMPOSE_ENV) up -d
	@echo "Waiting for Keycloak..."
	@for i in $$(seq 1 60); do \
		if curl -sf http://localhost:9090/health/ready > /dev/null 2>&1; then \
			echo "Keycloak healthy."; break; \
		fi; \
		sleep 5; \
	done
	$(COMPOSE) up keycloak-setup

compose-down: ## Stop Docker services
	$(COMPOSE) down --remove-orphans

compose-logs: ## Follow Docker compose logs
	$(COMPOSE) logs -f --tail=200

compose-ps: ## Show Docker service status
	$(COMPOSE) ps

compose-build: ## Rebuild Docker images
	$(COMPOSE) $(COMPOSE_ENV) build

compose-restart: ## Restart all Docker services
	$(COMPOSE) restart

clean: compose-down docs-clean ## Stop services, remove volumes, clean caches
	$(COMPOSE) down -v 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/ .tests/
	rm -rf htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ──── Documentation ────

MKDOCS_CFG := docs/site/en/mkdocs.yml

docs: docs-serve ## Alias for docs-serve

docs-serve: ## Serve docs locally with live-reload (http://127.0.0.1:8001)
	$(UV) run mkdocs serve -f $(MKDOCS_CFG) --dev-addr 127.0.0.1:8001

docs-build: ## Build docs site (strict mode)
	$(UV) run mkdocs build -f $(MKDOCS_CFG) --strict

docs-test: ## Run documentation tests
	$(UV) run pytest tests/docs/ -v --tb=short -m "docs and not integration"

docs-clean: ## Remove built docs site
	rm -rf docs/site/en/site

# ──── Testing ────

test: ## Run full test suite (unit only, no Docker env)
	$(UV) run pytest tests/ -v --tb=short

test-unit: ## Run unit tests only (no Docker required)
	$(UV) run pytest tests/ -v --tb=short -m "not (db or redis or smtp or s3 or rabbitmq or oidc or integration)"

test-docker: ## Run full test suite against Docker services
	@test -f $(TEST_ENV_FILE) || { echo "ERROR: $(TEST_ENV_FILE) not found. Copy .env.testing.example or run 'make setup'."; exit 1; }
	@$(COMPOSE) ps --format '{{.Health}}' 2>/dev/null | grep -q healthy || \
		{ echo "ERROR: Docker services not running. Run 'make compose-up' first."; exit 1; }
	env $$(grep -v '^\s*#' $(TEST_ENV_FILE) | grep -v '^\s*$$' | xargs) \
		$(UV) run pytest tests/ -v --tb=short

test-integration: ## Run integration-marked tests only (Docker required)
	@test -f $(TEST_ENV_FILE) || { echo "ERROR: $(TEST_ENV_FILE) not found."; exit 1; }
	env $$(grep -v '^\s*#' $(TEST_ENV_FILE) | grep -v '^\s*$$' | xargs) \
		$(UV) run pytest tests/ -v --tb=short -m "integration or db or redis or smtp or s3 or rabbitmq or oidc"

coverage: ## Run tests with coverage report
	@if [ -f $(TEST_ENV_FILE) ]; then \
		env $$(grep -v '^\s*#' $(TEST_ENV_FILE) | grep -v '^\s*$$' | xargs) \
			$(UV) run pytest tests/ -v --cov=src/arvel --cov-report=term-missing --cov-report=html --cov-fail-under=80; \
	else \
		$(UV) run pytest tests/ -v --cov=src/arvel --cov-report=term-missing --cov-report=html; \
	fi

# ──── Code Quality ────

lint: ## Run linter + format check
	$(UV) run ruff check src/ tests/
	$(UV) run ruff format --check src/ tests/

format: ## Auto-format source code
	$(UV) run ruff format src/ tests/

format-check: ## Check formatting without changes
	$(UV) run ruff format --check src/ tests/

typecheck: ## Run type checker
	$(UV) run ty check src/

verify: lint typecheck test ## Run lint + typecheck + test (quick CI gate)

pre-commit: ## Run pre-commit hooks on all files
	$(UV) run pre-commit run --all-files

# ──── Database ────

migrate: ## Run database migrations
	$(UV) run arvel db migrate

seed: ## Seed the database
	$(UV) run arvel db seed

fresh: ## Drop and recreate database + migrate + seed
	@if [ "$$APP_ENV" != "testing" ] && [ "$$APP_ENV" != "development" ] && [ -z "$$APP_ENV" ]; then \
		echo ""; \
		echo "WARNING: APP_ENV is not 'testing' or 'development'."; \
		echo "This will destroy all data. Are you sure? [y/N]"; \
		read -r confirm; \
		if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
			echo "Aborted."; \
			exit 1; \
		fi; \
	fi
	$(UV) run arvel db fresh
