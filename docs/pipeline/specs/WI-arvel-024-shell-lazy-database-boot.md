# WI-arvel-024 — `arvel shell` boots lazily, like Laravel Tinker

- **Module**: 24 — application kernel (`Application.boot`) · console (`shell`)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`arvel shell` (and its `tinker` alias) crashed before the REPL opened whenever
the database was unreachable. `DatabaseServiceProvider.boot()` ran an eager
`SELECT 1` connectivity probe; a host that won't resolve raised
`DatabaseConnectionError` → `BootError`, after first blocking on DNS/connect —
which is also where the "shell takes a long time" symptom came from.

```
gaierror: [Errno 8] nodename nor servname provided, or not known
BootError: Provider DatabaseServiceProvider failed during boot: gaierror(...)
```

Laravel Tinker survives a dead DB because Laravel connections are **lazy** — boot
never opens a socket; the PDO connection (and any error) appears on the first
query. The shell wants the same: full provider chain, but no eager probe.

Research: `.context/research/024-tinker-shell-bootstrap.md`. Confirmed the DB ping
is the only eager network probe on the boot path — `DatabaseService.connect()` is
a no-op, so nothing else opens a socket at boot.

## Fix

Add a boot-time switch that infra providers honour:

```python
# Application
async def boot(self, *, probe_connections: bool = True) -> None:
    if self._booted:
        return
    self._probe_connections = probe_connections
    ...

def probe_connections(self) -> bool:
    return self._probe_connections
```

```python
# DatabaseServiceProvider.boot — ping only when probing is on
engine = self.app.container.make(AsyncEngine)
if self.app.probe_connections():
    try:
        async with engine.connect() as conn:
            await conn.execute(_PING)
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(...) from exc
# engine / session-maker / DB facade are wired regardless → ORM stays usable
```

```python
# ShellCommand.run_repl — open the REPL lazily
loop.run_until_complete(framework_app.boot(probe_connections=False))
```

Default stays `probe_connections=True`, so `serve` and DB-using CLI commands keep
their eager fail-fast boot. Only the shell opts out.

## Acceptance criteria

- The shell opens even when the DB is unreachable; no eager probe runs.
- The ORM (engine, session-maker, `DB` facade) is configured after a lazy boot;
  a query against a healthy DB works, and a dead DB only errors on first query.
- `Application.boot()` with defaults still raises `BootError`
  (`__cause__` is `DatabaseConnectionError`) when the DB is unreachable.
- mypy, pyright, ruff check clean; affected suites green.

## Out of scope (deferred)

- A bounded connect timeout on the eager probe so a reachable-but-hung host can't
  stall the server's boot — separate follow-up.

## Files

- `packages/arvel/src/arvel/application/application.py`
- `packages/arvel/src/arvel/providers/database_provider.py`
- `packages/arvel/src/arvel/console/commands/shell.py`
- `packages/arvel/tests/database/test_database_provider.py`
- `packages/arvel/tests/console/test_shell_extended.py` (new case)
- `docs/site/docs/cli/commands.md`
