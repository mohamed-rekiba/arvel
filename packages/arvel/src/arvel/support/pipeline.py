"""Generic async middleware pipeline.

Behavior is documented in PRD-001 §FR-001-006.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Generic, TypeVar, cast

InT = TypeVar("InT")
OutT = TypeVar("OutT")

Next = Callable[[InT], Awaitable[OutT]]
Middleware = Callable[[InT, Next[InT, OutT]], Awaitable[OutT]]


class Pipeline(Generic[InT, OutT]):
    """Compose async middlewares around a final handler."""

    def __init__(self) -> None:
        self._payload: InT | None = None
        self._payload_set: bool = False
        self._middlewares: Sequence[Middleware[InT, OutT]] = ()

    def send(self, payload: InT) -> Pipeline[InT, OutT]:
        self._payload = payload
        self._payload_set = True
        return self

    def through(self, middlewares: Sequence[Middleware[InT, OutT]]) -> Pipeline[InT, OutT]:
        self._middlewares = tuple(middlewares)
        return self

    async def then(self, final: Callable[[InT], Awaitable[OutT]]) -> OutT:
        if not self._payload_set:
            msg = "Pipeline.then() called before Pipeline.send()."
            raise RuntimeError(msg)

        # Compose middlewares right-to-left so they execute left-to-right.
        chain: Next[InT, OutT] = final
        for mw in reversed(self._middlewares):
            current_mw = mw
            previous_chain = chain

            async def step(
                value: InT,
                *,
                _mw: Middleware[InT, OutT] = current_mw,
                _nxt: Next[InT, OutT] = previous_chain,
            ) -> OutT:
                return await _mw(value, _nxt)

            chain = step

        # The cast below is sound: send() requires InT, and we tracked that it was set.
        payload = cast("InT", self._payload)
        return await chain(payload)
