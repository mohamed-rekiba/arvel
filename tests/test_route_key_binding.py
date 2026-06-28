"""C5 — custom route-key binding: {param} resolves a model by a non-PK column
(Laravel ``{post:slug}``), 404 on miss. Test-first."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


class _Query:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    async def first(self) -> Any:
        return _Article(self._row) if self._row is not None else None


class _Article:
    _rows = [{"slug": "hello-world", "title": "Hello World"}]

    def __init__(self, row: dict[str, Any]) -> None:
        self.title = row["title"]

    @classmethod
    def where(cls, column: str, _op: str, value: Any) -> _Query:
        match = next((r for r in cls._rows if r[column] == value), None)
        return _Query(match)


async def _show(request: Any, article: _Article) -> dict[str, Any]:
    return {"title": article.title}


def _client() -> TestClient[Any]:
    router = Router()
    router.get("/articles/{article}", _show)
    router.model("article", _Article, key="slug")  # bind by slug, not PK
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_custom_key_binding_resolves_by_column() -> None:
    with _client() as client:
        assert client.get("/articles/hello-world").json() == {"title": "Hello World"}


def test_custom_key_binding_404_on_miss() -> None:
    with _client() as client:
        assert client.get("/articles/nope").status_code == 404
