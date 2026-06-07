COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend
FRONTEND_RUN := $(COMPOSE) run --rm --no-deps frontend

.PHONY: env up down nuke ps logs migrate migrate-fresh seed build-frontend api-generate test-backend test-frontend test shell-backend shell-frontend

env:
	test -f .env || cp .env.example .env

up: env
	$(COMPOSE) up -d --wait

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
	$(BACKEND) arvel openapi:export --output ../frontend/openapi.yaml --format yaml
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
