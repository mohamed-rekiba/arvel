"""arvel.http.maintenance — maintenance mode.

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

import hmac
from typing import Any, cast

#: Cache key holding the maintenance payload (absent ⇒ the app is up).
KEY = "arvel:maintenance"
#: The bypass cookie set on a request whose ``?secret=`` matched (so subsequent requests bypass
#: without repeating the query param — ``down --secret``).
SECRET_COOKIE = "arvel_maintenance_secret"  # noqa: S105 - a cookie name, not a credential


def _cache() -> Any:
    # falls back to a bare CacheManager so `arvel down`/`up` work from the CLI without a booted app
    from arvel.kernel import app, has_application

    if has_application() and app().bound("cache"):
        return app().make("cache").driver()
    from arvel.cache import CacheManager

    return CacheManager().driver()


async def down(
    message: str = "Down for maintenance.",
    retry: int = 60,
    secret: str | None = None,
    allow: list[str] | None = None,
    render: str | None = None,
) -> None:
    """Enter maintenance mode — store the flag (no TTL ⇒ until ``up``) with a Retry-After hint, plus
    an optional bypass ``secret``, IP ``allow``-list, and a pre-``render``-ed page."""
    info: dict[str, Any] = {"message": message, "retry": retry}
    if secret:
        info["secret"] = secret
    if allow:
        info["allow"] = list(allow)
    if render:
        info["render"] = _render_page(render)
    await _cache().put(KEY, info)


def _render_page(view_name: str) -> str:
    """Read ``resources/views/<view_name>.html`` verbatim, once, at ``down`` time (``--render``). A raw file read, not the Jinja view engine: maintenance mode must not depend on
    services that might themselves be why the app is down — and ``arvel.http`` stays below
    ``arvel.views`` in the module DAG (G1), so it can't import the view engine anyway."""
    from pathlib import Path

    path = Path("resources") / "views" / f"{view_name}.html"
    return path.read_text() if path.is_file() else f"<h1>{view_name}</h1>"


async def up() -> None:
    """Leave maintenance mode — drop the flag (no-op if already up)."""
    await _cache().forget(KEY)


async def is_down() -> bool:
    return bool(await _cache().has(KEY))


async def payload() -> dict[str, Any]:
    info = await _cache().get(KEY)
    return cast("dict[str, Any]", info) if isinstance(info, dict) else {}


def _client_ip(request: Any) -> str | None:
    """Best-effort, duck-typed client IP — ``request`` may be the real ``arvel.http.Request``
    (unwraps ``.raw.client.host``) or a bare test double (degrades to ``None``, never crashes)."""
    raw = getattr(request, "raw", request)
    client = getattr(raw, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return str(host) if host else None


def _duck_call(request: Any, method: str, *args: Any) -> Any:
    """Best-effort duck-typed call (``request.query(...)``/``request.cookie(...)``) — missing on a
    bare test double degrades to ``None`` rather than crashing the maintenance check."""
    fn = getattr(request, method, None)
    return fn(*args) if callable(fn) else None


class PreventRequestsDuringMaintenance:
    """Middleware: return 503 (with Retry-After) while the app is in maintenance mode.

    Paths in ``config('app.maintenance_except')`` (e.g. a health probe) stay reachable —
    the ``$except`` on the maintenance middleware. An IP in the ``down --allow`` list, or a
    request whose ``?secret=``/bypass cookie matches ``down --secret``, passes straight through
    (the first ``?secret=`` hit also sets the bypass cookie for later requests)."""

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.kernel import app, has_application

        excepted: list[str] = []
        if has_application():
            excepted = list(app().config("app.maintenance_except", []) or [])
        raw_path = getattr(request, "path", "")
        path = str(raw_path() if callable(raw_path) else raw_path or "")
        # exact-match only (no wildcards, unlike the $except globs) — list full paths
        if path in excepted:
            return await call_next(request)
        if not await is_down():
            return await call_next(request)

        info = await payload()
        allow = cast("list[str]", info.get("allow") or [])
        if allow and _client_ip(request) in allow:
            return await call_next(request)

        secret = info.get("secret")
        if secret:
            query_secret = _duck_call(request, "query", "secret")
            cookie_secret = _duck_call(request, "cookie", SECRET_COOKIE)
            # constant-time compare — the bypass secret is a credential; a plain == leaks it
            # byte-by-byte through response timing.
            query_ok = hmac.compare_digest(str(query_secret or ""), str(secret))
            cookie_ok = hmac.compare_digest(str(cookie_secret or ""), str(secret))
            if query_ok or cookie_ok:
                response = await call_next(request)
                if query_ok and hasattr(response, "with_cookie"):
                    response.with_cookie(SECRET_COOKIE, secret, minutes=60 * 24)
                return response

        from arvel.http.response import Response

        rendered = info.get("render")
        body = (
            rendered
            if rendered is not None
            else {"message": info.get("message", "Down for maintenance.")}
        )
        return Response(
            body,
            status=503,
            headers={"Retry-After": str(info.get("retry", 60))},
        )
