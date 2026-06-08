# Epic: Storage drivers raise one missing-file exception

## Summary
A missing file produced an unrelated exception per disk — `MemoryDriver` raised
`StorageFileNotFoundError`, `LocalDriver` raised the builtin `FileNotFoundError`. They were
disjoint `OSError` branches, so disk-agnostic callers had nothing single to catch.
`StorageFileNotFoundError` now subclasses the builtin and every driver raises it.

**Module:** storage / filesystem · **Spec:** `docs/pipeline/specs/WI-arvel-006-storage-missing-file-contract.md`

## Stories

### Story 1: One exception for a missing file across every disk
**As an** application developer, **I want** `disk.get(...)` / `disk.size(...)` to raise the same
exception on every disk when a file is missing, **so that** my disk-agnostic code can catch one
type instead of branching per driver.

**Acceptance Criteria**:
- [x] Given a missing file, when `LocalDriver.get` runs, then it raises `StorageFileNotFoundError`.
- [x] Given a missing file, when `LocalDriver.size` runs, then it raises `StorageFileNotFoundError` (mirrors `MemoryDriver`).
- [x] Given a missing file on any driver, when caught with `except FileNotFoundError`, then the builtin catches it (the storage type subclasses the builtin).
- [x] Given `MemoryDriver`, when a file is missing, then behavior is unchanged (regression guard).

**Security Requirements**:
- [x] None — error-typing change only; no read path or traversal guard altered.

**Documentation Requirements**:
- [x] `docs/site/docs/features/storage.md` "Retrieving Files" documents the unified missing-file contract.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Existing catchers keep working without churn
**As a** framework maintainer, **I want** the fix to avoid rewriting every `except FileNotFoundError`
call-site, **so that** the serve route, media cleanup, console, and maintenance code stay correct.

**Acceptance Criteria**:
- [x] Given the unified exception subclasses the builtin, when existing `except FileNotFoundError` blocks run (serve route 404, `media/model.py::_delete_quiet`), then they still catch a missing file.
- [x] Given no call-site changes, when the storage + media suites run, then all pass (834).

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] Spec records why subclassing the builtin was chosen over call-site swaps.

**Requirement Refs**: SPEC-3, SPEC-5
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..005.

## Notes
- Two prior suspicions were cleared, not fixed:
  - **Path traversal** in `LocalDriver._safe_path` — false positive (`startswith(root + "/")` blocks sibling-prefix bypass).
  - **`except FileNotFoundError, StoragePathError:`** — valid under Python 3.14 (PEP 758), equivalent to `except (A, B)`.
- Deferred follow-ups (separate work items):
  - **F2** — `LocalDriver.size` on a directory returns the dir size rather than erroring (file-vs-dir parity).
  - **F3** — `url()` does no path validation (matches Laravel; reads validated at serve time).
  - **F4** — cloud drivers' (`S3`/`GCS`/`Azure`) missing-key paths not exercised here (cloud-parity WI).
