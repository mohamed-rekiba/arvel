# WI-arvel-006 — Storage drivers must raise one missing-file exception

| | |
|---|---|
| **Module** | storage / filesystem |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/006-storage-media.md` (F1) |
| **Review** | defect confirmed by reading both drivers + tests; path-traversal & `except A, B` syntax cleared as non-issues |

## Problem

A missing file produced **different, unrelated** exceptions per disk:

- `MemoryDriver.get`/`size` → `StorageFileNotFoundError` (extended only `StorageDriverError`).
- `LocalDriver.get` → builtin `FileNotFoundError`; `LocalDriver.size` → builtin
  `FileNotFoundError` implicitly via `Path.stat()`.

`StorageFileNotFoundError` did **not** subclass the builtin, so the two were disjoint `OSError`
branches. A disk-agnostic caller using `Storage.disk(name)` had no single exception to catch for
"file missing." The driver tests baked the split in (local asserted the builtin, memory the
storage type).

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `LocalDriver.get` on a missing file raises `StorageFileNotFoundError`. | `tests/storage/test_drivers.py::test_local_driver_full_file_lifecycle` | PASS |
| SPEC-2 | `LocalDriver.size` on a missing file raises `StorageFileNotFoundError` (mirrors memory). | `...::test_local_driver_size_missing_raises` | PASS |
| SPEC-3 | The unified error is catchable as the builtin `FileNotFoundError` (preserves existing catchers). | `...::test_local_missing_is_catchable_as_builtin` | PASS |
| SPEC-4 | `MemoryDriver` behavior unchanged (regression guard). | `tests/storage/test_memory_driver.py` + `...::test_memory_driver_size_missing_raises` | PASS |
| SPEC-5 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean on changed files; storage + media suites green. | `mypy` + `pyright` + `ruff` + `pytest` (834 passed) | PASS |

## Root-cause fix

- `storage/exceptions.py` — `StorageFileNotFoundError(FileNotFoundError, StorageDriverError)`.
  One type, raised by every driver, catchable as the storage taxonomy *or* the builtin. MRO:
  `[StorageFileNotFoundError, FileNotFoundError, StorageDriverError, OSError, …]`.
- `storage/drivers/local.py` — `get` and `size` raise `StorageFileNotFoundError` explicitly
  (existence check before `read_bytes`/`stat`), matching `MemoryDriver`.
- Tests unified to assert `StorageFileNotFoundError`; added local `size`-missing and
  builtin-catchability tests.

## Deliberate design decisions

- **Subclass the builtin** instead of swapping every caller. The serve route
  (`storage_provider.py`), `media/model.py::_delete_quiet`, console, and maintenance all catch
  builtin `FileNotFoundError`; subclassing keeps them working while giving disk-agnostic callers
  one storage type. No call-site churn, no shims.
- **Left `except FileNotFoundError, StoragePathError:` as-is** — valid under Python 3.14 PEP 758
  (== `except (A, B)`), and it still catches the unified exception.

## Cleared (not defects)

- **Path traversal** in `LocalDriver._safe_path` — false positive; the `startswith(root + "/")`
  guard blocks sibling-prefix bypass (`../app_evil`). Covered by `test_local_driver_blocks_path_traversal`.
- **`except A, B:` syntax** — valid in 3.14 (PEP 758), verified empirically.

## Deferred (tracked)

- **F2** — `LocalDriver.size` on a directory returns the dir size rather than erroring (file-vs-dir parity).
- **F3** — `url()` does no path validation (matches Laravel; reads are validated at serve time).
- **F4** — cloud drivers' (`S3`/`GCS`/`Azure`) missing-key paths not exercised here (cloud-parity WI).
