"""arvel.http.maintenance — maintenance mode (Laravel ``artisan down`` / ``up``).

State lives in the **default cache driver** — whatever the app is configured to use
(``array`` in-process, ``redis`` shared, or any other store). So the reach of ``down`` follows
your cache: with Redis every instance sees it at once and it survives restarts; with the
in-process ``array`` driver it's local to one process (fine for a single instance, but a
CLI ``arvel down`` won't reach a separate server process — point ``cache.default`` at Redis for
multi-process / multi-instance maintenance).

``down()`` writes the flag, ``up()`` removes it, ``is_down()`` reads it;
``PreventRequestsDuringMaintenance`` returns 503 while it's set.
"""

from __future__ import annotations

from typing import Any, cast

#: Cache key holding the maintenance payload (absent ⇒ the app is up).
KEY = "arvel:maintenance"


def _cache() -> Any:
    # Use the app-bound cache when booted, else a default CacheManager — so `arvel down`/`up` work
    # from the CLI without a fully-booted app. http→cache is a legal downward edge (DR-0026); the
    # support ``cache()`` helper can't be used here because support is a leaf that no longer
    # constructs a cache app-less.
    from arvel.kernel import app, has_application

    if has_application() and app().bound("cache"):
        return app().make("cache").driver()
    from arvel.cache import CacheManager

    return CacheManager().driver()


async def down(message: str = "Down for maintenance.", retry: int = 60) -> None:
    """Enter maintenance mode — store the flag (no TTL ⇒ until ``up``) with a Retry-After hint."""
    await _cache().put(KEY, {"message": message, "retry": retry})


async def up() -> None:
    """Leave maintenance mode — drop the flag (no-op if already up)."""
    await _cache().forget(KEY)


async def is_down() -> bool:
    return bool(await _cache().has(KEY))


async def payload() -> dict[str, Any]:
    info = await _cache().get(KEY)
    return cast("dict[str, Any]", info) if isinstance(info, dict) else {}


class PreventRequestsDuringMaintenance:
    """Middleware: return 503 (with Retry-After) while the app is in maintenance mode."""

    async def handle(self, request: Any, call_next: Any) -> Any:
        if not await is_down():
            return await call_next(request)
        from arvel.http.response import Response

        info = await payload()
        return Response(
            {"message": info.get("message", "Down for maintenance.")},
            status=503,
            headers={"Retry-After": str(info.get("retry", 60))},
        )
