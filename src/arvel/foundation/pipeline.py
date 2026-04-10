"""Pipeline primitive — ordered pipe processing for middleware and workflows.

Inspired by Laravel's Pipeline. Sends a passable through a list of pipes,
where each pipe can transform the passable or short-circuit the chain.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from arvel.foundation.container import Container

Pipe = Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]

PipeSpec = type | Pipe | Callable[..., Any]
"""A pipe specification: a class (resolved via DI), a ``Pipe`` callable, or any callable."""


class Pipeline:
    """Sends a passable through an ordered list of pipes.

    Pipes can be:
    - Async callables matching the Pipe signature
    - Sync callables (adapted transparently)
    - Class references resolved through the DI container

    The passable type is erased at the pipeline level (see ADR-001).
    Individual pipes cast the passable to their expected type at runtime.
    """

    def __init__(self, container: Container | None = None) -> None:
        self._container = container
        self._passable: Any = None
        self._pipes: list[PipeSpec] = []

    def send(self, passable: Any) -> Self:
        self._passable = passable
        return self

    def through(self, pipes: list[PipeSpec]) -> Self:
        self._pipes = list(pipes)
        return self

    async def then(self, destination: Callable[..., Any]) -> Any:
        pipeline = self._build_pipeline(destination)
        return await pipeline(self._passable)

    async def then_return(self) -> Any:
        async def identity(passable: Any) -> Any:
            return passable

        return await self.then(identity)

    def _build_pipeline(self, destination: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
        async def final_dest(passable: Any) -> Any:
            if inspect.iscoroutinefunction(destination):
                return await destination(passable)
            return destination(passable)

        pipeline = final_dest

        for pipe in reversed(self._pipes):
            pipeline = self._wrap_pipe(pipe, pipeline)

        return pipeline

    def _wrap_pipe(
        self, pipe: PipeSpec, next_pipeline: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        async def wrapper(passable: Any) -> Any:
            resolved_pipe = await self._resolve_pipe(pipe)

            is_async = inspect.iscoroutinefunction(resolved_pipe)
            if not is_async and callable(resolved_pipe) and not inspect.isfunction(resolved_pipe):
                is_async = inspect.iscoroutinefunction(resolved_pipe.__call__)

            if is_async:
                return await resolved_pipe(passable, next_pipeline)
            return resolved_pipe(passable, next_pipeline)

        return wrapper

    async def _resolve_pipe(self, pipe: PipeSpec) -> Callable[..., Any]:
        if isinstance(pipe, type) and self._container is not None:
            # DI-resolved pipe classes implement __call__; cast is sound
            # because the pipeline contract requires all pipes to be callable.
            return cast("Callable[..., Any]", await self._container.resolve(pipe))
        # Non-type branches of PipeSpec are already Callable
        return cast("Callable[..., Any]", pipe)
