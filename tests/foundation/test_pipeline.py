"""Tests for Pipeline primitive — Story 5.

FR-017: Pipes execute in declared order
FR-018: Short-circuit when pipe skips next
FR-019: Container-resolvable pipes
FR-020: Mixed sync/async pipes
NFR-010: Exceptions propagate (not swallowed)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from arvel.foundation.container import ContainerBuilder, Scope
from arvel.foundation.pipeline import Pipeline


class TestPipeOrdering:
    """FR-017: Pipes execute in declared order."""

    async def test_three_pipes_in_order(self) -> None:
        log: list[str] = []

        async def pipe_a(passable: dict, next_pipe: Callable) -> dict:
            log.append("A")
            return await next_pipe(passable)

        async def pipe_b(passable: dict, next_pipe: Callable) -> dict:
            log.append("B")
            return await next_pipe(passable)

        async def pipe_c(passable: dict, next_pipe: Callable) -> dict:
            log.append("C")
            return await next_pipe(passable)

        await Pipeline().send({"value": 0}).through([pipe_a, pipe_b, pipe_c]).then_return()

        assert log == ["A", "B", "C"]

    async def test_passable_modified_through_pipes(self) -> None:
        async def add_one(passable: dict, next_pipe: Callable) -> dict:
            passable["value"] += 1
            return await next_pipe(passable)

        result = await (
            Pipeline().send({"value": 0}).through([add_one, add_one, add_one]).then_return()
        )

        assert result["value"] == 3


class TestShortCircuit:
    """FR-018: Pipe that doesn't call next short-circuits."""

    async def test_skipping_next_stops_pipeline(self) -> None:
        log: list[str] = []

        async def pipe_a(passable: dict, next_pipe: Callable) -> dict:
            log.append("A")
            return await next_pipe(passable)

        async def pipe_b(passable: dict, next_pipe: Callable) -> dict:
            log.append("B")
            return passable  # does NOT call next

        async def pipe_c(passable: dict, next_pipe: Callable) -> dict:
            log.append("C")
            return await next_pipe(passable)

        await Pipeline().send({"value": 0}).through([pipe_a, pipe_b, pipe_c]).then_return()

        assert log == ["A", "B"]
        assert "C" not in log


class TestContainerResolvedPipes:
    """FR-019: Pipes specified as types are resolved via DI."""

    async def test_class_pipe_resolved_from_container(self) -> None:

        class LoggingPipe:
            def __init__(self) -> None:
                self.called = False

            async def __call__(self, passable: dict, next_pipe: Callable) -> dict:
                self.called = True
                passable["logged"] = True
                return await next_pipe(passable)

        builder = ContainerBuilder()
        builder.provide(LoggingPipe, LoggingPipe, scope=Scope.APP)
        container = builder.build()

        result = await Pipeline(container).send({"value": 0}).through([LoggingPipe]).then_return()

        assert result["logged"] is True
        await container.close()


class TestMixedSyncAsync:
    """FR-020: Sync and async pipes work together transparently."""

    async def test_sync_pipe_adapted(self) -> None:
        log: list[str] = []

        def sync_pipe(passable: dict, next_pipe: Callable) -> dict:
            log.append("sync")
            passable["sync"] = True
            # Sync pipes can't await — the pipeline adapts this
            return passable

        async def async_pipe(passable: dict, next_pipe: Callable) -> dict:
            log.append("async")
            passable["async"] = True
            return await next_pipe(passable)

        await Pipeline().send({}).through([async_pipe, sync_pipe]).then_return()

        assert "async" in log
        assert "sync" in log


class TestExceptionPropagation:
    """NFR-010: Pipeline does not swallow exceptions."""

    async def test_pipe_exception_propagates(self) -> None:
        async def exploding_pipe(passable: dict, next_pipe: Callable) -> dict:
            raise ValueError("intentional test explosion")

        with pytest.raises(ValueError, match="intentional test explosion"):
            await Pipeline().send({}).through([exploding_pipe]).then_return()

    async def test_exception_in_middle_pipe_skips_downstream(self) -> None:
        log: list[str] = []

        async def pipe_a(passable: dict, next_pipe: Callable) -> dict:
            log.append("A")
            return await next_pipe(passable)

        async def pipe_b(passable: dict, next_pipe: Callable) -> dict:
            raise RuntimeError("B failed")

        async def pipe_c(passable: dict, next_pipe: Callable) -> dict:
            log.append("C")
            return await next_pipe(passable)

        with pytest.raises(RuntimeError, match="B failed"):
            await Pipeline().send({}).through([pipe_a, pipe_b, pipe_c]).then_return()

        assert "A" in log
        assert "C" not in log


class TestPipelineThenDestination:
    """Pipeline.then() passes result to a final destination callable."""

    async def test_then_receives_final_passable(self) -> None:
        async def increment(passable: dict, next_pipe: Callable) -> dict:
            passable["value"] += 1
            return await next_pipe(passable)

        async def destination(passable: dict) -> str:
            return f"final:{passable['value']}"

        result = await (
            Pipeline().send({"value": 0}).through([increment, increment]).then(destination)
        )

        assert result == "final:2"


class TestEmptyPipeline:
    """Edge case: pipeline with no pipes returns passable unchanged."""

    async def test_no_pipes_returns_passable(self) -> None:
        result = await Pipeline().send({"value": 42}).through([]).then_return()
        assert result["value"] == 42
