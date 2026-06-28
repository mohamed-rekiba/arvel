"""Views (doc 09) — the Inertia adapter: JSON for X-Inertia requests, page object. Test-first."""

from __future__ import annotations

from typing import Any

import msgspec

from arvel.http.request import current_request
from arvel.views.inertia import inertia, inertia_page


class FakeRequest:
    def __init__(self, *, is_inertia: bool = False, path: str = "/dashboard") -> None:
        self._is_inertia = is_inertia
        self._path = path

    def path(self) -> str:
        return self._path

    def header(self, name: str, default: Any = None) -> Any:
        if name.lower() == "x-inertia" and self._is_inertia:
            return "true"
        return default


def test_inertia_page_shape() -> None:
    page = inertia_page("Dashboard", {"user": "ada"}, FakeRequest(path="/d"))
    assert page["component"] == "Dashboard"
    assert page["props"] == {"user": "ada"}
    assert page["url"] == "/d"
    assert "version" in page  # asset version for cache-busting


async def test_inertia_returns_json_for_xinertia_request() -> None:
    token = current_request.set(FakeRequest(is_inertia=True, path="/d"))  # type: ignore[arg-type]
    try:
        response = await inertia("Dashboard", {"count": 1})
        assert response.headers["X-Inertia"] == "true"
        assert response.headers["Vary"] == "X-Inertia"
        body = msgspec.json.decode(response.content)
        assert body["component"] == "Dashboard"
        assert body["props"] == {"count": 1}
        assert body["url"] == "/d"
    finally:
        current_request.reset(token)
