"""Tests for the Prunable mixin and model:prune command."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arvel.database.model import Prunable


class TestPrunableMixin:
    """Prunable raises NotImplementedError on default prunable_query."""

    def test_abstract_prunable_query_raises(self) -> None:
        class Unpruned(Prunable):
            pass

        obj = Unpruned()
        with pytest.raises(NotImplementedError, match="prunable_query"):
            obj.prunable_query()

    def test_concrete_prunable_query_is_callable(self) -> None:
        sentinel = object()

        class PrunedModel(Prunable):
            def prunable_query(self) -> Any:
                return sentinel

        assert PrunedModel().prunable_query() is sentinel

    def test_prunable_is_pure_mixin_no_sqla_columns(self) -> None:
        # Prunable must not introduce any SQLAlchemy column definitions.
        prunable = Prunable()
        assert not hasattr(prunable, "__table__")
        assert not hasattr(prunable, "__tablename__")


class TestModelPruneCommand:
    """model:prune dispatches prunable_query.force_delete for each registered model."""

    @pytest.mark.asyncio
    async def test_prune_force_deletes_on_each_model(self) -> None:
        from arvel.console.commands.model_prune import ModelPruneCommand

        mock_qb = MagicMock()
        mock_qb.force_delete = AsyncMock(return_value=5)

        class FakeModel(Prunable):
            __name__ = "FakeModel"

            def prunable_query(self) -> Any:
                return mock_qb

        with (
            patch(
                "arvel.console.commands.model_prune.collect_prunable_models",
                return_value=[FakeModel],
            ),
            patch("typer.echo"),
        ):
            cmd = ModelPruneCommand()
            cmd.app = MagicMock()  # non-None so the guard passes
            await cmd.prune()

        mock_qb.force_delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prune_exits_when_app_not_bound(self) -> None:
        import typer
        from arvel.console.commands.model_prune import ModelPruneCommand

        cmd = ModelPruneCommand()
        cmd.app = None
        with pytest.raises(typer.Exit):
            await cmd.prune()

    def test_collect_skips_abstract_models(self) -> None:
        from arvel.console.commands.model_prune import collect_prunable_models
        from arvel.database.model import Model

        # Build a fake mapper list with one abstract and one concrete Prunable
        class FakeConcreteMapper:
            class_ = type(
                "ConcreteModel",
                (Prunable,),
                {"__abstract__": False},
            )

        class FakeAbstractMapper:
            class_ = type(
                "AbstractModel",
                (Prunable,),
                {"__abstract__": True},
            )

        fake_mappers: list[Any] = [FakeConcreteMapper, FakeAbstractMapper]
        with patch.object(type(Model.registry), "mappers", property(lambda _: fake_mappers)):
            result = collect_prunable_models()

        assert len(result) == 1
        assert result[0].__name__ == "ConcreteModel"
