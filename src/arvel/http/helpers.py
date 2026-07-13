"""http helper shorthands — the global helpers that read the current request or raise an HTTP
status. They live here (not in ``arvel.support``, which is a leaf that must not import ``arvel.http``)
and are re-exported on the top-level ``arvel`` surface. Grounded in knowledge/port/06-facades.md
§helpers."""

from __future__ import annotations

from typing import Any


# --- conditional abort -------------------------------------------------------
def abort_if(condition: Any, status: int, message: str | None = None) -> None:
    """Raise an HTTP ``status`` (via :func:`arvel.http.abort`) when ``condition`` is truthy."""
    if condition:
        from arvel.http.exceptions import abort

        abort(status, message)


def abort_unless(condition: Any, status: int, message: str | None = None) -> None:
    """Raise an HTTP ``status`` (via :func:`arvel.http.abort`) when ``condition`` is falsy."""
    if not condition:
        from arvel.http.exceptions import abort

        abort(status, message)


# --- per-request accessors (read the request contextvar) ---------------------
def request() -> Any:
    """The in-flight request, or ``None`` outside a request cycle."""
    from arvel.http.request import current_request

    return current_request.get(None)


def session() -> dict[str, Any] | None:
    """The current request's session dict, or ``None`` off the web group / outside a request."""
    req = request()
    return getattr(req, "session", None) if req is not None else None


def cookie(name: str, default: str | None = None) -> str | None:
    """A cookie off the current request, or ``default`` when absent / outside a request."""
    req = request()
    return req.cookie(name, default) if req is not None else default


def old(key: str | None = None, default: Any = None) -> Any:
    """Flashed old-input off the current request's session — ``old()`` for all, ``old("field")``
    for one. Empty (or ``default``) when there's no session / nothing flashed."""
    sess = session()
    if sess is None:
        return {} if key is None else default
    from arvel.http.flash import FlashBag

    return FlashBag(sess).old(key, default)
