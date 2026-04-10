"""Tests for structured concurrency utility — FR-004."""

from __future__ import annotations

import pytest
from anyio import sleep

from arvel.context.concurrency import Concurrency


class TestConcurrencyRun:
    """FR-004.1 / FR-004.2 / FR-004.3: run() parallel execution."""

    async def test_run_returns_results_in_input_order(self) -> None:
        async def slow() -> str:
            await sleep(0.05)
            return "slow"

        async def fast() -> str:
            return "fast"

        results = await Concurrency.run([slow, fast])
        assert results == ["slow", "fast"]

    async def test_run_fail_fast_on_exception(self) -> None:
        async def good() -> str:
            await sleep(0.5)
            return "ok"

        async def bad() -> str:
            msg = "task failed"
            raise ValueError(msg)

        with pytest.raises(BaseExceptionGroup):
            await Concurrency.run([good, bad])

    async def test_run_with_deadline(self) -> None:
        async def forever() -> str:
            await sleep(60)
            return "never"

        with pytest.raises(TimeoutError):
            await Concurrency.run([forever], deadline=0.1)

    async def test_run_empty_list(self) -> None:
        results = await Concurrency.run([])
        assert results == []

    async def test_run_single_task(self) -> None:
        async def one() -> int:
            return 42

        results = await Concurrency.run([one])
        assert results == [42]


class TestConcurrencyGather:
    """FR-004.4 / FR-004.5: gather() with exception collection."""

    async def test_gather_returns_all_results(self) -> None:
        async def a() -> int:
            return 1

        async def b() -> int:
            return 2

        results = await Concurrency.gather([a, b])
        assert results == [1, 2]

    async def test_gather_raises_on_error_by_default(self) -> None:
        async def ok() -> str:
            return "ok"

        async def fail() -> str:
            msg = "oops"
            raise RuntimeError(msg)

        with pytest.raises(BaseExceptionGroup):
            await Concurrency.gather([ok, fail])

    async def test_gather_return_exceptions_true(self) -> None:
        async def ok() -> str:
            return "ok"

        async def fail() -> str:
            msg = "oops"
            raise RuntimeError(msg)

        results = await Concurrency.gather([ok, fail], return_exceptions=True)
        assert results[0] == "ok"
        assert isinstance(results[1], RuntimeError)

    async def test_gather_empty_list(self) -> None:
        results = await Concurrency.gather([])
        assert results == []


class TestConcurrencyContextInheritance:
    """Concurrent tasks inherit parent context."""

    async def test_tasks_see_parent_context(self) -> None:
        from arvel.context.context_store import Context

        Context.flush()
        Context.add("tenant_id", 99)

        async def check_context() -> int:
            val = Context.get("tenant_id")
            return val if isinstance(val, int) else 0

        results = await Concurrency.run([check_context, check_context])
        assert results == [99, 99]
        Context.flush()
