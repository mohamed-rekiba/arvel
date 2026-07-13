"""Router.public() serves a directory as the app's public web root.
spa_fallback=True (default) falls back unmatched paths to index.html (SPA); False 404s instead."""

from __future__ import annotations

from pathlib import Path

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


def _build_public_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "favicon.ico").write_text("ico")
    (tmp_path / "assets" / "app.abc123.js").write_text("console.log(1)")
    return tmp_path


async def api_ping(request: object) -> dict[str, bool]:
    return {"ok": True}


def test_root_serves_index_html(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"
        assert resp.headers["cache-control"] == "no-cache"


def test_unmatched_deep_path_falls_back_to_index_html(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/products/some-slug")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"


def test_real_asset_served_with_immutable_cache(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/assets/app.abc123.js")
        assert resp.is_success
        assert resp.text == "console.log(1)"
        assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_root_level_static_file_served_with_no_cache(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"
        assert resp.headers["cache-control"] == "no-cache"


def test_specific_route_wins_over_public_even_when_registered_first(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path)  # registered BEFORE the API route — is_fallback ordering must still win
    r.get("/api/ping", api_ping)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/api/ping")
        assert resp.json() == {"ok": True}


def test_path_traversal_cannot_escape_the_public_directory(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("do not serve me")
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/../secret.txt")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"  # fell back to the shell, not the escape


# --- spa_fallback=False: static files only, no SPA shell ---


def test_no_fallback_serves_real_files(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path, spa_fallback=False)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"


def test_no_fallback_404s_on_unmatched_path(tmp_path: Path) -> None:
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path, spa_fallback=False)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/products/some-slug")
        assert resp.status_code == 404


def test_no_fallback_does_not_claim_root(tmp_path: Path) -> None:
    """public(spa_fallback=False) must not register a competing root route."""
    _build_public_dir(tmp_path)
    r = Router()
    r.public(tmp_path, spa_fallback=False)
    r.get("/", api_ping, name="home")
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/")
        assert resp.json() == {"ok": True}


def test_missing_index_html_is_a_clear_error_not_a_bare_crash(tmp_path: Path) -> None:
    """Missing index.html should give a diagnosable message, not a raw FileNotFoundError-as-500."""
    r = Router()
    r.public(tmp_path)  # empty dir — no index.html at all
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/anything")
        assert resp.status_code == 500
        assert "index.html" in resp.text


def test_nested_asset_is_immutable_too(tmp_path: Path) -> None:
    """Bundlers nest under the assets dir (assets/chunks/...); depth must not lose the cache."""
    _build_public_dir(tmp_path)
    nested = tmp_path / "assets" / "chunks"
    nested.mkdir()
    (nested / "app.def456.js").write_text("//chunk")
    r = Router()
    r.public(tmp_path)
    kernel = HttpKernel()
    r.apply_to(kernel)
    with TestClient(app=kernel.build()) as client:
        resp = client.get("/assets/chunks/app.def456.js")
        assert resp.is_success
        assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
