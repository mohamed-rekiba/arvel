"""arvel.http.exceptions — content-negotiated rendering of arvel exceptions.

The kernel registers ``render_exception`` as a Litestar exception handler for
``ValidationException`` (and friends). Negotiation (doc 10 §error rendering / doc 04):
- **API / JSON / Inertia** (``Accept: application/json``, the default, or ``X-Inertia: true``)
  → a JSON body ``{message, errors}`` with the real status (422/403/404/…).
- **web** (``Accept: text/html``) → the errors are flashed to the session **error bag** and the
  client is **redirected back** (302) to the ``Referer`` (or ``/``) — Laravel's redirect-back.
Litestar is imported lazily here (serve path only).
Grounded in knowledge/port/10-validation.md + 04-http-kernel-middleware.md.
"""

from __future__ import annotations

from typing import Any, NoReturn, cast

_STATUS_MESSAGES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    419: "Page Expired",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Server Error",
    503: "Service Unavailable",
}


def _status_text(status: int) -> str:
    """The user-facing default text for ``status``, localized via ``trans("http.status.<code>")``.

    Falls back to the English ``_STATUS_MESSAGES`` entry (or ``"Server Error"`` for an unknown code)
    when no translation exists — so it never leaks a bare key and stays correct with no app booted.
    ``trans`` is imported lazily (keeps ``import arvel`` light; avoids an import cycle)."""
    default = _STATUS_MESSAGES.get(status, "Server Error")
    from arvel.localization import trans

    key = f"http.status.{status}"
    text = trans(key)
    return default if text == key else text


class HttpException(Exception):
    """An HTTP error carrying a status code (rendered by ``render_exception``). Raised by the
    ``abort()`` helper; the message, when given, overrides the default status text."""

    def __init__(self, status: int, message: str | None = None) -> None:
        self.status = status
        super().__init__(message or _status_text(status))


def abort(status: int, message: str | None = None) -> NoReturn:
    """Raise an HTTP error with ``status`` (and optional ``message``) — e.g. ``abort(404)`` or
    ``abort(403, "Nope")``. The exception handler renders it content-negotiated (spec 04).

    Typed ``NoReturn`` (it always raises), so type-checkers narrow values after an ``abort`` guard."""
    raise HttpException(status, message)


def _headers(request: Any) -> Any:
    headers = getattr(request, "headers", None)
    return headers if hasattr(headers, "get") else {}


def wants_json(accept: str | None) -> bool:
    """API-first: default to JSON; only render HTML when the client explicitly asks for it."""
    if not accept:
        return True
    accept = accept.lower()
    if "application/json" in accept:
        return True
    return "text/html" not in accept


def is_inertia(request: Any) -> bool:
    """An Inertia request (``X-Inertia: true``) takes the JSON 422 path, not the web redirect."""
    return str(_headers(request).get("x-inertia") or "").lower() == "true"


def render_exception(request: Any, exc: Any, *, debug: bool = False) -> Any:
    import litestar

    # arvel's HttpException carries `.status`; litestar's HTTPException carries `.status_code`.
    status = int(getattr(exc, "status", None) or getattr(exc, "status_code", None) or 500)
    errors = getattr(exc, "errors", None)
    if isinstance(exc, HttpException):
        message = str(exc)
    elif status >= 500:
        # never leak exception detail in production; it may carry sensitive internals.
        message = f"{type(exc).__name__}: {exc}" if debug else _status_text(status)
    else:
        detail = getattr(exc, "detail", None)
        message = str(detail) if detail else _status_text(status)
    headers = _headers(request)
    accept = headers.get("accept")

    if wants_json(accept) or is_inertia(request):
        body: dict[str, Any] = {"message": message}
        if errors is not None:
            body["errors"] = errors
        return litestar.Response(body, status_code=status, media_type="application/json")

    try:  # request.session is a property that raises without session middleware configured
        session: Any = getattr(request, "session", None)
    except Exception:
        session = None
    if isinstance(session, dict) and errors is not None:
        from arvel.http.flash import FlashBag

        FlashBag(cast("dict[str, Any]", session)).flash_errors(errors)
    referer = headers.get("referer") or headers.get("referrer") or "/"
    location = _same_origin_or_root(str(referer), str(headers.get("host") or ""))
    return litestar.Response(None, status_code=302, headers={"Location": location})


def _same_origin_or_root(target: str, host: str) -> str:
    """Return ``target`` only if it's safe to redirect to — a same-origin/relative URL — else ``/``.

    Prevents an open redirect: an attacker-controlled ``Referer`` (now reachable on every auth
    failure via the web-redirect path) must not bounce the browser to an external host.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(target)
    if not parts.scheme and not parts.netloc:
        return target or "/"
    if host and parts.netloc == host:
        return target
    return "/"
