"""``arvel new --kit ...`` — kit registry and CLI integration.

The ``api`` kit's behaviour is already covered by ``test_new_command.py``;
these tests focus on the multi-kit registry surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.console._scaffold import (
    DEFAULT_KIT,
    KITS,
    KitNotInstalledError,
    KitSpec,
    UnknownKitError,
    available_kits,
    format_kit_listing,
    resolve_kit,
)
from arvel.console.entrypoint import build_app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ────────────────────────────────────────────────────────────────────
#  Kit registry — typed structure
# ────────────────────────────────────────────────────────────────────


def test_kits_registry_is_typed() -> None:
    assert isinstance(KITS, dict)
    assert all(isinstance(name, str) for name in KITS)
    assert all(isinstance(spec, KitSpec) for spec in KITS.values())
    assert KITS["api"].name == "api"
    assert KITS["ecommerce"].name == "ecommerce"


def test_default_kit_is_api() -> None:
    assert DEFAULT_KIT == "api"
    assert DEFAULT_KIT in KITS


def test_available_kits_returns_registered_names() -> None:
    names = available_kits()
    assert "api" in names
    assert "ecommerce" in names


def test_resolve_kit_returns_spec_for_known_name() -> None:
    spec = resolve_kit("api")
    assert spec.name == "api"
    assert callable(spec.resolve)


# ────────────────────────────────────────────────────────────────────
#  Unknown kit → exit 2 + listing
# ────────────────────────────────────────────────────────────────────


def test_resolve_kit_raises_unknown_kit_for_missing_name() -> None:
    with pytest.raises(UnknownKitError) as excinfo:
        resolve_kit("not-a-real-kit")
    assert excinfo.value.name == "not-a-real-kit"
    assert "api" in excinfo.value.available
    assert "ecommerce" in excinfo.value.available


def test_unknown_kit_exits_with_listing(runner: CliRunner, tmp_path: Path) -> None:
    """``--kit unknown`` → exit 2 + the available-kits listing in stderr."""
    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", "my-app", "--kit", "not-a-kit", "--no-install"])
        assert result.exit_code == 2
        assert "unknown kit" in result.stderr
        assert "api" in result.stderr
        assert "ecommerce" in result.stderr


def test_format_kit_listing_includes_every_kit() -> None:
    listing = format_kit_listing()
    assert "Available kits:" in listing
    for spec in KITS.values():
        assert spec.name in listing
        assert spec.description in listing


# ────────────────────────────────────────────────────────────────────
#  --kit flag with default api  +  api preserves behaviour
# ────────────────────────────────────────────────────────────────────


def test_new_kit_flag_appears_in_help(runner: CliRunner) -> None:
    app = build_app()
    result = runner.invoke(app, ["new", "--help"])
    assert result.exit_code == 0
    assert "--kit" in result.stdout


def test_new_kit_defaults_to_api_when_omitted(runner: CliRunner, tmp_path: Path) -> None:
    """``arvel new <name>`` without ``--kit`` produces the api skeleton."""
    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        target = Path(iso_cwd) / "my-app"
        assert (target / "bootstrap" / "app.py").exists()
        assert not (target / "backend").exists()


def test_new_explicit_api_kit_matches_default_output(runner: CliRunner, tmp_path: Path) -> None:
    """``--kit api`` and the default produce the same project layout."""
    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        runner.invoke(app, ["new", "default-app", "--no-install"])
        runner.invoke(app, ["new", "explicit-app", "--kit", "api", "--no-install"])

        default_files = sorted(
            p.relative_to(Path(iso_cwd) / "default-app")
            for p in (Path(iso_cwd) / "default-app").rglob("*")
            if p.is_file()
        )
        explicit_files = sorted(
            p.relative_to(Path(iso_cwd) / "explicit-app")
            for p in (Path(iso_cwd) / "explicit-app").rglob("*")
            if p.is_file()
        )
        assert default_files == explicit_files


# ────────────────────────────────────────────────────────────────────
#  ecommerce kit — scaffolds the full-stack demo layout
# ────────────────────────────────────────────────────────────────────


def test_new_kit_ecommerce_scaffolds_runnable_layout(runner: CliRunner, tmp_path: Path) -> None:
    """``--kit ecommerce`` copies backend / frontend / Makefile / docker-compose."""
    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-shop", "--kit", "ecommerce", "--no-install"])
        assert result.exit_code == 0, result.stderr
        target = Path(iso_cwd) / "my-shop"

        for path in [
            "backend/bootstrap/app.py",
            "backend/routes",
            "frontend/package.json",
            "Makefile",
        ]:
            assert (target / path).exists(), f"missing: {path}"


def test_new_kit_ecommerce_skips_build_caches(runner: CliRunner, tmp_path: Path) -> None:
    """node_modules / __pycache__ / .venv aren't copied into the new project."""
    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(app, ["new", "my-shop", "--kit", "ecommerce", "--no-install"])
        assert result.exit_code == 0, result.stderr
        target = Path(iso_cwd) / "my-shop"
        assert not (target / "frontend" / "node_modules").exists()
        assert not (target / ".venv").exists()


# ────────────────────────────────────────────────────────────────────
#  Kit-not-installed surface
# ────────────────────────────────────────────────────────────────────


def test_kit_not_installed_surfaces_install_hint(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registered kit whose package isn't importable → exit 1 + install hint."""
    from arvel.console._scaffold import kits as kits_module

    def _raise() -> Path:
        raise KitNotInstalledError(
            name="ecommerce",
            package="arvel-ecommerce-demo",
            original=ImportError("simulated"),
        )

    fake_spec = KitSpec(
        name="ecommerce",
        description="(test override)",
        resolve=_raise,
    )
    monkeypatch.setitem(kits_module.KITS, "ecommerce", fake_spec)

    app = build_app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", "my-app", "--kit", "ecommerce", "--no-install"])
        assert result.exit_code == 1
        assert "arvel-ecommerce-demo" in result.stderr
        assert "pip install" in result.stderr or "uv add" in result.stderr
