"""Fetch, verify, cache, and extract the e-commerce kit from its GitHub Release.

The kit ships as a release tarball (``arvel-ecommerce-kit-<ver>.tar.gz``) — not
on PyPI, not bundled in the wheel. ``arvel new --kit ecommerce`` resolves the
newest ``arvel-ecommerce-kit-v*`` release, streams the tarball with a progress
bar, verifies it against the release's ``.sha256`` sidecar, extracts it into a
per-version cache, and hands the tree to the scaffolder.

Set ``ARVEL_ECOMMERCE_KIT_VERSION`` to pin an exact version and skip the
release lookup — reproducible builds, or when you already know the version.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import typer
from pydantic import BaseModel, ConfigDict, TypeAdapter

from arvel.console._scaffold.kits import KitDownloadError

__all__ = ["fetch_ecommerce_kit"]

_REPO = "mohamed-rekiba/arvel"
_TAG_PREFIX = "arvel-ecommerce-kit-v"
_RELEASES_URL = f"https://api.github.com/repos/{_REPO}/releases?per_page=100"
_RELEASE_DOWNLOAD = f"https://github.com/{_REPO}/releases/download"
_USER_AGENT = "arvel-cli"
_TAG_RE = re.compile(r"^arvel-ecommerce-kit-v(\d+)\.(\d+)\.(\d+)$")
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_CHUNK = 65536
_MIB = 1024 * 1024
_BAR_WIDTH = 24

_NETWORK_HINT = (
    "couldn't fetch the e-commerce kit release. Check your network, then retry "
    "— or browse it at "
    "https://github.com/mohamed-rekiba/arvel/tree/main/kits/arvel-ecommerce-kit."
)


class _Asset(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    browser_download_url: str


class _Release(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag_name: str
    assets: list[_Asset]


_RELEASES = TypeAdapter(list[_Release])


@dataclass(frozen=True)
class _KitRelease:
    version: str
    tarball_url: str
    sha256_url: str


def fetch_ecommerce_kit(*, client: httpx.Client | None = None) -> Path:
    """Return a local path to the e-commerce kit tree, downloading if needed."""
    owned = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=_TIMEOUT)
    try:
        release = _resolve_release(http)
        cached = _cache_dir(release.version)
        if _is_complete(release.version):
            return cached
        return _download_and_extract(http, release)
    except httpx.HTTPError as exc:
        raise KitDownloadError(name="ecommerce", hint=_NETWORK_HINT, original=exc) from exc
    finally:
        if owned:
            http.close()


def _resolve_release(client: httpx.Client) -> _KitRelease:
    pinned = os.environ.get("ARVEL_ECOMMERCE_KIT_VERSION")
    if pinned:
        return _release_for_version(pinned)
    response = client.get(_RELEASES_URL, headers=_api_headers())
    response.raise_for_status()
    best: tuple[tuple[int, int, int], str] | None = None
    for release in _RELEASES.validate_python(response.json()):
        key = _version_key(release.tag_name)
        if key is not None and (best is None or key > best[0]):
            best = (key, ".".join(str(part) for part in key))
    if best is None:
        raise KitDownloadError(
            name="ecommerce",
            hint="no published arvel-ecommerce-kit release found yet.",
        )
    return _release_for_version(best[1])


def _release_for_version(version: str) -> _KitRelease:
    base = f"{_RELEASE_DOWNLOAD}/{_TAG_PREFIX}{version}"
    tarball = f"arvel-ecommerce-kit-{version}.tar.gz"
    return _KitRelease(
        version=version,
        tarball_url=f"{base}/{tarball}",
        sha256_url=f"{base}/{tarball}.sha256",
    )


def _download_and_extract(client: httpx.Client, release: _KitRelease) -> Path:
    dest = _cache_dir(release.version)
    cache_root = dest.parent
    cache_root.mkdir(parents=True, exist_ok=True)
    label = f"arvel-ecommerce-kit {release.version}"
    typer.echo(f"Fetching {label} …", err=True)
    with tempfile.TemporaryDirectory(prefix=".arvel-kit-", dir=cache_root) as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "kit.tar.gz"
        _stream_download(client, release.tarball_url, archive, label=label)
        expected = _fetch_sha256(client, release.sha256_url)
        actual = _sha256(archive)
        if actual != expected:
            raise KitDownloadError(
                name="ecommerce",
                hint=(
                    "checksum mismatch on the downloaded kit archive "
                    f"(expected {expected[:12]}…, got {actual[:12]}…). Refusing to use it."
                ),
            )
        extracted = _strip_top_level(_extract(archive, tmp_path / "tree"))
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(extracted), str(dest))
    _marker(release.version).write_text("ok\n", encoding="utf-8")
    return dest


def _stream_download(client: httpx.Client, url: str, dest: Path, *, label: str) -> None:
    _require_https(url)
    with client.stream("GET", url, headers={"User-Agent": _USER_AGENT}) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes(_CHUNK):
                handle.write(chunk)
                done += len(chunk)
                _progress(label, done, total)
    _progress_end()


def _fetch_sha256(client: httpx.Client, url: str) -> str:
    _require_https(url)
    response = client.get(url, headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    # Sidecar is "<hexdigest>  <filename>"; the digest is the first token.
    return response.text.split()[0].strip().lower()


def _extract(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        # filter="data" blocks path traversal, absolute paths, and device nodes.
        tar.extractall(dest, filter="data")
    return dest


def _strip_top_level(root: Path) -> Path:
    """A ``git archive --prefix`` tarball has one top dir; return it."""
    entries = [entry for entry in root.iterdir() if entry.name != "."]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_https(url: str) -> None:
    if not url.startswith("https://"):
        raise KitDownloadError(
            name="ecommerce",
            hint=f"refusing to download the kit over a non-HTTPS URL: {url!r}.",
        )


def _api_headers() -> dict[str, str]:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _version_key(tag: str) -> tuple[int, int, int] | None:
    match = _TAG_RE.match(tag)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "arvel" / "kits"


def _cache_dir(version: str) -> Path:
    return _cache_root() / f"ecommerce-{version}"


def _marker(version: str) -> Path:
    # Sibling of the kit dir so it never gets copied into the scaffolded project.
    return _cache_root() / f"ecommerce-{version}.complete"


def _is_complete(version: str) -> bool:
    return _cache_dir(version).is_dir() and _marker(version).exists()


def _progress(label: str, done: int, total: int) -> None:
    if not sys.stderr.isatty():
        return
    if total > 0:
        filled = int(_BAR_WIDTH * done / total)
        bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
        sys.stderr.write(f"\r  {label}  [{bar}] {done / _MIB:5.1f}/{total / _MIB:.1f} MiB")
    else:
        sys.stderr.write(f"\r  {label}  {done / _MIB:5.1f} MiB")
    sys.stderr.flush()


def _progress_end() -> None:
    if sys.stderr.isatty():
        sys.stderr.write("\n")
        sys.stderr.flush()
