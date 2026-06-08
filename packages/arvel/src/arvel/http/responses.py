"""Response and redirect helpers — Laravel's `response()` / `redirect()` for Arvel.

Handlers can already return Starlette responses directly; these add the discoverable
builders Laravel devs reach for, plus redirect-with-session-flash, which needs to
touch ``request.state.session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

if TYPE_CHECKING:
    from starlette.requests import Request


def _headers(headers: Mapping[str, str] | None) -> dict[str, str] | None:
    return dict(headers) if headers else None


class ResponseFactory:
    """Mirrors Laravel's `response()` — builders for the common response shapes."""

    @staticmethod
    def json(
        data: Any,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> JSONResponse:
        return JSONResponse(data, status_code=status, headers=_headers(headers))

    @staticmethod
    def make(
        content: str | bytes = b"",
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        return Response(content, status_code=status, headers=_headers(headers))

    @staticmethod
    def text(
        content: str,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> PlainTextResponse:
        return PlainTextResponse(content, status_code=status, headers=_headers(headers))

    @staticmethod
    def no_content(*, headers: Mapping[str, str] | None = None) -> Response:
        return Response(status_code=204, headers=_headers(headers))


_RESPONSE_FACTORY = ResponseFactory()


def response() -> ResponseFactory:
    """Return the response builder, e.g. ``response().json({...}, status=201)``."""
    return _RESPONSE_FACTORY


class Redirect(RedirectResponse):
    """A redirect that can flash values into the session before sending."""

    def with_(self, request: Request, **values: object) -> Redirect:
        """Flash key/values so they're readable on the next request. Chainable.

        No-op when the session middleware isn't active for the route.
        """
        session = getattr(request.state, "session", None)
        if session is not None:
            for key, value in values.items():
                session.flash(key, value)
        return self


def redirect(
    to: str,
    *,
    status: int = 302,
    headers: Mapping[str, str] | None = None,
) -> Redirect:
    """Redirect to a URL/path. Chain `.with_(request, key=value)` to flash."""
    return Redirect(url=to, status_code=status, headers=_headers(headers))


def to_route(
    name: str,
    *,
    status: int = 302,
    headers: Mapping[str, str] | None = None,
    **params: Any,
) -> Redirect:
    """Redirect to a named route, substituting *params* into its placeholders."""
    from arvel import routing

    return redirect(routing.route(name, **params), status=status, headers=headers)


def back(
    request: Request,
    *,
    fallback: str = "/",
    status: int = 302,
    headers: Mapping[str, str] | None = None,
) -> Redirect:
    """Redirect to the Referer, falling back to *fallback* when it's absent."""
    target = request.headers.get("referer") or fallback
    return redirect(target, status=status, headers=headers)


__all__ = [
    "Redirect",
    "ResponseFactory",
    "back",
    "redirect",
    "response",
    "to_route",
]
