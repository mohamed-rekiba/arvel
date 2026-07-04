"""HTTP (doc 04/13) — maintenance mode stores its flag in the default cache + a 503 guard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.http import maintenance as m
from arvel.http.maintenance import PreventRequestsDuringMaintenance
from arvel.http.response import Response
from arvel.kernel import Application, set_application


class _FakeRequest:
    """A duck-typed request double exposing just what the middleware touches."""

    def __init__(
        self,
        path: str = "/",
        query: dict[str, str] | None = None,
        cookie: str | None = None,
        client_ip: str | None = None,
    ) -> None:
        self._path = path
        self._query = query or {}
        self._cookie = cookie
        if client_ip is not None:
            self.raw = SimpleNamespace(client=SimpleNamespace(host=client_ip))

    def path(self) -> str:
        return self._path

    def query(self, key: str, default: str | None = None) -> str | None:
        return self._query.get(key, default)

    def cookie(self, name: str, default: str | None = None) -> str | None:
        return self._cookie if name == m.SECRET_COOKIE else default


def _app_with_cache() -> Application:
    app = Application()
    app.instance("cache", CacheManager())  # default 'array' driver, isolated per test
    set_application(app)
    return app


async def test_down_up_via_default_cache() -> None:
    _app_with_cache()
    try:
        assert await m.is_down() is False
        await m.down("Back at 5", retry=90)
        assert await m.is_down() is True
        assert await m.payload() == {"message": "Back at 5", "retry": 90}
        await m.up()
        assert await m.is_down() is False
        await m.up()  # idempotent
    finally:
        set_application(None)


async def test_middleware_passes_through_when_up() -> None:
    _app_with_cache()
    try:
        await m.up()

        async def _next(req: Any) -> str:
            return "ok"

        assert await PreventRequestsDuringMaintenance().handle(object(), _next) == "ok"
    finally:
        set_application(None)


async def test_middleware_returns_503_when_down() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", retry=30)

        async def _next(req: Any) -> str:  # must NOT run during maintenance
            raise AssertionError("handler ran during maintenance")

        resp = await PreventRequestsDuringMaintenance().handle(object(), _next)
        assert resp.status == 503
        assert resp.headers["Retry-After"] == "30"
        assert resp.content == {"message": "Soon"}
    finally:
        set_application(None)


def test_down_up_cli_uses_the_app_bound_cache() -> None:
    """`arvel down` must flag the APP's cache driver (redis in prod → every server process sees
    it). Without booting the app, the flag lands in a CLI-process-local array cache and dies with
    the process — maintenance mode that never reaches the server."""
    from typer.testing import CliRunner

    from arvel.console import build_cli
    from arvel.kernel import Application, set_application

    class SpyCache:
        def __init__(self) -> None:
            self.store: dict[str, object] = {}

        async def put(self, key: str, value: object, ttl: object = None) -> bool:
            self.store[key] = value
            return True

        async def forget(self, key: str) -> bool:
            self.store.pop(key, None)
            return True

        async def has(self, key: str) -> bool:
            return key in self.store

        async def get(self, key: str, default: object = None) -> object:
            return self.store.get(key, default)

    class SpyManager:
        def __init__(self) -> None:
            self.repo = SpyCache()

        def driver(self, name: object = None) -> SpyCache:
            return self.repo

    spy = SpyManager()
    app = Application()
    app.instance("cache", spy)
    set_application(app)
    runner = CliRunner()
    try:
        assert runner.invoke(build_cli(), ["down"]).exit_code == 0
        assert "arvel:maintenance" in spy.repo.store  # flagged in the APP cache, not a local one
        assert runner.invoke(build_cli(), ["up"]).exit_code == 0
        assert "arvel:maintenance" not in spy.repo.store
    finally:
        set_application(None)


# -- --secret / --allow / --render (CLI-6/CLI-7) -------------------------------------------------


async def _ok(_req: Any) -> Response:
    return Response({"ok": True}, status=200)


async def test_secret_query_param_bypasses_and_sets_the_cookie() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", secret="s3cr3t")
        request = _FakeRequest(query={"secret": "s3cr3t"})
        response = await PreventRequestsDuringMaintenance().handle(request, _ok)
        assert response.status == 200
        assert any(c.name == m.SECRET_COOKIE and c.value == "s3cr3t" for c in response.cookies)
    finally:
        set_application(None)


async def test_secret_cookie_bypasses_without_the_query_param() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", secret="s3cr3t")
        request = _FakeRequest(cookie="s3cr3t")
        response = await PreventRequestsDuringMaintenance().handle(request, _ok)
        assert response.status == 200
    finally:
        set_application(None)


async def test_wrong_secret_still_gets_503() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", secret="s3cr3t")
        request = _FakeRequest(query={"secret": "nope"})
        response = await PreventRequestsDuringMaintenance().handle(request, _ok)
        assert response.status == 503
    finally:
        set_application(None)


async def test_allowed_ip_bypasses() -> None:
    _app_with_cache()
    try:
        await m.down("Soon", allow=["10.0.0.1"])
        allowed = await PreventRequestsDuringMaintenance().handle(
            _FakeRequest(client_ip="10.0.0.1"), _ok
        )
        blocked = await PreventRequestsDuringMaintenance().handle(
            _FakeRequest(client_ip="10.0.0.2"), _ok
        )
        assert allowed.status == 200
        assert blocked.status == 503
    finally:
        set_application(None)


async def test_render_serves_the_prerendered_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    views = tmp_path / "resources" / "views"
    views.mkdir(parents=True)
    (views / "maintenance.html").write_text("<h1>brb</h1>")
    _app_with_cache()
    try:
        await m.down("Soon", render="maintenance")
        response = await PreventRequestsDuringMaintenance().handle(_FakeRequest(), _ok)
        assert response.status == 503
        assert response.content == "<h1>brb</h1>"
    finally:
        set_application(None)


async def test_render_missing_view_falls_back_to_a_plain_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no resources/views/maintenance.html here
    _app_with_cache()
    try:
        await m.down("Soon", render="maintenance")
        response = await PreventRequestsDuringMaintenance().handle(_FakeRequest(), _ok)
        assert response.content == "<h1>maintenance</h1>"
    finally:
        set_application(None)


def test_down_cli_passes_through_secret_allow_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from typer.testing import CliRunner

    from arvel.console import build_cli

    monkeypatch.chdir(tmp_path)
    app = Application()
    app.instance("cache", CacheManager())
    set_application(app)
    try:
        result = CliRunner().invoke(
            build_cli(),
            ["down", "--secret", "s3cr3t", "--allow", "1.1.1.1", "--allow", "2.2.2.2"],
        )
        assert result.exit_code == 0, result.output
        payload = asyncio.run(m.payload())
        assert payload["secret"] == "s3cr3t"
        assert payload["allow"] == ["1.1.1.1", "2.2.2.2"]
    finally:
        set_application(None)
