"""Item 3c — inline {param:field} route-key binding: `/posts/{post:slug}` implicitly binds a
Post by its slug column, while Litestar's typed converters ({x:path}/{x:int}) still work."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


class _Post:
    _rows = {"hello-world": "Hello World", "second": "Second Post"}

    def __init__(self, title: str) -> None:
        self.title = title

    @classmethod
    async def resolve_route_binding(cls, value: Any, field: str | None = None) -> _Post | None:
        # field is the inline route-key ("slug"); default route key would be the PK.
        assert field == "slug"
        title = cls._rows.get(str(value))
        return cls(title) if title is not None else None


async def _show(request: Any, post: _Post) -> dict[str, str]:
    return {"title": post.title}


def _client(router: Router) -> TestClient[Any]:
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_inline_field_binds_by_that_column() -> None:
    router = Router()
    router.get("/posts/{post:slug}", _show)
    with _client(router) as client:
        assert client.get("/posts/hello-world").json() == {"title": "Hello World"}


def test_inline_field_404_on_miss() -> None:
    router = Router()
    router.get("/posts/{post:slug}", _show)
    with _client(router) as client:
        assert client.get("/posts/nope").status_code == 404


def test_litestar_path_converter_still_works() -> None:
    """A Litestar typed converter ({filepath:path}) is left untouched and captures the rest."""

    async def _files(request: Any, filepath: str) -> dict[str, str]:
        return {"filepath": filepath}

    router = Router()
    router.get("/files/{filepath:path}", _files)
    with _client(router) as client:
        # Litestar's `path` converter captures the multi-segment remainder.
        assert client.get("/files/a/b/c.txt").json() == {"filepath": "/a/b/c.txt"}


def test_compile_path_classifies_suffixes() -> None:
    # `_compile_path` returns a LIST of Litestar paths (>1 only for trailing `{x?}` params).
    assert HttpKernel._compile_path("/u/{id}") == (["/u/{id:str}"], {})
    assert HttpKernel._compile_path("/p/{post:slug}") == (["/p/{post:str}"], {"post": "slug"})
    assert HttpKernel._compile_path("/f/{x:path}") == (["/f/{x:path}"], {})
    assert HttpKernel._compile_path("/n/{n:int}") == (["/n/{n:int}"], {})
