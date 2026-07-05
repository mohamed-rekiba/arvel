"""Bootstrap — the ASGI lifespan seam.

The register→boot→(serve)→terminate sequence, as an async context manager the
ASGI server drives. T1.3 ships the core boot/terminate; later phases extend it
(env loading + provider discovery in T1.4, DB/redis pool open/close in T5, the
BootReporter in T1.5).

Grounded in knowledge/port/03-application-providers-bootstrap.md.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from arvel.kernel.application import Application
from arvel.kernel.boot_report import BootReporter
from arvel.kernel.discovery import bootstrap_providers
from arvel.kernel.globals import set_application
from arvel.kernel.logging import configure_logging
from arvel.kernel.service_provider import load_config_directory
from arvel.kernel.settings import load_dotenv


def bootstrap_app(app: Application) -> None:
    """Synchronous boot preparation — everything that must run **before** the served ASGI app is
    built so its bindings and routes exist: set the global app, load ``.env`` + ``config/*.py``,
    configure logging, register providers (binding the router etc.), and attach the boot reporter.

    The async ``app.boot()`` is run **separately** — in :func:`lifespan` (workers/direct use) or the
    served app's lifespan (:func:`serve_lifespan`) — because provider ``boot()`` may be async while
    the ASGI app must be constructed synchronously with its routes already in place.

    Idempotent: a second call (e.g. ``as_asgi()`` invoked twice) is a no-op, so providers aren't
    re-discovered and the boot reporter isn't subscribed twice.
    """
    if app.bootstrapped:
        return
    set_application(app)
    load_dotenv(Path(app.base_path) / ".env")  # .env → os.environ (no override)
    load_config_directory(app, app.config_dir)  # config/*.py → repo (with_config_dir may override)
    configure_logging(json_logs=app.config("app.env", "local") == "production")
    bootstrap_providers(app)  # framework + installed-package + app providers
    load_route_files(app)  # import route files → register their Route.* defs into the bound router
    # Boot/shutdown reporting (server/worker path only). Subscribe before boot.
    BootReporter(app, level=app.config("app.boot_report", "summary")).register()
    app.bootstrapped = True


# Named route groups → kernel middleware group + URL prefix (web=stateful/no-prefix,
# api=stateless+/api). An unrecognized name maps to a same-named group with no prefix.
_ROUTE_GROUPS: dict[str, dict[str, str]] = {
    "web": {"group": "web"},
    "api": {"group": "api", "prefix": "/api"},
}


def load_route_files(app: Application) -> None:
    """Import every registered route file so its module-level ``Route.*`` definitions register into
    the bound router. Routes reach the router only as a side effect of importing the file that calls
    ``Route.get(...)``; ``load_routes_from`` / ``with_routing`` record the *paths*, and this is the
    step that actually loads them (B5). Runs after providers (so the router is bound and providers'
    ``load_routes_from`` has appended) — guarded by ``bootstrap_app``'s idempotency so routes aren't
    registered twice. Paths resolve against ``base_path`` and are executed as Python (trusted tree);
    each distinct file is imported at most once; a missing file is skipped.

    Named groups from the fluent builder (``with_routing(web=…, api=…)``) are imported **inside their
    route group** so their defs inherit the matching kernel middleware group + URL prefix; flat
    registrations (``load_routes_from`` / legacy ``route_files``) import ungrouped.
    """
    from arvel.kernel.logging import LogManager

    log = LogManager().channel("bootstrap")
    router = app.make("router") if app.bound("router") else None
    seen: set[str] = set()
    # 1. named groups (web/api/…) — imported under their group + prefix; console is not HTTP, skip it
    for index, (name, raw) in enumerate(app.routing.items()):
        if name == "console":
            continue
        _import_route_file(
            app, raw, seen, index, log, router, _ROUTE_GROUPS.get(name, {"group": name})
        )
    # 2. flat / legacy route files (load_routes_from, providers) — no group; web/api already deduped
    for index, raw in enumerate(app.route_files):
        _import_route_file(app, raw, seen, 1000 + index, log, None, {})


def _import_route_file(
    app: Application,
    raw: str,
    seen: set[str],
    index: int,
    log: Any,
    router: Any,
    group_opts: dict[str, str],
) -> None:
    """Resolve + import one route file (at most once), optionally inside a router group context."""
    import contextlib
    import importlib.util

    path = Path(raw)
    if not path.is_absolute():
        path = Path(app.base_path) / path
    path = path.resolve()  # collapse ../ + symlinks so different spellings dedup to one import
    resolved = str(path)
    if resolved in seen:
        return
    seen.add(resolved)
    if not path.is_file():
        # a deliberately-recorded route file gone missing is a bug, not a silent no-op
        log.warning("route_file_not_found", path=raw)
        return
    spec = importlib.util.spec_from_file_location(f"_arvel_routes_{index}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return
    module = importlib.util.module_from_spec(spec)
    ctx = (
        router.group(prefix=group_opts.get("prefix", ""), group=group_opts.get("group"))
        if router is not None and group_opts
        else contextlib.nullcontext()
    )
    with ctx:
        spec.loader.exec_module(module)


async def safe_terminate(app: Application) -> None:
    """Best-effort terminate used to clean up a *partial* boot — never raises (a cleanup failure
    must not mask the original boot error)."""
    with contextlib.suppress(Exception):
        await app.terminate()


@contextlib.asynccontextmanager
async def lifespan(app: Application) -> AsyncGenerator[Application]:
    """The full server/worker boot sequence as an async CM: env → logging → providers → boot →
    serve → graceful terminate. If ``boot()`` fails, a partial boot is cleaned up before re-raising
    so half-opened resources (pools, etc.) are still released (M7)."""
    bootstrap_app(app)
    try:
        await app.boot()
    except BaseException:
        await safe_terminate(app)  # a failed boot still runs terminate() before propagating
        raise
    try:
        yield app
    finally:
        await app.terminate()  # terminating hooks: pools disposed, logs flushed


def serve_lifespan(
    app: Application,
) -> Callable[[Any], contextlib.AbstractAsyncContextManager[None]]:
    """A Litestar ``lifespan`` callable that drives the arvel app's async ``boot()``/``terminate()``.

    The synchronous :func:`bootstrap_app` has already run (in ``Application.as_asgi``) so providers
    and routes exist by the time Litestar is built; here we only boot on ASGI startup — cleaning up a
    partial boot on failure (M7) — and terminate on shutdown. Litestar passes its own instance to the
    callable; the arvel ``Application`` is captured in the closure.
    """

    @contextlib.asynccontextmanager
    async def _cm(_litestar: Any) -> AsyncGenerator[None]:
        try:
            await app.boot()
        except BaseException:
            await safe_terminate(app)
            raise
        try:
            yield
        finally:
            await app.terminate()

    return _cm
