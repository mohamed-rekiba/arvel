"""Shared test fixtures and helpers for the Reverb test suite."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast


class QueueWS:
    """Queue-backed fake WebSocket used by ReverbServer integration tests.

    Frames pushed via :meth:`push` are read by the server's ``async for`` loop.
    The loop only terminates when :meth:`close_input` is called, so tests can
    interleave reads and writes deterministically.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent: list[str] = []
        self._handshake: asyncio.Event = asyncio.Event()

    async def send(self, msg: str) -> None:
        self.sent.append(msg)
        if "pusher:connection_established" in msg:
            self._handshake.set()

    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> str:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def push(self, frame: str) -> None:
        await self._queue.put(frame)

    async def close_input(self) -> None:
        await self._queue.put(None)

    async def wait_handshake(self) -> str:
        await self._handshake.wait()
        handshake = cast("dict[str, Any]", json.loads(self.sent[0]))
        data_field: Any = handshake["data"]
        payload = cast(
            "dict[str, Any]",
            data_field if isinstance(data_field, dict) else json.loads(data_field),
        )
        return cast("str", payload["socket_id"])

    async def wait_for(self, substring: str, *, attempts: int = 50, interval: float = 0.01) -> bool:
        for _ in range(attempts):
            if any(substring in m for m in self.sent):
                return True
            await asyncio.sleep(interval)
        return False
