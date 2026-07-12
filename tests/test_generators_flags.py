"""CLI-002/003 — generator flags (--force, make:controller -r/--api/-i, make:migration
--create/--table) and type-safe stub output (real Request/Schema/ClassVar types, not Any)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.console.generators import generate, generate_migration

runner = CliRunner()


def _cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), list(args))
    assert result.exit_code == 0, result.output


# --- --force overwrites (CLI-002) --------------------------------------------
def test_force_overwrites_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(tmp_path, monkeypatch, "make:middleware", "Auth")
    # without --force a second run fails
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(build_cli(), ["make:middleware", "Auth"]).exit_code == 1
    # with --force it succeeds
    _cli(tmp_path, monkeypatch, "make:middleware", "Auth", "--force")


# --- make:controller flags (CLI-003) -----------------------------------------
def test_make_controller_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cli(tmp_path, monkeypatch, "make:controller", "PostController", "--resource")
    src = (tmp_path / "app/controllers/post_controller.py").read_text()
    for action in ("index", "create", "store", "show", "edit", "update", "destroy"):
        assert f"async def {action}" in src


def test_make_controller_api_and_invokable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(tmp_path, monkeypatch, "make:controller", "ApiC", "--api")
    api = (tmp_path / "app/controllers/api_c.py").read_text()
    assert "async def create" not in api and "async def edit" not in api
    _cli(tmp_path, monkeypatch, "make:controller", "InvokeC", "-i")
    inv = (tmp_path / "app/controllers/invoke_c.py").read_text()
    assert "async def __call__" in inv


# --- make:migration --create / --table (CLI-003) -----------------------------
def test_make_migration_create_and_table(tmp_path: Path) -> None:
    create = generate_migration("whatever", base=tmp_path, create="products")
    assert 'schema.create("products"' in create.read_text()
    alter = generate_migration("tweak_orders", base=tmp_path, table="orders")
    body = alter.read_text()
    assert "schema.create" not in body  # --table forces the generic (alter) stub


# --- type-safe stubs: real types, not Any (the "why aren't files type-safe" fix) ---
def test_stubs_use_real_types_not_any(tmp_path: Path) -> None:
    controller = generate("controller", "PostController", base=tmp_path).read_text()
    assert "request: Request" in controller and "request: Any" not in controller
    assert "-> dict[str, Any]" in controller

    model = generate("model", "Post", base=tmp_path).read_text()
    assert "__fillable__: ClassVar[list[str]]" in model  # matches the base ClassVar

    factory = generate("factory", "PostFactory", base=tmp_path).read_text()
    assert "Factory[Any]" in factory  # the generic is parametrized

    migration = generate_migration("create_posts_table", base=tmp_path).read_text()
    assert "def up(self, schema: Schema) -> None:" in migration
    assert "def define(t: Blueprint) -> None:" in migration
