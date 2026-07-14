"""Example drivers: `memory` is the working default, `fake` the test double.

A driver wrapping a heavy third-party engine must lazy-import it INSIDE the
method that uses it (never at module top) and declare an extra in
pyproject.toml — the import-linter contract enforces this.
"""

from __future__ import annotations


class MemoryDriver:
    """Working example: records everything it sends."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: str) -> str:
        self.sent.append(message)
        return f"sent: {message}"


class FakeDriver:
    """Test double — script the reply, assert on calls (mirrors arvel.testing fakes)."""

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: list[str] = []

    def send(self, message: str) -> str:
        self.calls.append(message)
        return self.reply

    def assert_sent(self, message: str) -> None:
        assert message in self.calls, f"nothing sent matching {message!r}"
