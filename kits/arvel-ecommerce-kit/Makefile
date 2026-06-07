# --env-file points compose's ${VAR} interpolation at backend/.env, the same
# file the services inject via env_file. Keeps container ports/passwords and the
# app's own config reading from one source. compose errors if it's missing, so
# every lifecycle target below depends on `env`.
COMPOSE := docker compose --env-file backend/.env
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend
FRONTEND_RUN := $(COMPOSE) run --rm --no-deps frontend

.PHONY: env up down nuke ps logs migrate migrate-fresh seed build-frontend api-generate test-backend test-frontend test shell-backend shell-frontend

env:
	test -f backend/.env || cp backend/.env.example backend/.env

up: env
	$(COMPOSE) up -d --wait

down: env
	$(COMPOSE) down

nuke: env
	$(COMPOSE) down -v --remove-orphans || true

ps: env
	$(COMPOSE) ps

logs: env
	$(COMPOSE) logs -f backend frontend scheduler db redis

migrate:
	$(BACKEND) arvel migrate

migrate-fresh:
	$(BACKEND) arvel migrate:fresh

seed: env
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
