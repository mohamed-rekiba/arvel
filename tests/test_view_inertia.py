"""Views (doc 09) — the Inertia adapter: JSON for X-Inertia requests, page object. Test-first."""

from __future__ import annotations

from typing import Any

import msgspec

from arvel.http.request import current_request
from arvel.views.inertia import inertia, inertia_page


class FakeRequest:
    def __init__(
        self,
        *,
        is_inertia: bool = False,
        path: str = "/dashboard",
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._is_inertia = is_inertia
        self._path = path
        self._method = method
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def path(self) -> str:
        return self._path

    def method(self) -> str:
        return self._method

    def header(self, name: str, default: Any = None) -> Any:
        key = name.lower()
        if key == "x-inertia" and self._is_inertia:
            return "true"
        return self._headers.get(key, default)


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


async def test_partial_reload_returns_only_requested_props() -> None:
    req = FakeRequest(
        is_inertia=True,
        path="/d",
        headers={"x-inertia-partial-data": "count", "x-inertia-partial-component": "Dashboard"},
    )
    token = current_request.set(req)  # type: ignore[arg-type]
    try:
        response = await inertia("Dashboard", {"count": 1, "extra": "big"})
        assert msgspec.json.decode(response.content)["props"] == {"count": 1}  # "extra" trimmed
    finally:
        current_request.reset(token)


async def test_partial_for_a_different_component_returns_all_props() -> None:
    req = FakeRequest(
        is_inertia=True,
        path="/d",
        headers={"x-inertia-partial-data": "count", "x-inertia-partial-component": "OtherPage"},
    )
    token = current_request.set(req)  # type: ignore[arg-type]
    try:
        response = await inertia("Dashboard", {"count": 1, "extra": "big"})
        assert msgspec.json.decode(response.content)["props"] == {"count": 1, "extra": "big"}
    finally:
        current_request.reset(token)


async def test_stale_asset_version_on_get_forces_a_full_reload() -> None:
    req = FakeRequest(is_inertia=True, path="/d", headers={"x-inertia-version": "stale"})
    token = current_request.set(req)  # type: ignore[arg-type]
    try:
        response = await inertia("Dashboard", {"count": 1})
        assert response.status == 409
        assert response.headers["X-Inertia-Location"] == "/d"
    finally:
        current_request.reset(token)


async def test_asset_version_changes_with_manifest_content(tmp_path: object) -> None:
    from arvel.views.inertia import _asset_version

    m1, m2 = f"{tmp_path}/m1.json", f"{tmp_path}/m2.json"
    from pathlib import Path

    Path(m1).write_text('{"a": 1}')
    Path(m2).write_text('{"a": 2}')
    v1, v2 = await _asset_version(m1), await _asset_version(m2)
    assert v1 != "dev" and len(v1) == 12  # wired to the manifest hash, not a constant
    assert v1 != v2  # a new build (different manifest) busts the version
