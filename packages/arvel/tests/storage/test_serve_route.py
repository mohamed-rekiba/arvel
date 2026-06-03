"""Framework-level local file serving (WI-arvel-001, PRD-001).

RTM — acceptance criterion → test:
  AC-1 public 200            -> test_serves_public_file
  AC-2 missing 404           -> test_missing_file_404
  AC-3 traversal 404         -> test_traversal_attempts_404
  AC-4 serve=false no route  -> test_serve_disabled_registers_no_route
  AC-5 absolute url no route -> test_absolute_url_registers_no_route
  AC-6 valid signed 200      -> test_valid_signed_url_served
  AC-7 tampered/expired 403  -> test_tampered_token_403 / test_expired_token_403
  AC-8 temp-url round trip   -> test_temporary_url_round_trips
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from arvel import Application


def _build_app(tmp_path: Path, env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Application:
    from arvel import Application
    from arvel.providers import HttpServiceProvider
    from arvel.providers.storage_provider import StorageServiceProvider
    from arvel.routing import Router

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    Router.reset_singleton()
    return (
        Application.configure(tmp_path)
        .with_environment("local")
        .with_providers([HttpServiceProvider, StorageServiceProvider])
        .create()
    )


def _client(app: Application) -> httpx.Client:
    fa = app.into_asgi()
    return cast("httpx.Client", TestClient(fa))


def _local_env(root: Path, *, url: str = "/storage", serve: str = "true") -> dict[str, str]:
    return {
        "STORAGE_DEFAULT": "local",
        "STORAGE_LOCAL_ROOT": str(root),
        "STORAGE_LOCAL_URL": url,
        "STORAGE_LOCAL_SERVE": serve,
    }


class TestLocalConfigServe:
    def test_serve_defaults_true(self) -> None:
        from arvel.config.storage_config import LocalConfig

        assert LocalConfig().serve is True


class TestServeRoute:
    def test_serves_public_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b.png").write_bytes(b"\x89PNG\r\n\x1a\nDATA")
        app = _build_app(tmp_path, _local_env(tmp_path), monkeypatch)
        with _client(app) as client:
            resp = client.get("/storage/a/b.png")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG\r\n\x1a\nDATA"
        assert resp.headers["content-type"].startswith("image/png")
        assert "cache-control" in resp.headers

    def test_missing_file_404(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        app = _build_app(tmp_path, _local_env(tmp_path), monkeypatch)
        with _client(app) as client:
            assert client.get("/storage/nope.png").status_code == 404

    def test_traversal_attempts_404(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = tmp_path.parent / "secret.txt"
        secret.write_text("top secret")
        app = _build_app(tmp_path, _local_env(tmp_path), monkeypatch)
        with _client(app) as client:
            for attempt in ("/storage/../secret.txt", "/storage/%2e%2e/secret.txt"):
                resp = client.get(attempt)
                assert resp.status_code == 404
                assert b"top secret" not in resp.content

    def test_serve_disabled_registers_no_route(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_app(tmp_path, _local_env(tmp_path, serve="false"), monkeypatch)
        from arvel.routing import Router

        paths = [spec.path for spec in Router.singleton().routes()]
        assert not any(p.startswith("/storage") for p in paths)

    def test_absolute_url_registers_no_route(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = _local_env(tmp_path, url="https://cdn.example.com/files")
        _build_app(tmp_path, env, monkeypatch)
        from arvel.routing import Router

        paths = [spec.path for spec in Router.singleton().routes()]
        assert not any("cdn.example.com" in p or p.startswith("/storage") for p in paths)


class TestSignedUrls:
    def _signed_params(self, app: Application, path: str, ttl: int) -> dict[str, str]:
        from arvel.storage import StorageManager

        manager = app.container.make(StorageManager)
        url = manager.disk("local").temporary_url(path, ttl)
        return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}

    def test_temporary_url_round_trips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "doc.txt").write_text("private")
        env = _local_env(tmp_path) | {"APP_KEY": "test-app-key-round-trip"}
        app = _build_app(tmp_path, env, monkeypatch)
        params = self._signed_params(app, "doc.txt", 300)
        with _client(app) as client:
            resp = client.get("/storage/doc.txt", params=params)
        assert resp.status_code == 200
        assert resp.content == b"private"

    def test_valid_signed_url_served(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "doc.txt").write_text("ok")
        env = _local_env(tmp_path) | {"APP_KEY": "k"}
        app = _build_app(tmp_path, env, monkeypatch)
        params = self._signed_params(app, "doc.txt", 300)
        with _client(app) as client:
            assert client.get("/storage/doc.txt", params=params).status_code == 200

    def test_tampered_token_403(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "doc.txt").write_text("ok")
        env = _local_env(tmp_path) | {"APP_KEY": "k"}
        app = _build_app(tmp_path, env, monkeypatch)
        params = self._signed_params(app, "doc.txt", 300)
        params["token"] = "tampered" + params["token"][8:]
        with _client(app) as client:
            assert client.get("/storage/doc.txt", params=params).status_code == 403

    def test_expired_token_403(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "doc.txt").write_text("ok")
        env = _local_env(tmp_path) | {"APP_KEY": "k"}
        app = _build_app(tmp_path, env, monkeypatch)
        params = self._signed_params(app, "doc.txt", 300)
        params["expires"] = str(int(time.time()) - 10)
        with _client(app) as client:
            assert client.get("/storage/doc.txt", params=params).status_code == 403
