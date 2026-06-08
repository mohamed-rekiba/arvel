# Epic: `arvel shell` boots lazily, like Laravel Tinker

## Summary
The interactive shell must open even when the database is unreachable. Today
`DatabaseServiceProvider.boot()` runs an eager `SELECT 1` probe; when the DB host
can't be resolved the probe raises `DatabaseConnectionError` → `BootError`, so the
REPL never starts (and blocks on DNS/connect first). Laravel Tinker survives a dead
DB because connections are lazy — boot never opens a socket; the error surfaces on
the first query. We adopt the same model for the shell: same provider chain, but a
boot that skips the eager connectivity probe. The engine, session-maker, and `DB`
facade stay configured, so the ORM is fully usable and connects on first use.

**Module:** application kernel · console (shell) · **Research:** `.context/research/024-tinker-shell-bootstrap.md` · **Spec:** `docs/pipeline/specs/WI-arvel-024-shell-lazy-database-boot.md`

## Stories

### Story 1: The shell opens when the database is down
**As a** developer, **I want** `arvel shell` to launch even when the database is
unreachable, **so that** I can inspect config, run non-DB code, and explore the app
without a live DB — exactly like `php artisan tinker`.

**Acceptance Criteria**:
- [ ] Given the configured DB host can't be resolved (or refuses connections), when I run `arvel shell`, then the REPL launches instead of aborting with `BootError`.
- [ ] Given a down DB, when the shell boots, then no eager `SELECT 1` probe runs (no DNS/connect stall at startup).
- [ ] Given the shell boots with probing off, when boot completes, then every provider in the chain still booted and every facade (`Cache`, `Auth`, `Config`, `DB`, …) is reachable in the namespace.

**Security Requirements**:
- [ ] DB host/URL must not leak into REPL output or logs on the lazy-connect path (same redaction contract as `DatabaseConnectionError`).

**Documentation Requirements**:
- [ ] Note in the shell docs that the REPL connects to the DB lazily (errors surface on first query), mirroring Tinker.

**Requirement Refs**: C1
**Priority**: Must · **Complexity**: Small · **Status**: Draft

### Story 2: ORM stays usable and errors surface lazily on first query
**As a** developer in the shell, **I want** the engine, session, and `DB` facade
configured even when probing is off, **so that** `await User.find(1)` works against a
healthy DB and raises a clear connection error on first use when the DB is down —
not at boot.

**Acceptance Criteria**:
- [ ] Given a healthy DB, when I run a query in the shell, then it executes normally (engine/session/`DB` facade are wired regardless of the probe).
- [ ] Given a down DB, when I run my first query, then the underlying SQLAlchemy connection error is raised at that call site, not during boot.
- [ ] Given probing is off at boot, when the provider finishes `boot()`, then `DB.configure(...)`/`configure_engine(...)` and the `async_sessionmaker` binding still ran.

**Security Requirements**:
- [ ] None beyond Story 1's redaction contract.

**Documentation Requirements**:
- [ ] None beyond Story 1.

**Requirement Refs**: C2
**Priority**: Must · **Complexity**: Small · **Status**: Draft

### Story 3: Server and CLI keep eager fail-fast
**As an** operator, **I want** `serve` and DB-using CLI commands to still fail loudly
at boot when the DB is unreachable, **so that** I never start serving traffic or run
a command against a database that isn't there.

**Acceptance Criteria**:
- [ ] Given `Application.boot()` is called with default settings (probing on), when the DB is unreachable, then it still raises `BootError`/`DatabaseConnectionError` as today.
- [ ] Given the new boot option, when no caller opts out, then existing server/CLI/test boot behavior is byte-for-byte unchanged.
- [ ] Given only the shell opts out, when other entrypoints boot, then they are unaffected.

**Security Requirements**:
- [ ] None (preserves the existing fail-fast guard for production serving).

**Documentation Requirements**:
- [ ] None — internal boot contract; covered by spec + docstring.

**Requirement Refs**: C3
**Priority**: Must · **Complexity**: Small · **Status**: Draft

## Dependencies
- Builds on the single-event-loop shell bootstrap (epic 014) and the provider
  lifecycle drained at shutdown (epic 023). No blockers.

## Notes
- Lever is **boot semantics**, not the provider set — trimming providers would break
  the "everything reachable" REPL contract that both Tinker and arvel intend.
- The boot probe sets no connect timeout, so a reachable-but-hung host can still stall
  the server's boot. Out of scope here; tracked as a follow-up (bounded connect
  timeout on the probe).
