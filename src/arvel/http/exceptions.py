"""arvel.http.exceptions — content-negotiated rendering of arvel exceptions.

The kernel registers ``render_exception`` as a Litestar exception handler for
``ValidationException`` (and friends). Negotiation (doc 10 §error rendering / doc 04):
- **API / JSON / Inertia** (``Accept: application/json``, the default, or ``X-Inertia: true``)
  → a JSON body ``{message, errors}`` with the real status (422/403/404/…).
- **web** (``Accept: text/html``) → the errors are flashed to the session **error bag** and the
  client is **redirected back** (302) to the ``Referer`` (or ``/``) — the redirect-back.
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

    def __init__(
        self, status: int, message: str | None = None, *, headers: dict[str, str] | None = None
    ) -> None:
        self.status = status
        self.response_headers = headers or {}
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


def _report_server_error(exc: Any) -> None:
    """Route a 5xx through the app's ``ExceptionHandler.report()`` so it is logged — honoring the
    app's ``dont_report``/``level`` policy. ``report()`` is idempotent (it marks the exception), so
    this is safe even when ``_handle_uncaught`` already reported the same exception. Fully guarded:
    the error renderer must never itself raise. This is the seam that makes 5xx ``HttpException``s
    (which Litestar routes straight here, bypassing ``_handle_uncaught``) leave a server-side trace."""
    import contextlib

    with contextlib.suppress(Exception):
        from arvel.kernel import app, has_application

        if has_application() and app().bound("exceptions"):
            app().make("exceptions").report(exc)


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
    if status >= 500:
        _report_server_error(exc)  # 5xx must leave a server-side trace (idempotent via report())
    headers = _headers(request)
    accept = headers.get("accept")

    extra_headers: dict[str, str] = getattr(exc, "response_headers", None) or {}
    if accept and "application/vnd.api+json" in accept:
        # a JSON:API client gets that spec's error shape; validation errors point at the
        # offending attribute so client tooling can map them back to fields
        error_objects: list[dict[str, Any]] = []
        if isinstance(errors, dict):
            for field, messages in cast("dict[str, Any]", errors).items():
                details: list[Any] = (
                    list(cast("list[Any]", messages)) if isinstance(messages, list) else [messages]
                )
                error_objects.extend(
                    {
                        "status": str(status),
                        "detail": str(detail),
                        "source": {"pointer": f"/data/attributes/{field}"},
                    }
                    for detail in details
                )
        elif isinstance(errors, list):
            # a plain list of messages has no field to point at, but the details survive
            error_objects = [
                {"status": str(status), "detail": str(detail)}
                for detail in cast("list[Any]", errors)
            ]
        elif errors is not None:
            error_objects = [{"status": str(status), "detail": str(errors)}]
        if not error_objects:
            error_objects = [{"status": str(status), "detail": message}]
        return litestar.Response(
            {"errors": error_objects},
            status_code=status,
            media_type="application/vnd.api+json",
            headers=extra_headers or None,
        )
    if wants_json(accept) or is_inertia(request):
        body: dict[str, Any] = {"message": message}
        if errors is not None:
            body["errors"] = errors
        return litestar.Response(
            body,
            status_code=status,
            media_type="application/json",
            headers=extra_headers or None,
        )

    if status in (419, 422):
        # "return to the form" semantics: flash the errors and bounce back — only for
        # validation/CSRF failures; a 404 or 5xx must render as its real status
        try:  # request.session is a property that raises without session middleware configured
            session: Any = getattr(request, "session", None)
        except Exception:
            session = None
        if isinstance(session, dict) and errors is not None:
            from arvel.http.flash import FlashBag

            FlashBag(cast("dict[str, Any]", session)).flash_errors(errors)
        referer = headers.get("referer") or headers.get("referrer") or "/"
        location = same_origin_or_root(str(referer), str(headers.get("host") or ""))
        return litestar.Response(
            None, status_code=302, headers={"Location": location, **extra_headers}
        )
    # HTML-accepting client, non-form failure. Prefer an app-provided error page
    # (resources/views/errors/<status>.html, then errors/generic.html); fall back to the built-in.
    custom = _render_error_view(status, message, debug, extra_headers)
    if custom is not None:
        return custom

    import html as _html

    detail = f"<p>{_html.escape(message)}</p>" if (debug or status < 500) else ""
    page = (
        f"<!doctype html><html><head><title>{status} — {_status_text(status)}</title></head>"
        f"<body><h1>{status} — {_status_text(status)}</h1>{detail}</body></html>"
    )
    return litestar.Response(
        page, status_code=status, media_type="text/html", headers=extra_headers or None
    )


def _render_error_view(
    status: int, message: str, debug: bool, extra_headers: dict[str, str]
) -> Any:
    """Render ``resources/views/errors/<status>.html`` (else ``errors/generic.html``) as the HTML
    error page, with ``status``/``message``/``debug`` in scope. Returns a ``litestar.Response`` or
    ``None`` to fall back to the built-in page. Fully guarded: no app, a missing template, or a
    render error all return ``None`` — the error renderer must never itself raise."""
    try:
        import contextlib
        from pathlib import Path

        import jinja2
        import litestar

        from arvel.kernel import app, has_application

        paths: Any = "resources/views"
        with contextlib.suppress(Exception):
            if has_application() and app().bound("config"):
                from arvel.kernel.config import config

                paths = config("view.paths", "resources/views") or "resources/views"
        roots = [str(paths)] if isinstance(paths, str) else [str(p) for p in paths]

        # withhold internal detail from a production 5xx, exactly as the built-in page does
        shown = message if (debug or status < 500) else _status_text(status)

        for name in (f"errors/{status}.html", "errors/generic.html"):
            if any((Path(root) / name).is_file() for root in roots):
                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(roots),
                    autoescape=jinja2.select_autoescape(default=True),
                )
                body = env.get_template(name).render(status=status, message=shown, debug=debug)
                return litestar.Response(
                    body,
                    status_code=status,
                    media_type="text/html",
                    headers=extra_headers or None,
                )
    except Exception:
        return None
    return None


def same_origin_or_root(target: str, host: str) -> str:
    """Return ``target`` only if it's safe to redirect to — a same-origin/relative URL — else ``/``.

    Prevents an open redirect: an attacker-controlled ``Referer`` (now reachable on every auth
    failure via the web-redirect path) must not bounce the browser to an external host.
    """
    from urllib.parse import urlsplit

    # browsers treat backslashes as forward slashes, so "/\evil.com" would redirect off-host;
    # normalize before deciding so a protocol-relative "//host" is recognized, not read as relative.
    candidate = target.replace("\\", "/")
    parts = urlsplit(candidate)
    if not parts.scheme and not parts.netloc:
        return candidate or "/"
    if host and parts.netloc == host:
        return candidate
    return "/"
