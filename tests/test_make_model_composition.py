"""CLI-003 — `make:model` companion generation: -m/-f/-s/-c/-r/--api/-p and -a, with names
derived from the model (Product → create_products_table, ProductController, ProductFactory, …)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["make:model", *args])
    assert result.exit_code == 0, result.output


def test_bare_model_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(tmp_path, monkeypatch, "Product")
    assert (tmp_path / "app/models/product.py").exists()
    assert not (tmp_path / "app/controllers").exists()  # no companions without flags


def test_all_generates_the_whole_feature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(tmp_path, monkeypatch, "Product", "--all")
    assert (tmp_path / "app/models/product.py").exists()
    assert (tmp_path / "database/factories/product_factory.py").exists()
    assert (tmp_path / "database/seeders/product_seeder.py").exists()
    assert (tmp_path / "app/policies/product_policy.py").exists()
    # migration name is derived + pluralized
    migrations = list((tmp_path / "database/migrations").glob("*_create_products_table.py"))
    assert len(migrations) == 1
    # -a implies a resourceful controller (7 actions)
    controller = tmp_path / "app/controllers/product_controller.py"
    assert controller.exists()
    src = controller.read_text()
    for action in ("index", "create", "store", "show", "edit", "update", "destroy"):
        assert f"async def {action}" in src


def test_short_flags_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(tmp_path, monkeypatch, "Order", "-m", "-c", "-r")
    assert (tmp_path / "app/models/order.py").exists()
    assert list((tmp_path / "database/migrations").glob("*_create_orders_table.py"))
    assert (tmp_path / "app/controllers/order_controller.py").exists()


def test_api_controller_drops_create_and_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(tmp_path, monkeypatch, "Invoice", "--api")  # --api implies -c
    src = (tmp_path / "app/controllers/invoice_controller.py").read_text()
    ast.parse(src)
    for action in ("index", "store", "show", "update", "destroy"):
        assert f"async def {action}" in src
    assert "async def create" not in src and "async def edit" not in src


def test_lowercase_name_is_studlied_for_derivations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(tmp_path, monkeypatch, "blog_post", "-c")
    assert (tmp_path / "app/models/blog_post.py").read_text().count("class BlogPost") == 1
    assert (tmp_path / "app/controllers/blog_post_controller.py").exists()
