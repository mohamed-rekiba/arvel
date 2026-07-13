"""arvel.http.responder — the response-conversion funnel (H12 split from ``HttpKernel``).

Free functions, not a class: the funnel closes over nothing but its own arguments (no
``self.app``, no ``self.bindings``), so a stateful unit here would be ceremony (DR-0042). The one
conversion funnel for every value type a handler may return — extend here, don't add a second
path.

Grounded in knowledge/port/04-http-kernel-middleware.md (route-adaptation + pipeline).
"""

from __future__ import annotations

from typing import Any, cast

from arvel.http.response import Response


async def to_response(result: Any, request: Any | None = None) -> Any:
    """Normalize any handler return into a Litestar ``Response`` (doc 04 §response
    normalization + HTTP-PARITY §2), so middleware/terminate see a uniform response object.
    The one conversion funnel for every value type a handler may return — extend here, don't
    add a second path."""
    import litestar

    if isinstance(result, litestar.Response):
        return cast("Any", result)
    if isinstance(result, Response):
        return apply_cookies(
            request,
            litestar.Response(result.content, status_code=result.status, headers=result.headers),
            result,
        )
    from arvel.http.redirect import Redirect

    if isinstance(result, Redirect):
        return await redirect_response(result, request)
    from arvel.http.response import FileDownload, StreamValue

    if isinstance(result, FileDownload):
        import mimetypes

        from litestar.response import File

        # Litestar's `File`/`Stream` resolve content-type from the *route handler's* declared
        # return annotation, not their own constructor arg — and every arvel adapter is typed
        # `Any` (dynamic handler I/O), so that resolution always lands on the JSON default.
        # Forcing it into `headers` sidesteps that resolution entirely.
        guessed = mimetypes.guess_type(str(result.name or result.path))[0]
        headers = {"content-type": guessed or "application/octet-stream", **result.headers}
        return cast(
            "Any",
            File(
                path=result.path,
                filename=result.name,
                content_disposition_type="inline" if result.inline else "attachment",
                headers=headers,
            ),
        )
    if isinstance(result, StreamValue):
        from litestar.response import Stream

        headers = {"content-type": result.media_type, **result.headers}
        return cast("Any", Stream(result.content, headers=headers))
    from arvel.pagination import AbstractPaginator

    if isinstance(result, AbstractPaginator):
        return cast("Any", litestar.Response(result.to_dict()))
    # a route handler returning a JsonResource/ResourceCollection (DB-MODEL §4) "just works" —
    # database sits below http in the layered DAG, so this downward import is legal.
    from arvel.database.resources import (
        JsonApiCollection,
        JsonApiResource,
        JsonResource,
        ResourceCollection,
    )

    if isinstance(result, (JsonApiResource, JsonApiCollection)):
        # the JSON:API media type is part of that spec's conformance, not a plain json response
        return cast(
            "Any",
            litestar.Response(result.to_payload(request), media_type="application/vnd.api+json"),
        )
    if isinstance(result, (JsonResource, ResourceCollection)):
        return cast("Any", litestar.Response(result.to_payload(request)))
    # no explicit status_code, so the route's method-aware default still applies (e.g. POST -> 201)
    return cast("Any", litestar.Response(result))


def apply_cookies(request: Any, litestar_response: Any, response: Response) -> Any:
    """Apply a ``Response``'s queued cookies/expirations to the built Litestar response. A
    ``__Host-``-prefixed name gets ``path="/"``/no ``domain``/``secure=True`` forced — the full
    browser rule that prefix requires (``StartSession`` enforces the same for the session
    cookie). Without the forced ``Secure`` a ``__Host-`` cookie is silently rejected, so it
    overrides even an app whose ``session.secure`` is False; a non-prefixed cookie's unset
    ``secure`` defers to ``SessionSettings().secure``.

    Every cookie value is routed through :func:`~arvel.http.middleware.emit_cookie` (H7) so a
    queued cookie is encrypted exactly like the session/CSRF cookies are — one codec decision,
    not a second bespoke path here."""
    if not response.cookies and not response.forgotten_cookies:
        return litestar_response
    from arvel.http.middleware import SessionSettings, emit_cookie

    default_secure = SessionSettings().secure
    for cookie in response.cookies:
        host_prefixed = cookie.name.startswith("__Host-")
        emit_cookie(
            request,
            litestar_response,
            cookie.name,
            cookie.value,
            max_age=cookie.max_age,
            path="/" if host_prefixed else cookie.path,
            domain=None if host_prefixed else cookie.domain,
            secure=True
            if host_prefixed
            else (default_secure if cookie.secure is None else cookie.secure),
            httponly=cookie.http_only,
            samesite=cookie.same_site,
        )
    for name in response.forgotten_cookies:
        litestar_response.delete_cookie(name)
    return litestar_response


async def redirect_response(value: Any, request: Any) -> Any:
    """Convert a ``Redirect`` into a 302 (or its own ``status``), writing its flash/old-input/
    errors through the same session machinery ``ShareErrorsFromSession``/``render_exception``'s
    redirect-back path use — ``FlashBag`` and ``Request._flash_old_input`` — not a second
    implementation."""
    import litestar

    session = getattr(request, "session", None)
    if isinstance(session, dict):
        from arvel.http.flash import FlashBag

        bag = FlashBag(cast("dict[str, Any]", session))
        for key, flashed in value.flash_data.items():
            bag.flash(key, flashed)
        if value.errors is not None:
            bag.flash_errors(value.errors)
        if value.wants_input:
            content_type = request.header("content-type") or ""
            try:
                data = (
                    await request.form()
                    if ("form" in content_type or "urlencoded" in content_type)
                    else await request.json()
                )
            except Exception:  # unparseable/absent body → nothing to flash, not a 500
                data = {}
            request._flash_old_input(data, except_=value.input_except)
    headers = {"Location": value.location or "/", **value.headers}
    return litestar.Response(None, status_code=value.status, headers=headers)


def to_litestar_response(rendered: Any) -> Any:
    """An ``arvel.http.Response`` from a renderable becomes a litestar response; anything
    else (already a litestar Response, or a serializable body) passes through as-is."""
    from arvel.http.response import Response as ArvelResponse

    if isinstance(rendered, ArvelResponse):
        import litestar

        return litestar.Response(
            rendered.content, status_code=rendered.status, headers=rendered.headers
        )
    return rendered
