"""arvel.http.Response — a light, engine-agnostic response value.

Handlers may return a plain ``dict``/``list``/``str`` (Litestar serializes it), a
``JsonResource``/``ResourceCollection``, or one of the value objects here (an explicit
``Response``, a ``FileDownload``, a ``StreamValue``, or an ``http.redirect.Redirect``); the
one conversion funnel (``arvel.http.responder.to_response``) turns each into a
``litestar.Response`` in the serve path (Litestar imported there, not here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from os import PathLike


@dataclass
class QueuedCookie:
    """A cookie queued by :meth:`Response.with_cookie`, applied by the kernel on the way out.

    ``secure=None`` defers to ``SessionSettings().secure`` at apply time (the same default the
    session cookie itself uses) rather than baking a guess in here."""

    name: str
    value: str
    max_age: int | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool | None = None
    http_only: bool = True
    same_site: str = "lax"


@dataclass
class Response:
    content: Any = None
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict[str, str])
    cookies: list[QueuedCookie] = field(default_factory=list[QueuedCookie])
    forgotten_cookies: list[str] = field(default_factory=list[str])

    def with_cookie(
        self,
        name: str,
        value: str,
        *,
        minutes: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool | None = None,
        http_only: bool = True,
        same_site: str = "lax",
    ) -> Response:
        """Queue a cookie for the outgoing response.

        ``minutes`` is minutes-to-live (``None`` → a session cookie, no ``max-age``). A name
        starting with ``__Host-`` gets ``path="/"``/no ``domain`` forced by the kernel on apply
        (browsers reject the prefix otherwise), mirroring the session cookie's own rule."""
        max_age = minutes * 60 if minutes is not None else None
        self.cookies.append(
            QueuedCookie(name, value, max_age, path, domain, secure, http_only, same_site)
        )
        return self

    def without_cookie(self, name: str) -> Response:
        """Queue ``name`` for expiry."""
        self.forgotten_cookies.append(name)
        return self


@dataclass
class FileDownload:
    """A file response the kernel serves via Litestar's ``File`` response (streamed off disk,
    correct ``Content-Disposition``/``Content-Length``/etag). ``inline=True`` (``response().file``)
    renders in-browser; ``inline=False`` (``response().download``) forces a save-as download."""

    path: str | PathLike[str]
    name: str | None = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    inline: bool = False


@dataclass
class StreamValue:
    """A streamed response: ``content`` is
    an (async or sync) iterator of ``str``/``bytes`` chunks; the kernel wraps it in Litestar's
    ``Stream`` response."""

    content: Any
    media_type: str = "application/octet-stream"
    headers: dict[str, str] = field(default_factory=dict[str, str])


class _ResponseFactory:
    """The ``response()`` builder: callable for a plain body,
    plus ``.json``/``.no_content``/``.download``/``.file``/``.stream`` for the rest of the surface.
    A module-level singleton (``response = _ResponseFactory()``) so ``response(...)`` and
    ``response.json(...)`` both work off the one name."""

    def __call__(
        self, content: Any = None, status: int = 200, headers: Mapping[str, str] | None = None
    ) -> Response:
        return Response(content=content, status=status, headers=dict(headers or {}))

    def json(self, data: Any, status: int = 200) -> Response:
        return Response(content=data, status=status)

    def no_content(self) -> Response:
        return Response(content=None, status=204)

    def download(
        self,
        path: str | PathLike[str],
        name: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FileDownload:
        """Force a save-as download of ``path``, as ``name`` (defaults to the file's own name)."""
        return FileDownload(path=path, name=name, headers=dict(headers or {}), inline=False)

    def file(
        self, path: str | PathLike[str], headers: Mapping[str, str] | None = None
    ) -> FileDownload:
        """Render ``path`` in-browser (inline ``Content-Disposition``) — images/PDFs/etc."""
        return FileDownload(path=path, headers=dict(headers or {}), inline=True)

    def stream(
        self, content: Iterable[Any] | Any, media_type: str = "application/octet-stream"
    ) -> StreamValue:
        """Stream ``content`` (a sync/async iterator of chunks) as ``media_type``."""
        return StreamValue(content=content, media_type=media_type)


response = _ResponseFactory()


def json(content: Any, status: int = 200) -> Response:
    return Response(content=content, status=status)


async def prometheus_metrics(request: Any = None) -> Response:
    """Route handler for the Prometheus scrape endpoint: wraps telemetry's exposition payload in an
    http ``Response``. Lives here (http→telemetry is a legal downward edge) so telemetry need not
    import http; the routing provider registers it at ``/metrics`` when ``telemetry.prometheus`` is on
    (DR-0026)."""
    from arvel.telemetry import prometheus_payload

    content, content_type = prometheus_payload()
    return Response(content=content, headers={"content-type": content_type})
