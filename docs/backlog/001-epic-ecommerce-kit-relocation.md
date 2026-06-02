# Epic: Relocate & rename the e-commerce demo to `kits/arvel-ecommerce-kit`

## Summary
Move the reference app out of `packages/` (where it reads as a publishable library) into a new top-level `kits/` directory, and rename it `arvel-ecommerce-demo` → `arvel-ecommerce-kit`. It stays an installable uv workspace member so `arvel new --kit ecommerce` keeps resolving via import — framework runtime behavior is unchanged. This is a relocation + rename only; no split to a separate repo, no change to how the kit is distributed.

## Naming decisions (apply consistently)
| Thing | From | To |
|---|---|---|
| Directory | `packages/arvel-ecommerce-demo/` | `kits/arvel-ecommerce-kit/` |
| Distribution package | `arvel-ecommerce-demo` | `arvel-ecommerce-kit` |
| Import package | `arvel_ecommerce_demo` | `arvel_ecommerce_kit` |
| Frontend npm package | `arvel-ecommerce-demo-frontend` | `arvel-ecommerce-kit-frontend` |
| CLI kit id (`--kit ecommerce`) | `ecommerce` | `ecommerce` (unchanged) |

The `--kit ecommerce` id stays the same — only the package/dir that backs it is renamed. Keeps the user-facing command stable.

## Scope boundary
- **In scope**: directory move, package + import rename, every config/path reference that points at the old location or name, lockfile regen, green gates.
- **Out of scope**: separate repo, bundling the kit into the `arvel` wheel, changing kit resolution from import to filesystem path, renaming the `ecommerce` CLI id.
- **Leave as historical record** (do NOT edit): `packages/arvel/CHANGELOG.md`, `docs/pipeline/stage-log.yaml`, ADR-021, ADR-049 — these describe past events/locations and should stay accurate to when they were written. ADR-003 is current architecture and *does* get updated (Story 6).

---

## Stories

### Story 1: Relocate and rename the package tree
**As a** framework maintainer, **I want** the demo moved to `kits/arvel-ecommerce-kit/` with its import package renamed, **so that** the repo layout signals "starter kit," not "publishable library."

**Acceptance Criteria**:
- [ ] Given the move uses `git mv`, when `git status` is checked, then history is preserved (renames, not delete+add)
- [ ] Given the new layout, when listing `kits/arvel-ecommerce-kit/`, then it contains `backend/`, `frontend/`, `src/arvel_ecommerce_kit/`, `Makefile`, `docker-compose.yml`, `README.md`, `pyproject.toml`, `.env.example`
- [ ] Given the import rename, when `kits/arvel-ecommerce-kit/src/arvel_ecommerce_kit/__init__.py` is read, then it exposes `kit_root()` and its docstring/comments reference `arvel_ecommerce_kit`
- [ ] Given the package metadata, when `kits/arvel-ecommerce-kit/pyproject.toml` is read, then `name = "arvel-ecommerce-kit"` and the hatch wheel target is `packages = ["backend", "src/arvel_ecommerce_kit"]`
- [ ] Given `git mv`, when `packages/` is listed, then `arvel-ecommerce-demo` is gone

**Files**:
- `git mv packages/arvel-ecommerce-demo kits/arvel-ecommerce-kit`
- `git mv kits/arvel-ecommerce-kit/src/arvel_ecommerce_demo kits/arvel-ecommerce-kit/src/arvel_ecommerce_kit`
- `kits/arvel-ecommerce-kit/pyproject.toml` — `name`, `[tool.hatch.build.targets.wheel] packages`
- `kits/arvel-ecommerce-kit/src/arvel_ecommerce_kit/__init__.py` — comments/docstring

**Security Requirements**:
- [ ] No secrets introduced; `.env` (real) must not be staged if it carries live values — confirm it stays gitignored as today

**Documentation Requirements**:
- [ ] None in this story (docs handled in Story 6)

**Priority**: Must · **Complexity**: Medium · **Status**: Draft

---

### Story 2: Update root workspace + lint path config
**As a** maintainer, **I want** the root `pyproject.toml` to discover the kit at its new path, **so that** `uv sync` and `ruff` keep working.

**Acceptance Criteria**:
- [ ] Given the kit now lives under `kits/`, when `[tool.uv.workspace]` is read, then `members = ["packages/*", "kits/*"]`
- [ ] Given the 3 ruff per-file-ignores, when they're read, then each path starts `kits/arvel-ecommerce-kit/backend/...` (was `packages/arvel-ecommerce-demo/backend/...`)
- [ ] Given the config change, when `uv sync --all-packages --all-extras` runs, then it resolves with no "member not found" error
- [ ] Given `ruff check` on the kit backend, then the per-file ignores still apply (no new E402/RUF001/E501 failures)

**Files**: root `pyproject.toml` — lines ~13 (`members`), ~123, ~161, ~164 (per-file-ignores)

**Security Requirements**:
- [ ] None

**Documentation Requirements**:
- [ ] None

**Priority**: Must · **Complexity**: Small · **Status**: Draft
**Depends on**: Story 1

---

### Story 3: Update the kit registry + its tests
**As an** `arvel new --kit ecommerce` user, **I want** the registry to import the renamed package, **so that** scaffolding still finds the kit tree.

**Acceptance Criteria**:
- [ ] Given `kits.py`, when `_ecommerce_kit_root()` is read, then it does `importlib.import_module("arvel_ecommerce_kit")` and `KitNotInstalledError(package="arvel-ecommerce-kit", ...)`
- [ ] Given the `ecommerce` `KitSpec` description, when read, then it says `(requires arvel-ecommerce-kit package)`
- [ ] Given `test_new_kits.py`, when read, then the install-hint assertions reference `arvel-ecommerce-kit`
- [ ] Given the suite, when `pytest packages/arvel/tests/console/scaffold/test_new_kits.py` runs, then all tests pass
- [ ] Given an installed kit, when `arvel new tmp-app --kit ecommerce --no-install` runs (in a temp dir), then it scaffolds the full-stack tree (exit 0)

**Files**:
- `packages/arvel/src/arvel/console/_scaffold/kits.py` — lines ~75, ~83, ~87, ~105
- `packages/arvel/tests/console/scaffold/test_new_kits.py` — lines ~152, ~167

**Security Requirements**:
- [ ] None

**Documentation Requirements**:
- [ ] None

**Priority**: Must · **Complexity**: Small · **Status**: Draft
**Depends on**: Story 1

---

### Story 4: Update CI workflow
**As a** maintainer, **I want** CI to run the kit's suites from the new path, **so that** the demo keeps gating merges.

**Acceptance Criteria**:
- [ ] Given the `ecommerce-demo` job, when read, then every `working-directory:` is `kits/arvel-ecommerce-kit/backend`
- [ ] Given the `ecommerce-demo-frontend` job, when read, then `cache-dependency-path` and all `working-directory:` entries point at `kits/arvel-ecommerce-kit/frontend`
- [ ] Given the integration command, when read, then `uv run --project <repo-root>` resolves correctly from the new depth (`kits/arvel-ecommerce-kit/backend` → root is still 3 levels up, so `../../..` is unchanged)
- [ ] Given the `build` job, when read, then its `needs:` list still references the (optionally renamed) job ids and they exist
- [ ] (Optional, consistency) job ids/names `ecommerce-demo*` renamed to `ecommerce-kit*` — if renamed, the `needs:` list is updated to match

**Files**: `.github/workflows/ci.yml` — lines 243–291

**Security Requirements**:
- [ ] No credentials added to the workflow; existing service env vars unchanged

**Documentation Requirements**:
- [ ] None

**Priority**: Must · **Complexity**: Small · **Status**: Draft
**Depends on**: Story 1

---

### Story 5: Update container + env path references
**As a** developer running the kit locally, **I want** docker-compose and env files to point at the new path, **so that** `docker compose up` and storage resolution work.

**Acceptance Criteria**:
- [ ] Given `docker-compose.yml`, when read, then `working_dir:` and `cd` commands use `packages` → `kits/arvel-ecommerce-kit/backend` (lines 4, 17, 74, 87)
- [ ] Given `.env.example` (and the local `.env`), when read, then `STORAGE_LOCAL_ROOT` uses the new path
- [ ] Given the frontend `package.json` + `package-lock.json`, when read, then `name` is `arvel-ecommerce-kit-frontend`
- [ ] Given `npm ci` in the frontend dir, then it succeeds with the renamed lockfile
- [ ] (Optional) `JWT_ISSUER` / `JWT_AUDIENCE` updated to `arvel-ecommerce-kit` — cosmetic; only if no env depends on the old value

**Files**:
- `kits/arvel-ecommerce-kit/docker-compose.yml`
- `kits/arvel-ecommerce-kit/.env.example`, `.env`
- `kits/arvel-ecommerce-kit/frontend/package.json`, `package-lock.json`

**Security Requirements**:
- [ ] Don't commit the real `.env` if it holds live secrets — keep gitignore behavior intact

**Documentation Requirements**:
- [ ] None

**Priority**: Should · **Complexity**: Small · **Status**: Draft
**Depends on**: Story 1

---

### Story 6: Sweep documentation references
**As a** reader of the docs, **I want** doc references to match the new name/path, **so that** instructions are accurate.

**Acceptance Criteria**:
- [ ] Given the kit's own `README.md`, when read, then the `cd` path is `kits/arvel-ecommerce-kit`
- [ ] Given the root `README.md` (line ~405), then the table links `kits/arvel-ecommerce-kit`
- [ ] Given `mkdocs.yml` (line 213) and the doc page, then the page renders (rename `ecommerce-demo.md` → `ecommerce-kit.md` and the nav entry, or keep filename and only update content — pick one and keep nav consistent)
- [ ] Given `docs/site/docs/*` (index, packages/README, packages/ecommerce-demo, releases, frontend/integration, contributions), then path/name references read `arvel-ecommerce-kit` / `kits/...`
- [ ] Given `docs-fresh/*` (packages/overview, packages/ecommerce-demo, architecture/overview, reference/source-map, reference/CUTOVER-NOTES, contributing/repo-and-build), then references updated
- [ ] Given ADR-003 (current architecture), then the workspace table row reads `arvel-ecommerce-kit`
- [ ] Given `mkdocs build --strict`, then it succeeds with no broken-link warnings

**Files**: see reference map in Notes. **Do not touch** CHANGELOG, stage-log.yaml, ADR-021, ADR-049.

**Security Requirements**:
- [ ] None

**Documentation Requirements**:
- [ ] This story *is* the doc update

**Priority**: Should · **Complexity**: Medium · **Status**: Draft
**Depends on**: Story 1

---

### Story 7: Regenerate lockfile & verify all gates
**As a** maintainer, **I want** the lockfile regenerated and the full gate green, **so that** the move is provably non-breaking.

**Acceptance Criteria**:
- [ ] Given the renamed member, when `uv sync --all-packages --all-extras` runs, then `uv.lock` updates with `arvel-ecommerce-kit` and no `arvel-ecommerce-demo`
- [ ] Given the changes, when `make pre-commit` (or the project's gate: ruff, mypy, pyright, bandit, pip-audit, gitleaks) runs, then it exits 0 with zero warnings
- [ ] Given the framework suite, when `pytest packages/arvel` runs, then green (kit-registry tests included)
- [ ] Given the kit backend, when its integration suite runs the way CI does, then green
- [ ] Given a repo-wide search for `arvel-ecommerce-demo` / `arvel_ecommerce_demo`, then the only remaining hits are the intentional historical records (CHANGELOG, stage-log, ADR-021, ADR-049)

**Files**: `uv.lock` (generated)

**Security Requirements**:
- [ ] `gitleaks` and `pip-audit` clean

**Documentation Requirements**:
- [ ] None

**Priority**: Must · **Complexity**: Small · **Status**: Draft
**Depends on**: Stories 1–6

---

## Dependencies
- Story 1 unblocks everything.
- Stories 2, 3, 4, 5, 6 are independent of each other and can run in parallel after Story 1.
- Story 7 runs last (verification gate).

## Estimated total complexity
Medium overall — high file count, low per-file risk. No framework runtime logic changes; the only executable-code edits are the kit registry import name (Story 3) and config/path strings everywhere else.

## Notes — full reference map (verified by grep, excludes `uv.lock`)
**Path refs (`packages/arvel-ecommerce-demo`)**: root `pyproject.toml` (123, 161, 164); `.github/workflows/ci.yml` (255, 271, 273, 276, 279, 282, 285); `docker-compose.yml` (4, 17, 74, 87); `.env`/`.env.example` (storage root); kit `README.md` (43); root `README.md` (405); docs-fresh source-map/overview/repo-and-build; docs/site contributions.

**Import name (`arvel_ecommerce_demo`)**: `src/arvel_ecommerce_demo/__init__.py` (22, 23, 25); `kits.py` (83); hatch build target in kit `pyproject.toml` (49).

**Dist name (`arvel-ecommerce-demo`)**: kit `pyproject.toml` (2); `kits.py` (87, 105); `test_new_kits.py` (152, 167); frontend `package.json`/`package-lock.json` name; many doc pages.

**CLI id**: `ecommerce` — unchanged.

**Leave as historical**: `packages/arvel/CHANGELOG.md` (94); `docs/pipeline/stage-log.yaml` (253); ADR-021 (55); ADR-049 (8).

## Verification commands
```bash
# after the move
uv sync --all-packages --all-extras
ruff check .
pytest packages/arvel/tests/console/scaffold/test_new_kits.py -q
mkdocs build --strict
# residual-name check (expect only historical hits)
rg -n "arvel-ecommerce-demo|arvel_ecommerce_demo" --glob '!uv.lock'
```
