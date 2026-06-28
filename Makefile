# arvel — developer tasks. The gate targets mirror `make check` + CI.
# Prefer `uv run` so it works without an activated venv; falls back to PATH tools.
RUN ?= uv run

.DEFAULT_GOAL := help

.PHONY: help install lock lint format typecheck imports security test test-parallel coverage audit check \
        hooks docs docs-serve pre-commit clean stubs build test-integration

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Create the dev environment (editable, all extras + dev tools)
	uv pip install -e ".[all,dev,docs]"

lock:  ## Refresh uv.lock
	uv lock

lint:  ## Ruff lint
	$(RUN) ruff check src tests

format:  ## Ruff format (writes)
	$(RUN) ruff format src tests

format-check:  ## Ruff format (check only)
	$(RUN) ruff format --check src tests

typecheck:  ## Strict mypy + pyright (G3)
	$(RUN) mypy
	$(RUN) pyright

imports:  ## import-linter — architecture + startup-NFR contracts (G1/G2)
	$(RUN) lint-imports

security:  ## bandit static security scan
	$(RUN) bandit -q -r src

test:  ## pytest (includes G2 startup NFR + G4 stack-fidelity)
	$(RUN) pytest

test-parallel:  ## pytest across CPU cores (pytest-xdist); same unit suite, process-isolated workers
	$(RUN) pytest -n auto

test-integration:  ## integration tier — real services via testcontainers (needs Docker)
	$(RUN) pytest -m integration

coverage:  ## pytest under coverage; enforce line coverage >= 95%
	$(RUN) bash tools/coverage_gate.sh

audit:  ## pip-audit (blocking; one documented carve-out — see DR-0008 / SECURITY.md)
	# GHSA-qhqw-rrw9-25rm (asyncmy SQLi): no upstream fix; optional mysql extra; not
	# reachable via arvel's ORM (dict-key path). Accepted-risk per DR-0008. Any OTHER
	# new high/critical CVE blocks. Drop the ignore when asyncmy ships a fix.
	$(RUN) pip-audit --ignore-vuln GHSA-qhqw-rrw9-25rm

check: lint format-check typecheck imports security audit coverage  ## All gates + coverage (what CI runs)

stubs:  ## Regenerate facade type stubs (.pyi) from the live backing classes
	$(RUN) python tools/gen_facade_stubs.py

build:  ## Build sdist + wheel into dist/
	uv build

hooks:  ## Install pre-commit git hooks
	$(RUN) pre-commit install

docs:  ## Build the Zensical docs site
	$(RUN) zensical build

docs-serve:  ## Serve the docs locally with live reload
	$(RUN) zensical serve

pre-commit:  ## Run pre-commit checks (lint, format, typecheck, imports, security)
	$(RUN) pre-commit run --all-files

clean:  ## Remove build/test artifacts
	rm -rf .site .cache .pytest_cache .mypy_cache .ruff_cache .hypothesis .import_linter_cache .coverage.json dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
