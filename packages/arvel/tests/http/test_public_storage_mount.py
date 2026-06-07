"""Static serving for `storage:link` mounted under /storage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from arvel import Application


def _build_app(base: Path, monkeypatch: pytest.MonkeyPatch) -> Application:
    from arvel import Application
    from arvel.providers import HttpServiceProvider
    from arvel.routing import Router

    # Keep the static mount isolated from the serve=true route.
    monkeypatch.delenv("STORAGE_DEFAULT", raising=False)
    Router.reset_singleton()
    return (
        Application.configure(base)
        .with_environment("local")
        .with_providers([HttpServiceProvider])
        .create()
    )


def _client(app: Application) -> httpx.Client:
    return cast("httpx.Client", TestClient(app.into_asgi()))


def _make_public_storage(base: Path) -> Path:
    target = base / "public" / "storage"
    target.mkdir(parents=True)
    return target


class TestPublicStorageMount:
    def test_serves_file_under_public_storage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = _make_public_storage(tmp_path)
        (store / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nDATA")
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            resp = client.get("/storage/logo.png")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG\r\n\x1a\nDATA"
        assert resp.headers["content-type"].startswith("image/png")

    def test_serves_through_storage_link_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Mirror `storage:link`: public/storage -> storage/app/public.
        real = tmp_path / "storage" / "app" / "public"
        real.mkdir(parents=True)
        (real / "doc.txt").write_text("linked")
        (tmp_path / "public").mkdir()
        (tmp_path / "public" / "storage").symlink_to(real)
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            resp = client.get("/storage/doc.txt")
        assert resp.status_code == 200
        assert resp.content == b"linked"

    def test_missing_file_404(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_public_storage(tmp_path)
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            assert client.get("/storage/nope.png").status_code == 404

    def test_boots_without_link(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # public/ exists but the symlink doesn't yet: must boot, just 404.
        (tmp_path / "public").mkdir()
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            assert client.get("/storage/x.png").status_code == 404

    def test_no_public_dir_skips_mount(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No public/ at all (test/CLI context): app still assembles and serves.
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            assert client.get("/storage/x.png").status_code == 404

    def test_non_storage_path_uses_framework_404(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_public_storage(tmp_path)
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            resp = client.get("/definitely/not/storage")
        assert resp.status_code == 404
        # Framework JSON 404, not a bare static 404.
        assert resp.headers["content-type"].startswith("application/json")

    def test_traversal_blocked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("top secret")
        _make_public_storage(tmp_path)
        app = _build_app(tmp_path, monkeypatch)
        with _client(app) as client:
            for attempt in ("/storage/../secret.txt", "/storage/%2e%2e/secret.txt"):
                resp = client.get(attempt)
                assert resp.status_code == 404
                assert b"top secret" not in resp.content
