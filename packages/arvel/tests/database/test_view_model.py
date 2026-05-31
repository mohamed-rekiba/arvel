"""Tests for ViewModel — read-only guards, refresh() routing, and make:model flags."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from arvel.database import ReadOnlyModelError, ViewModel, id_
from arvel.database.query import QueryBuilder

# ── fixtures ──────────────────────────────────────────────────────────────────


class ArticleStats(ViewModel):
    __tablename__ = "v_article_stats"
    id: int = id_()


class ArticleStatsMat(ViewModel):
    __tablename__ = "mv_article_stats"
    __is_materialized_view__ = True
    id: int = id_()


# ── class-level flags ─────────────────────────────────────────────────────────


def test_view_model_is_read_only() -> None:
    assert ArticleStats.__read_only__ is True


def test_view_model_not_materialized_by_default() -> None:
    assert ArticleStats.__is_materialized_view__ is False


def test_materialized_view_flag() -> None:
    assert ArticleStatsMat.__is_materialized_view__ is True


# ── ActiveRecord write guards ─────────────────────────────────────────────────


async def test_create_raises(session: Any) -> None:
    with pytest.raises(ReadOnlyModelError, match="create"):
        await ArticleStats.create(id=1)


async def test_save_raises(session: Any) -> None:
    instance = ArticleStats.__new__(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="save"):
        await instance.save()


async def test_delete_raises(session: Any) -> None:
    instance = ArticleStats.__new__(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="delete"):
        await instance.delete()


async def test_force_delete_raises(session: Any) -> None:
    instance = ArticleStats.__new__(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="force_delete"):
        await instance.force_delete()


# ── QueryBuilder write guards ─────────────────────────────────────────────────


async def test_qb_insert_raises(session: Any) -> None:
    qb = QueryBuilder(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="insert"):
        await qb.insert([{"id": 1}])


async def test_qb_update_raises(session: Any) -> None:
    qb = QueryBuilder(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="update"):
        await qb.update({"id": 2})


async def test_qb_delete_raises(session: Any) -> None:
    qb = QueryBuilder(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="delete"):
        await qb.delete()


async def test_qb_increment_raises(session: Any) -> None:
    qb = QueryBuilder(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="increment"):
        await qb.increment("id")


async def test_qb_upsert_raises(session: Any) -> None:
    qb = QueryBuilder(ArticleStats)
    with pytest.raises(ReadOnlyModelError, match="upsert"):
        await qb.upsert([{"id": 1}], unique_by=["id"], update=["id"])


# ── refresh() routing ─────────────────────────────────────────────────────────


async def test_refresh_view_raises_for_regular_view(session: Any) -> None:
    with pytest.raises(ReadOnlyModelError, match="refresh_view"):
        await ArticleStats.refresh_view()


async def test_refresh_view_calls_schema_for_materialized_view(
    session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []

    def _fake_refresh(view_name: str, *, concurrently: bool = False) -> None:
        calls.append((view_name, concurrently))

    import arvel.database.schema as _schema_mod

    monkeypatch.setattr(_schema_mod.Schema, "refresh_materialized_view", _fake_refresh)

    await ArticleStatsMat.refresh_view()
    assert calls == [("mv_article_stats", False)]


async def test_refresh_view_concurrently_passes_flag(
    session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []

    def _fake_refresh(view_name: str, *, concurrently: bool = False) -> None:
        calls.append((view_name, concurrently))

    import arvel.database.schema as _schema_mod

    monkeypatch.setattr(_schema_mod.Schema, "refresh_materialized_view", _fake_refresh)

    await ArticleStatsMat.refresh_view(concurrently=True)
    assert calls == [("mv_article_stats", True)]


# ── make:model --view / --materialized-view ───────────────────────────────────


def _run_make_model(tmp_path: Path, *args: str) -> tuple[int, str]:
    from arvel.console import Application
    from arvel.console.commands.make_model import MakeModelCommand
    from typer.testing import CliRunner

    app = Application(commands=[MakeModelCommand()])
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:model", *args])
    return result.exit_code, result.output


def test_make_model_default_generates_model(tmp_path: Path) -> None:
    code, output = _run_make_model(tmp_path, "ArticleStats")
    assert code == 0, output
    # isolated_filesystem writes files inside tmp_path's subdirectory
    generated = list(tmp_path.glob("**/article_stats.py"))
    assert generated, f"file not found in {list(tmp_path.rglob('*.py'))}"
    text = generated[0].read_text()
    assert "class ArticleStats(Model" in text
    assert "Timestamps" in text
    ast.parse(text)


def test_make_model_view_generates_view_model(tmp_path: Path) -> None:
    code, output = _run_make_model(tmp_path, "ArticleStats", "--view")
    assert code == 0, output
    generated = list(tmp_path.glob("**/article_stats.py"))
    assert generated
    text = generated[0].read_text()
    assert "class ArticleStats(ViewModel)" in text
    assert "__is_materialized_view__" not in text
    ast.parse(text)


def test_make_model_materialized_view_generates_mat_view(tmp_path: Path) -> None:
    code, output = _run_make_model(tmp_path, "ArticleStats", "--materialized-view")
    assert code == 0, output
    generated = list(tmp_path.glob("**/article_stats.py"))
    assert generated
    text = generated[0].read_text()
    assert "class ArticleStats(ViewModel)" in text
    assert "__is_materialized_view__ = True" in text
    ast.parse(text)


def test_make_model_view_and_materialized_are_mutually_exclusive(tmp_path: Path) -> None:
    code, output = _run_make_model(tmp_path, "ArticleStats", "--view", "--materialized-view")
    assert code != 0
    assert "mutually exclusive" in output
