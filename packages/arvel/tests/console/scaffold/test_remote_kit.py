"""``remote_kit`` — resolve, download, verify, cache, and extract the kit.

All HTTP is served by an in-process ``httpx.MockTransport``; no real network.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx2 as httpx
import pytest
from arvel.console._scaffold import remote_kit
from arvel.console._scaffold.kits import KitDownloadError

if TYPE_CHECKING:
    from collections.abc import Callable

_API = "https://api.github.com/repos/mohamed-rekiba/arvel/releases"
_DL = "https://github.com/mohamed-rekiba/arvel/releases/download"


def _tarball(version: str) -> bytes:
    """A git-archive-shaped tarball: one top dir holding the kit tree."""
    prefix = f"arvel-ecommerce-kit-{version}"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, body in (
            ("pyproject.toml", b'[project]\nname = "arvel-ecommerce-kit"\nversion = "1.0.0"\n'),
            ("backend/app.py", b"print('hi')\n"),
        ):
            data = body
            info = tarfile.TarInfo(f"{prefix}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _releases(*tags: str) -> list[dict[str, object]]:
    return [{"tag_name": tag, "assets": []} for tag in tags]


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
    calls: list[str],
) -> httpx.MockTransport:
    def _wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return handler(request)

    return httpx.MockTransport(_wrapped)


@pytest.fixture(autouse=True)
def isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("ARVEL_ECOMMERCE_KIT_VERSION", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def _client(handler: Callable[[httpx.Request], httpx.Response], calls: list[str]) -> httpx.Client:
    return httpx.Client(transport=_transport(handler, calls), follow_redirects=True)


def test_fetch_latest_downloads_and_extracts() -> None:
    version = "1.2.0"
    tar = _tarball(version)
    digest = hashlib.sha256(tar).hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(_API):
            return httpx.Response(200, json=_releases("arvel-ecommerce-kit-v1.2.0"))
        if url.endswith(".tar.gz.sha256"):
            return httpx.Response(200, text=f"{digest}  arvel-ecommerce-kit-{version}.tar.gz\n")
        if url.endswith(".tar.gz"):
            return httpx.Response(200, content=tar)
        return httpx.Response(404)

    with _client(handler, calls) as client:
        root = remote_kit.fetch_ecommerce_kit(client=client)

    assert (root / "pyproject.toml").read_text(encoding="utf-8").startswith("[project]")
    assert (root / "backend" / "app.py").is_file()


def test_picks_highest_version() -> None:
    chosen = "1.10.0"
    tar = _tarball(chosen)
    digest = hashlib.sha256(tar).hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(_API):
            return httpx.Response(
                200,
                json=_releases(
                    "arvel-ecommerce-kit-v1.2.0",
                    "arvel-ecommerce-kit-v1.10.0",
                    "arvel-ecommerce-kit-v1.9.0",
                    "arvel-v9.9.9",  # different component — ignored
                ),
            )
        if url.endswith(".tar.gz.sha256"):
            return httpx.Response(200, text=f"{digest}  x\n")
        if url.endswith(".tar.gz"):
            return httpx.Response(200, content=tar)
        return httpx.Response(404)

    with _client(handler, calls) as client:
        remote_kit.fetch_ecommerce_kit(client=client)

    assert any(f"{_DL}/arvel-ecommerce-kit-v{chosen}/" in url for url in calls)


def test_pinned_version_skips_api(monkeypatch: pytest.MonkeyPatch) -> None:
    version = "1.0.0"
    monkeypatch.setenv("ARVEL_ECOMMERCE_KIT_VERSION", version)
    tar = _tarball(version)
    digest = hashlib.sha256(tar).hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".tar.gz.sha256"):
            return httpx.Response(200, text=f"{digest}  x\n")
        if url.endswith(".tar.gz"):
            return httpx.Response(200, content=tar)
        return httpx.Response(404)

    with _client(handler, calls) as client:
        remote_kit.fetch_ecommerce_kit(client=client)

    assert not any(url.startswith(_API) for url in calls)


def test_cache_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    version = "2.0.0"
    monkeypatch.setenv("ARVEL_ECOMMERCE_KIT_VERSION", version)
    tar = _tarball(version)
    digest = hashlib.sha256(tar).hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".tar.gz.sha256"):
            return httpx.Response(200, text=f"{digest}  x\n")
        if url.endswith(".tar.gz"):
            return httpx.Response(200, content=tar)
        return httpx.Response(404)

    with _client(handler, calls) as client:
        remote_kit.fetch_ecommerce_kit(client=client)
        remote_kit.fetch_ecommerce_kit(client=client)

    assert sum(url.endswith(".tar.gz") for url in calls) == 1


def test_checksum_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARVEL_ECOMMERCE_KIT_VERSION", "1.0.0")
    tar = _tarball("1.0.0")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".tar.gz.sha256"):
            return httpx.Response(200, text="deadbeef  x\n")
        if url.endswith(".tar.gz"):
            return httpx.Response(200, content=tar)
        return httpx.Response(404)

    with (
        _client(handler, calls) as client,
        pytest.raises(KitDownloadError, match="checksum mismatch"),
    ):
        remote_kit.fetch_ecommerce_kit(client=client)


def test_no_release_found_raises() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_releases("arvel-v1.0.0"))

    with _client(handler, calls) as client, pytest.raises(KitDownloadError, match="no published"):
        remote_kit.fetch_ecommerce_kit(client=client)


def test_network_error_is_wrapped() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with _client(handler, calls) as client, pytest.raises(KitDownloadError, match="network"):
        remote_kit.fetch_ecommerce_kit(client=client)
