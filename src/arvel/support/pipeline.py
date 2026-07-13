"""arvel.support.pipeline — an onion/middleware pipeline.

Each pipe is `(value, next)`, not a plain transform: it decides *whether* and *how* to call
`next`, so pipes can wrap the rest of the pipeline (before/after logic) or short-circuit it
entirely. A 1-arg callable is auto-adapted into that shape as ergonomic sugar (a pure transform
that always calls `next`). No container coupling in v1 — pipes are instances/callables passed
directly, not class names; DI resolution can layer in later without an API break.

    result = await Pipeline().send(x).through([a, b]).then(dest)   # dest called with final value
    value  = await Pipeline().send(x).through([a, b]).then_return()
    Pipeline().via("process")   # method name used for object pipes (default "handle")
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any

#: What every pipe is normalized to: `(value, next) -> result-or-awaitable`.
type _Layer = Callable[[Any, Callable[[Any], Awaitable[Any]]], Any]


def _arity(fn: Callable[..., Any]) -> int:
    """Count `fn`'s positional parameters — used to tell a `(value)` transform from a
    `(value, next)` onion pipe. Opaque/builtin callables default to 2 (the onion shape)."""
    try:
        signature = inspect.signature(fn)
    except TypeError, ValueError:
        return 2
    return sum(
        1
        for param in signature.parameters.values()
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )


def _as_transform(fn: Callable[[Any], Any]) -> _Layer:
    """Adapt a 1-arg transform into the `(value, next)` shape: apply it, then always continue."""

    def transform(value: Any, next_: Callable[[Any], Awaitable[Any]]) -> Any:
        result = fn(value)
        if inspect.isawaitable(result):

            async def _continue() -> Any:
                return await next_(await result)

            return _continue()
        return next_(result)

    return transform


class Pipeline:
    """Send a value `through` a list of pipes, terminating in `then`/`then_return`."""

    def __init__(self) -> None:
        self._passable: Any = None
        self._pipes: Sequence[Any] = ()
        self._method: str = "handle"

    def send(self, passable: Any) -> Pipeline:
        self._passable = passable
        return self

    def through(self, pipes: Iterable[Any]) -> Pipeline:
        self._pipes = list(pipes)
        return self

    def via(self, method: str) -> Pipeline:
        """The method name to call on object pipes (a plain callable pipe is used as-is)."""
        self._method = method
        return self

    async def then(self, destination: Callable[[Any], Any]) -> Any:
        """Run the pipeline, calling `destination` with the final value."""

        async def run_destination(value: Any) -> Any:
            result = destination(value)
            return await result if inspect.isawaitable(result) else result

        pipeline: Callable[[Any], Awaitable[Any]] = run_destination
        for pipe in reversed(self._pipes):
            pipeline = self._carry(pipe, pipeline)
        return await pipeline(self._passable)

    async def then_return(self) -> Any:
        """Run the pipeline and return the piped value, with no destination."""
        return await self.then(lambda value: value)

    def _carry(
        self, pipe: Any, next_pipeline: Callable[[Any], Awaitable[Any]]
    ) -> Callable[[Any], Awaitable[Any]]:
        layer = self._adapt(pipe)

        async def call(value: Any) -> Any:
            result = layer(value, next_pipeline)
            return await result if inspect.isawaitable(result) else result

        return call

    def _adapt(self, pipe: Any) -> _Layer:
        """Resolve `pipe` to a `(value, next)` layer: the `via`-named method on an object, or the
        callable itself — auto-adapted from a 1-arg transform when its arity says so."""
        handler = getattr(pipe, self._method, None)
        target = handler if callable(handler) else pipe
        if not callable(target):
            raise TypeError(f"pipe {pipe!r} is not callable and has no {self._method!r} method")
        return _as_transform(target) if _arity(target) == 1 else target
