# WI-arvel-007 — Database cache driver must use the app connection + matching migration

| | |
|---|---|
| **Module** | cache |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/007-cache.md` (F1/C2 + F2/C1; F1 reproduced empirically) |
| **Review** | two coupled defects confirmed; `remember`/`flush`/mutex "criticals" cleared as Laravel-correct or asyncio false positives |

## Problem

The `database` cache driver was non-functional out of the box, in two coupled ways:

1. **C2** — `CacheManager._make_store(DATABASE)` built a throwaway `create_async_engine(":memory:")`
   and never created the table. First `put`/`get` raised
   `OperationalError: no such table: cache_entries`. Even with a table, `:memory:` is per-process
   and ephemeral — useless as a shared cache. The docs admitted it "is not yet wired to your
   application database."
2. **C1** — the published migration `create_cache_table.py` created table `cache` with column
   `expiration`, but `DatabaseStore` reads `cache_entries` with `expires_at`. Publishing+running
   the migration produced a table the store never uses.

Together: the documented path (publish migration → migrate → use `database` driver) could never work.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | The `database` driver uses the app's default DB connection; a write via the manager lands in that connection. | `tests/cache/test_cache_manager_drivers.py::test_database_driver_uses_app_connection` | PASS |
| SPEC-2 | When the DB isn't configured, building the `database` store raises a clear `RuntimeError` (no silent `:memory:`). | `...::test_database_driver_without_db_configured_raises` | PASS |
| SPEC-3 | The published migration creates exactly `cache_entries(key, value, expires_at)` — the columns the store reads. | `...::test_cache_migration_matches_database_store_table` | PASS |
| SPEC-4 | The framework-migration table list reflects the corrected name (`cache_entries`). | `tests/database/test_framework_migrations.py::test_framework_migrations_define_expected_tables` | PASS |
| SPEC-5 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean on changed files; full arvel suite green. | `mypy` + `pyright` + `ruff` + `pytest` (4295 passed) | PASS |

## Root-cause fix

- `cache/__init__.py` — DATABASE branch resolves `DB.session_maker_for()` (the app's default
  connection) instead of a throwaway `:memory:` engine. `DatabaseStore` already depends on
  `arvel.database`, so the lazy import adds no new coupling. The lazy resolution (first cache
  access) means DB is configured by then.
- `cache/migrations/create_cache_table.py` — creates `cache_entries(key VARCHAR(255) PK, value
  TEXT, expires_at INTEGER)`, matching `DatabaseStore.CacheEntry`.

## Deliberate design decisions

- **Use the default connection**, not a new `CACHE_DB_CONNECTION` config field (YAGNI; Laravel
  defaults to the default connection too). A named-connection option can come later if needed.
- **Don't auto-create the table** on the shared app engine — surprising DDL. The published
  migration is the documented, Laravel-parity path.
- **Clear error over silent fallback** — `session_maker_for()` raising "DB not configured" is far
  better than the previous silent `:memory:` + later "no such table".

## Cleared (not defects)

- `remember()` not single-flight — matches Laravel (only `flexible` locks).
- `flush()` clears whole table/dir — matches Laravel.
- `_get_or_create_mutex` "race" — false positive (sync, no `await`); unused `_mutex_registry_lock`
  is dead code (Low, tracked).

## Deferred (tracked)

- **F3 (H4)** — `ttl <= 0` inconsistent across stores (redis forever / array-file gone / database
  sub-second). Laravel forgets on `ttl<=0`. Normalize at the store boundary (TTL-contract WI).
- **F4** — `RateLimiter.attempt()` non-atomic RMW (needs store-level atomic increment).
- **F5** — parity-additive: `add`/`pull`/`missing`/`rememberForever`/`increment`/`decrement` on
  the facade; `many`/`put_many` on the manager/facade.
- **F6** — `Cache.facade.assert_stored` prefix-join missing `:` (test-helper edge).
