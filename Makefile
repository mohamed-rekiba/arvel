.DEFAULT_GOAL := help

SRC := packages/arvel/src packages/arvel/tests
PKG_DIRS := packages
PYTHON_VERSION ?= 3.14

EMULATOR_IMAGES_SCRIPT := packages/arvel/tests/integration/emulators/_images.py
# Recursive `=` (lazy) — Python is only invoked when EMULATOR_IMAGES is
# actually expanded (e.g. by `make pull-emulators`), not on every `make`.
EMULATOR_IMAGES = $(shell uv run --quiet python $(EMULATOR_IMAGES_SCRIPT))

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: sync
sync:  ## Install/sync workspace deps (root extras + every workspace member's extras)
	uv sync --all-packages --all-extras

.PHONY: dev
dev: sync  ## Alias for sync — install everything a contributor needs

.PHONY: lock
lock:  ## Refresh uv.lock
	uv lock

.PHONY: lint
lint: format ## Ruff check
	uv run ruff check --fix $(SRC)

.PHONY: format
format:  ## Ruff format
	uv run ruff format $(PKG_DIRS)

.PHONY: format-check
format-check:  ## Ruff format --check
	uv run ruff format --check $(PKG_DIRS)

.PHONY: typecheck
typecheck:  ## mypy --strict + pyright --strict (scope driven by pyproject.toml)
	uv run mypy
	uv run mypy packages/arvel-search/tests
	uv run mypy packages/arvel-audit/tests
	uv run pyright

.PHONY: test
test:  ## Fast tests — no Docker, no emulators
	uv run pytest packages/arvel/tests -m 'not benchmark and not requires_emulator' -n auto --dist=loadfile --tb=short

.PHONY: print-emulators
print-emulators:  ## Print the pinned emulator image list (one per line) from $(EMULATOR_IMAGES_SCRIPT)
	@uv run --quiet python $(EMULATOR_IMAGES_SCRIPT)

.PHONY: pull-emulators
pull-emulators:  ## Pre-pull emulator images used by test-integration (parallel, no-op if Docker unavailable)
	@# Single shell recipe — each `make` recipe line is its own shell, so `exit 0`
	@# would only exit that line. Joining with `\` keeps the early-exit semantics.
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "Docker not installed; skipping pull. Integration tests will skip cleanly."; \
		exit 0; \
	fi; \
	if ! docker info >/dev/null 2>&1; then \
		echo "Docker daemon not running; skipping pull. Integration tests will skip cleanly."; \
		exit 0; \
	fi; \
	uv run --quiet python $(EMULATOR_IMAGES_SCRIPT) | xargs -n1 -P7 docker pull

.PHONY: test-integration
test-integration: pull-emulators  ## Full tests — boots Docker emulators (S3, Azurite, GCS, Valkey, Mailpit, Postgres, MariaDB)
	uv run pytest packages/arvel/tests -m 'not benchmark' -n auto --dist=loadfile --tb=short

.PHONY: coverage
coverage:  ## Tests + coverage (fail-under 90)
	uv run pytest packages/arvel/tests --cov=arvel --cov-report=term-missing -n auto --dist=loadfile

.PHONY: bench
bench:  ## Run smoke benchmark
	uv run python benchmarks/bench_foundations.py

.PHONY: docs
docs:  ## Build the docs site (strict mode, same as CI)
	uv run mkdocs build --strict

.PHONY: docs-serve
docs-serve:  ## Serve docs locally with live reload
	uv run mkdocs serve

.PHONY: security
security:  ## bandit + pip-audit + gitleaks
	uv run bandit -r packages/arvel/src -l --exclude packages/arvel/src/arvel/_skeleton
	# Unfixed third-party CVEs: docs/security/dependency-exceptions.md
	uv run pip-audit --skip-editable \
		--ignore-vuln PYSEC-2026-89 \
		--ignore-vuln PYSEC-2025-183
	@command -v gitleaks >/dev/null && gitleaks detect --no-banner --source . --config .gitleaks.toml || echo "gitleaks not installed; install with: brew install gitleaks"

.PHONY: sbom
sbom:  ## Generate CycloneDX SBOM (from resolved deps)
	uv export --no-dev --no-hashes --package arvel --format requirements-txt > req-arvel.txt
	uv run cyclonedx-py requirements --pyproject packages/arvel/pyproject.toml --output-format JSON --output-file sbom-arvel.cdx.json req-arvel.txt
	rm -f req-arvel.txt

.PHONY: build
build:  ## Build sdist + wheel
	uv build --package arvel --out-dir dist/arvel

.PHONY: clean
clean:  ## Remove build / cache artifacts
	rm -rf dist build site _site .ruff_cache .pyright .pytest_cache .playwright-mcp htmlcov bootstrap .coverage* coverage.xml
	find . \( -name "__pycache__" -o -name ".mypy_cache" -o -name ".benchmarks" -o -name "dist" \) -type d -prune -exec rm -rf {} +

.PHONY: ci
ci: lint format-check typecheck coverage docs  ## Run the full CI gate locally

.PHONY: pre-commit
pre-commit: lint format-check typecheck security  ## Run the full CI gate locally
	# Skip no-commit-to-branch here: this target is a CI gate, not a commit.
	# The hook still fires on actual `git commit` to block writes to main/master.
	SKIP=no-commit-to-branch uv run pre-commit run --all-files

.PHONY: all
all: sync ci security bench  ## Sync, run CI gate, run security scans, run benchmark
