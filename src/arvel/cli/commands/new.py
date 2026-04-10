"""arvel new — scaffold a new Arvel project from a GitHub template.

Fetches the starters registry from the latest framework release to resolve
the template repo URL, downloads the skeleton tarball, renders Jinja2
templates, and optionally runs uv sync + git init.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import typer
from jinja2 import Environment, FileSystemLoader

new_app = typer.Typer(name="new", help="Create a new Arvel project.")

FRAMEWORK_REPO = "mohamed-rekiba/arvel"
TEMPLATES_ASSET = "templates.json"

DATABASE_CONFIGS: dict[str, dict[str, str]] = {
    "sqlite": {
        "driver": "sqlite+aiosqlite",
        "url_template": "sqlite+aiosqlite:///database/database.sqlite",
        "package": "aiosqlite",
    },
    "postgres": {
        "driver": "postgresql+asyncpg",
        "url_template": "postgresql+asyncpg://localhost:5432/{app_name}",
        "package": "asyncpg",
    },
    "mysql": {
        "driver": "mysql+aiomysql",
        "url_template": "mysql+aiomysql://localhost:3306/{app_name}",
        "package": "aiomysql",
    },
}


def validate_project_name(name: str) -> bool:
    """Check that name is a valid directory/package name."""
    if not name:
        return False
    normalized = name.replace("-", "_")
    return bool(re.match(r"^[a-z_][a-z0-9_]*$", normalized))


def to_package_name(name: str) -> str:
    """Convert kebab-case or raw name to a valid Python package name."""
    return name.replace("-", "_").lower()


def to_pascal_case(name: str) -> str:
    """Convert snake_case or kebab-case to PascalCase."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)


def _generate_secret_key() -> str:
    """Generate a 64-character hex secret key."""
    return secrets.token_hex(32)


def _get_arvel_version() -> str:
    """Get the current arvel framework version."""
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "0.1.0"


def _fetch_templates_registry() -> list[dict[str, Any]]:
    """Fetch templates.json from the latest framework release on GitHub.

    The newest release is always marked as ``latest`` so this URL is stable.
    Falls back to the bundled templates.json shipped with the framework.
    """
    url = f"https://github.com/{FRAMEWORK_REPO}/releases/latest/download/{TEMPLATES_ASSET}"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
            return data.get("templates", [])
    except Exception:
        return _load_bundled_registry()


def _load_bundled_registry() -> list[dict[str, Any]]:
    """Load templates.json bundled inside the arvel package (offline fallback)."""
    import importlib.resources

    try:
        ref = importlib.resources.files("arvel").joinpath("templates.json")
        data = json.loads(ref.read_text(encoding="utf-8"))
        return data.get("templates", [])
    except Exception:
        return []


def _resolve_template_repo(templates: list[dict[str, Any]], name: str | None = None) -> str:
    """Find the repo URL for a template by name, or the default template."""
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
    """Extract 'owner/repo' from a GitHub URL."""
    repo_url = repo_url.rstrip("/")
    if repo_url.startswith("https://github.com/"):
        return repo_url.removeprefix("https://github.com/")
    return repo_url


def _download_skeleton(
    repo_url: str,
    branch: str | None = None,
) -> Path:
    """Download and extract the template repo tarball. Returns path to extracted dir.

    Tries the GitHub tarball API first. If that fails (private repo, no network,
    etc.), falls back to ``git clone``. Raises ``SystemExit`` only when both
    strategies fail.
    """
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
    """Try downloading via the GitHub tarball API. Returns None on failure."""
    url = f"https://github.com/{owner_repo}/tarball/{branch}"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=30) as response:  # noqa: S310
            data = response.read()
    except (URLError, OSError):
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
    """Fall back to ``git clone --depth 1``. Returns None on failure."""
    import tempfile

    clone_dir = Path(tempfile.mkdtemp(prefix="arvel-new-"))
    target = clone_dir / "skeleton"

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(target)],  # noqa: S607
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            # Branch/tag might not exist — retry with default branch
            result = subprocess.run(
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
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _resolve_latest_tag(owner_repo: str) -> str:
    """Query the GitHub API for the latest release tag."""
    url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
            return data["tag_name"]
    except Exception:
        return "main"


_GHA_ESCAPE = "\x00GHA_EXPR\x00"


def render_skeleton(
    *,
    skeleton_dir: Path,
    target_dir: Path,
    context: dict[str, Any],
) -> None:
    """Copy skeleton to target, rendering .j2 files with Jinja2.

    GitHub Actions ``${{ }}`` expressions are escaped before rendering so
    Jinja2 doesn't try to evaluate them.
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(skeleton_dir, target_dir)

    env = Environment(
        loader=FileSystemLoader(str(target_dir)),
        autoescape=False,  # noqa: S701 — rendering Python/config files, not HTML
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    for j2_file in list(target_dir.rglob("*.j2")):
        raw = j2_file.read_text(encoding="utf-8")
        escaped = raw.replace("${{", f"${_GHA_ESCAPE}{{")

        j2_file.write_text(escaped, encoding="utf-8")

        rel = j2_file.relative_to(target_dir)
        template = env.get_template(str(rel))
        rendered = template.render(**context)
        rendered = rendered.replace(f"${_GHA_ESCAPE}{{", "${{")

        output_path = j2_file.with_suffix("")
        output_path.write_text(rendered)
        j2_file.unlink()


def _setup_env(target_dir: Path, context: dict[str, Any]) -> None:
    """Create .env from .env.example if it exists."""
    env_example = target_dir / ".env.example"
    env_file = target_dir / ".env"
    if env_example.exists():
        shutil.copy2(env_example, env_file)


def _run_uv_sync(target_dir: Path) -> None:
    """Run uv sync in the project directory."""
    try:
        subprocess.run(
            ["uv", "sync"],  # noqa: S607
            cwd=target_dir,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError:
        typer.echo("Warning: uv not found. Run 'uv sync' manually.", err=True)
    except subprocess.TimeoutExpired:
        typer.echo("Warning: uv sync timed out. Run 'uv sync' manually.", err=True)


def _git_init(target_dir: Path) -> None:
    """Initialize a git repo with an initial commit."""
    try:
        subprocess.run(["git", "init"], cwd=target_dir, check=True, capture_output=True)  # noqa: S607
        subprocess.run(["git", "add", "."], cwd=target_dir, check=True, capture_output=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],  # noqa: S607
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError, subprocess.CalledProcessError:
        typer.echo("Warning: git initialization failed.", err=True)


@new_app.command(name="project")
def new_project(
    name: str = typer.Argument(help="Project name (directory name)."),
    database: str = typer.Option(
        "sqlite",
        "--database",
        "-d",
        help="Database driver: sqlite, postgres, mysql.",
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git initialization."),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Template repo branch or tag."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing directory."),
    no_install: bool = typer.Option(False, "--no-install", help="Skip uv sync."),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Template name from the registry (default: 'default')."
    ),
    using: str | None = typer.Option(
        None, "--using", help="Custom template repo URL (bypasses registry)."
    ),
    no_input: bool = typer.Option(False, "--no-input", help="Skip interactive prompts."),
) -> None:
    """Create a new Arvel project."""
    if not validate_project_name(name):
        typer.echo("Invalid project name. Use lowercase letters, digits, hyphens, and underscores.")
        raise typer.Exit(code=1)

    target = Path.cwd() / name
    if target.exists() and not force:
        typer.echo(f"Directory '{name}' already exists. Use --force to overwrite.")
        raise typer.Exit(code=1)

    if database not in DATABASE_CONFIGS:
        typer.echo(f"Unknown database '{database}'. Choose: sqlite, postgres, mysql.")
        raise typer.Exit(code=1)

    if not no_input and database == "sqlite":
        pass

    typer.echo(f"Creating project '{name}'...")

    if using:
        repo_url = using
    else:
        templates = _fetch_templates_registry()
        repo_url = _resolve_template_repo(templates, template)

    skeleton_dir = _download_skeleton(repo_url, branch)

    package_name = to_package_name(name)
    db_cfg = DATABASE_CONFIGS[database]
    secret_key = _generate_secret_key()

    context: dict[str, Any] = {
        "app_name": package_name,
        "app_name_title": to_pascal_case(package_name),
        "database_driver": db_cfg["driver"],
        "database_url": db_cfg["url_template"].format(app_name=package_name),
        "python_version": "3.14",
        "arvel_version": _get_arvel_version(),
        "secret_key": secret_key,
    }

    render_skeleton(skeleton_dir=skeleton_dir, target_dir=target, context=context)

    _setup_env(target, context)

    if database == "sqlite":
        db_dir = target / "database"
        db_dir.mkdir(exist_ok=True)
        (db_dir / "database.sqlite").touch()

    if not no_install:
        typer.echo("Installing dependencies...")
        _run_uv_sync(target)

    if not no_git:
        typer.echo("Initializing git repository...")
        _git_init(target)

    typer.echo("")
    typer.echo("Application ready! Build something amazing.")
    typer.echo("")
    typer.echo(f"  cd {name}")
    typer.echo("  arvel serve")
    typer.echo("  arvel make module <your-first-module>")
    typer.echo("")
