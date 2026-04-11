"""Template registry and download helpers for `arvel new`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import _BUNDLED_TEMPLATES

if TYPE_CHECKING:
    from concurrent.futures import Future

    from rich.console import Console


def _fetch_templates_registry() -> list[dict[str, Any]]:
    """Return the built-in template registry."""
    return list(_BUNDLED_TEMPLATES)


def _resolve_template_repo(templates: list[dict[str, Any]], name: str | None = None) -> str:
    """Resolve a template's repo URL by name, or pick the default."""
    if name:
        for t in templates:
            if t.get("name") == name:
                return t["repo"]
        available = ", ".join(t.get("name", "?") for t in templates)
        raise SystemExit(f"Unknown template '{name}'. Available: {available}")

    for t in templates:
        if t.get("default"):
            return t["repo"]

    if templates:
        return templates[0]["repo"]
    raise SystemExit("No templates found in registry.")


def _repo_to_owner_name(repo_url: str) -> str:
    """'https://github.com/owner/repo' -> 'owner/repo'."""
    repo_url = repo_url.rstrip("/")
    if repo_url.startswith("https://github.com/"):
        return repo_url.removeprefix("https://github.com/")
    return repo_url


def _start_background_download(
    repo_url: str,
    branch: str | None,
) -> Future[Path]:
    """Kick off the template download in a background thread."""
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(_download_skeleton, repo_url, branch)


def _await_download(future: Future[Path], console: Console) -> Path:
    """Show a spinner while waiting for the background download."""
    if future.done():
        return future.result()

    with console.status(
        "[bold cyan]Downloading template...[/bold cyan]",
        spinner="dots",
    ):
        return future.result()


def _download_skeleton(
    repo_url: str,
    branch: str | None = None,
) -> Path:
    """Download the template repo. Tries tarball API, then git clone, then exits."""
    owner_repo = _repo_to_owner_name(repo_url)

    if branch is None:
        branch = _resolve_latest_tag(owner_repo)

    path = _download_skeleton_tarball(owner_repo, branch)
    if path is not None:
        return path

    path = _download_skeleton_git_clone(repo_url, branch)
    if path is not None:
        return path

    raise SystemExit(
        f"Could not download template from '{repo_url}'.\n"
        "  • Check your internet connection\n"
        "  • Verify the template repo exists and is accessible\n"
        "  • Use --using <url> to specify a custom template repo"
    )


def _download_skeleton_tarball(owner_repo: str, branch: str) -> Path | None:
    """GitHub tarball API download. Returns None on failure."""
    import io
    import tarfile
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    url = f"https://github.com/{owner_repo}/tarball/{branch}"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=30) as response:  # noqa: S310
            data = response.read()
    except URLError, OSError:
        return None

    import tempfile

    extract_dir = Path(tempfile.mkdtemp(prefix="arvel-new-"))

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if ".." in member.name or member.name.startswith("/"):
                continue
            if member.issym() or member.islnk():
                continue
            tar.extract(member, extract_dir, filter="data")

    subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    return extract_dir


def _download_skeleton_git_clone(repo_url: str, branch: str) -> Path | None:
    """Shallow git clone fallback. Returns None on failure."""
    import shutil
    import subprocess
    import tempfile

    clone_dir = Path(tempfile.mkdtemp(prefix="arvel-new-"))
    target = clone_dir / "skeleton"

    try:
        result = subprocess.run(  # noqa: S603
            ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(target)],  # noqa: S607
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            # Branch/tag might not exist — retry with default branch
            result = subprocess.run(  # noqa: S603
                ["git", "clone", "--depth", "1", repo_url, str(target)],  # noqa: S607
                capture_output=True,
                timeout=60,
                check=False,
            )
        if result.returncode == 0 and target.is_dir():
            git_dir = target / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
            return target
    except FileNotFoundError, subprocess.TimeoutExpired:
        pass
    return None


def _resolve_latest_tag(owner_repo: str) -> str:
    """Latest release tag from GitHub, or 'main' if unavailable."""
    import json
    from urllib.request import Request, urlopen

    url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
            return data["tag_name"]
    except Exception:
        return "main"
