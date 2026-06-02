COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend
FRONTEND_RUN := $(COMPOSE) run --rm --no-deps frontend

.PHONY: env up down nuke ps logs migrate migrate-fresh seed build-frontend api-generate test-backend test-frontend test shell-backend shell-frontend

env:
	test -f .env || cp .env.example .env

up: env
	$(COMPOSE) up -d db redis backend frontend
	$(BACKEND) sh -c 'i=0; until python -c "import urllib.request; urllib.request.urlopen(\"http://localhost:8001/healthz\", timeout=2)" >/dev/null 2>&1; do i=$$((i+1)); [ $$i -lt 90 ] || exit 1; sleep 2; done'
	$(FRONTEND) sh -c 'i=0; until node -e "fetch(\"http://localhost:5173\").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1; do i=$$((i+1)); [ $$i -lt 90 ] || exit 1; sleep 2; done'

down:
	$(COMPOSE) down

nuke:
	$(COMPOSE) down -v --remove-orphans || true

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f backend frontend scheduler db redis

migrate:
	$(BACKEND) arvel migrate

migrate-fresh:
	$(BACKEND) arvel migrate:fresh

seed:
	$(BACKEND) arvel db:seed
	$(COMPOSE) rm -sf scheduler || true
	$(COMPOSE) up -d scheduler

build-frontend:
	$(FRONTEND_RUN) sh -lc "npm ci --no-audit --no-fund && npm run build"

api-generate:
	$(BACKEND) arvel openapi:export --stdout --format yaml > frontend/openapi.yaml
	$(FRONTEND) npm run api:generate

test-backend:
	$(BACKEND) pytest tests/unit

test-frontend:
	$(FRONTEND) npm run test

test: test-backend test-frontend

shell-backend:
	$(BACKEND) bash

shell-frontend:
	$(FRONTEND) sh
