# Epic: Database cache driver uses the app connection

## Summary
The `database` cache driver was non-functional out of the box: the manager built a throwaway
in-memory SQLite engine (per-process, ephemeral, table never created → `no such table:
cache_entries` on first use), and the published migration created a `cache` table with an
`expiration` column the store never reads. The driver now uses the app's default DB connection and
a migration matching the store's `cache_entries` table.

**Module:** cache · **Spec:** `docs/pipeline/specs/WI-arvel-007-database-cache-driver.md`

## Stories

### Story 1: The database cache driver actually persists to the app database
**As an** application developer, **I want** `CACHE_CONNECTION=database` to store cache entries in
my application's database, **so that** the cache is shared across processes and survives restarts
like Laravel's database cache.

**Acceptance Criteria**:
- [x] Given a configured DB and the cache table, when I `put`/`get` via the `database` driver, then the value is stored in and read from the app's default connection (not a throwaway `:memory:` engine).
- [x] Given no DB configured, when the `database` store is built, then it raises a clear `RuntimeError` ("DB not configured") instead of silently using `:memory:` and failing later.

**Security Requirements**:
- [x] None — uses the existing app connection; no new credentials or surface.

**Documentation Requirements**:
- [x] `docs/site/docs/features/cache.md` replaces the "not yet wired" warning with the publish-migration-then-use instructions.

**Requirement Refs**: SPEC-1, SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: The published migration matches what the store reads
**As an** application developer, **I want** the cache migration to create the table the
`DatabaseStore` actually uses, **so that** publishing and running it enables the driver without a
silent schema mismatch.

**Acceptance Criteria**:
- [x] Given the published cache migration, when it runs, then it creates `cache_entries(key, value, expires_at)` — the exact table/columns the store reads.
- [x] Given the framework-migration table list, when validated, then it reflects the corrected `cache_entries` name.

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] Driver table noted as `cache_entries` in the cache docs.

**Requirement Refs**: SPEC-3, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..006.

## Notes
- The kit uses `redis`, so this is a framework-correctness fix with no kit runtime impact — but it
  makes an advertised first-class driver actually work and matches Laravel's database cache.
- Cleared as non-defects: `remember` not single-flight (matches Laravel), whole-table/dir `flush`
  (matches Laravel), `_get_or_create_mutex` "race" (asyncio false positive — sync, no `await`).
- Deferred follow-ups (separate work items):
  - **F3** — `ttl <= 0` inconsistent across stores (redis forever / array-file gone / database sub-second); Laravel forgets on `ttl<=0` (TTL-contract WI).
  - **F4** — `RateLimiter.attempt()` non-atomic read-modify-write (needs store-level atomic increment).
  - **F5** — parity-additive: `add`/`pull`/`missing`/`rememberForever`/`increment`/`decrement` on the facade; `many`/`put_many` on the manager/facade.
  - **F6** — `Cache.facade.assert_stored` prefix-join missing `:` (test-helper edge).
