"""Skeleton layout structural assertions.

Tests look at the **packaged skeleton tree** under
``packages/arvel/src/arvel/_skeleton/``. They DO NOT run ``arvel new`` —
that's covered by the CLI tests. These verify the skeleton template
itself is shaped correctly so the ``new`` command's copy step produces
the canonical layout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# packages/arvel/tests/console/scaffold/test_skeleton_layout.py
#   .parents[0] = scaffold/   [1] = console/   [2] = tests/   [3] = arvel/
SKELETON_ROOT = Path(__file__).resolve().parents[3] / "src" / "arvel" / "_skeleton"


def _exists(rel: str) -> bool:
    return (SKELETON_ROOT / rel).exists()


def test_skeleton_root_exists() -> None:
    assert SKELETON_ROOT.is_dir(), f"Skeleton root not found at {SKELETON_ROOT}"


# FR-004-013 — top-level directories
@pytest.mark.parametrize(
    "directory",
    ["bootstrap", "public", "routes", "config", "app", "database", "storage", "tests"],
)
def test_top_level_directory_exists(directory: str) -> None:
    assert (SKELETON_ROOT / directory).is_dir(), f"Missing top-level dir: {directory}"


# FR-004-014 — app/ lowercase subdirectories
@pytest.mark.parametrize(
    "directory",
    [
        "app/http",
        "app/http/controllers",
        "app/http/middleware",
        "app/http/requests",
        "app/http/resources",
        "app/models",
        "app/providers",
        "app/console",
        "app/console/commands",
    ],
)
def test_app_subdirectory_exists(directory: str) -> None:
    assert (SKELETON_ROOT / directory).is_dir(), f"Missing app subdir: {directory}"


@pytest.mark.parametrize(
    "directory",
    [
        "app",
        "app/http",
        "app/http/controllers",
        "app/http/middleware",
        "app/http/requests",
        "app/http/resources",
        "app/models",
        "app/providers",
        "app/console",
        "app/console/commands",
    ],
)
def test_app_subdirectory_has_init(directory: str) -> None:
    assert (SKELETON_ROOT / directory / "__init__.py").is_file(), (
        f"Missing __init__.py in {directory}"
    )


# FR-004-015 — required files in skeleton root (template extensions OK)
@pytest.mark.parametrize(
    "candidate_names",
    [
        # Each tuple is a set of acceptable filenames; one must exist.
        # The cli renames _dot_* → .* and *.tmpl → * during copy.
        (".env.example", "_dot_env_example"),
        (".env.testing", "_dot_env_testing"),
        (".gitignore", "_dot_gitignore"),
        ("pyproject.toml", "pyproject.toml.tmpl"),
        ("README.md", "README.md.tmpl"),
    ],
)
def test_required_root_file_exists(candidate_names: tuple[str, ...]) -> None:
    assert any(_exists(n) for n in candidate_names), (
        f"None of {candidate_names} exist in the skeleton root"
    )


# FR-004-016 — routes files
@pytest.mark.parametrize("name", ["web.py", "api.py", "console.py"])
def test_routes_file_exists(name: str) -> None:
    assert (SKELETON_ROOT / "routes" / name).is_file(), f"Missing routes/{name}"


def test_routes_web_declares_root_route() -> None:
    """Skeleton's web.py declares a GET / so the smoke test has something to hit."""
    web_py = (SKELETON_ROOT / "routes" / "web.py").read_text()
    assert "@Route" in web_py or "route" in web_py.lower(), (
        "routes/web.py must declare at least one route"
    )


# FR-004-017 — config files
@pytest.mark.parametrize("name", ["app.py", "database.py", "logging.py"])
def test_config_file_exists(name: str) -> None:
    assert (SKELETON_ROOT / "config" / name).is_file(), f"Missing config/{name}"


# FR-004-018 — storage placeholders + gitignore rule
@pytest.mark.parametrize(
    "path",
    [
        "storage/app/.gitkeep",
        "storage/framework/cache/.gitkeep",
        "storage/framework/sessions/.gitkeep",
        "storage/framework/views/.gitkeep",
        "storage/logs/.gitkeep",
    ],
)
def test_storage_placeholder_exists(path: str) -> None:
    assert (SKELETON_ROOT / path).is_file(), f"Missing storage placeholder: {path}"


def test_gitignore_excludes_storage_content_but_keeps_structure() -> None:
    gi_candidates = [SKELETON_ROOT / ".gitignore", SKELETON_ROOT / "_dot_gitignore"]
    gi = next((p for p in gi_candidates if p.exists()), None)
    assert gi is not None, "No .gitignore template in skeleton root"
    content = gi.read_text()
    assert "/storage/" in content
    assert ".gitkeep" in content


# FR-004-019 — bootstrap/providers.py
def test_bootstrap_providers_declares_providers_list() -> None:
    """The skeleton's providers list is for *application* providers only.

    Framework baseline providers (Config, Log, Lang, Database, Http, Scheduler,
    Console) are auto-registered by ``Application._init_from_builder``. The
    skeleton must not enumerate them — that would cause double registration
    if the user ever adds their own provider next to them.
    """
    providers_py = (SKELETON_ROOT / "bootstrap" / "providers.py").read_text()
    assert "providers" in providers_py
    assert "ServiceProvider" in providers_py
    # Sanity: framework baseline providers must NOT be hand-listed here.
    for baseline in (
        "ConfigServiceProvider",
        "LogServiceProvider",
        "LangServiceProvider",
        "DatabaseServiceProvider",
        "HttpServiceProvider",
        "SchedulerServiceProvider",
        "ConsoleServiceProvider",
    ):
        assert baseline not in providers_py, (
            f"{baseline} is framework-baseline; do not list it in the skeleton."
        )


# FR-004-011 — bootstrap/app.py with create_application()
def test_bootstrap_app_defines_create_application() -> None:
    app_py = (SKELETON_ROOT / "bootstrap" / "app.py").read_text()
    assert "def create_application" in app_py
    assert "Application" in app_py


# FR-004-012 — public/asgi.py
def test_public_asgi_exposes_asgi_var() -> None:
    asgi_py = (SKELETON_ROOT / "public" / "asgi.py").read_text()
    assert "asgi" in asgi_py
    assert "create_application" in asgi_py


# FR-004-020 — database subdirectories
@pytest.mark.parametrize(
    "path",
    [
        "database/migrations/.gitkeep",
        "database/seeders/__init__.py",
        "database/factories/user_factory.py",
    ],
)
def test_database_subdirectory_placeholder_exists(path: str) -> None:
    assert (SKELETON_ROOT / path).exists(), f"Missing database placeholder: {path}"


# FR-004-021 — tests subdirectories
@pytest.mark.parametrize(
    "path",
    [
        "tests/feature/__init__.py",
        "tests/unit/__init__.py",
        "tests/feature/test_http_smoke.py",
        "tests/unit/test_application_boots.py",
    ],
)
def test_tests_subdirectory_file_exists(path: str) -> None:
    assert (SKELETON_ROOT / path).is_file(), f"Missing tests file: {path}"
