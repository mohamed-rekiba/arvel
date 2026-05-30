"""``make:test`` — generate a pytest feature test.

Feature tests in Arvel are plain pytest functions that boot the
application via ``bootstrap.app.create_application()`` and drive it
through Starlette's ``TestClient``. The skeleton uses this style, and
it composes naturally with the dependency-override mechanism that
``arvel.testing`` exposes for swapping container bindings per test.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{name} — feature test."""

from __future__ import annotations

from bootstrap.app import create_application
from starlette.testclient import TestClient


def test_{snake}() -> None:
    asgi = create_application().into_asgi()
    with TestClient(asgi) as client:
        response = client.get("/")
    assert response.status_code == 200
'''


class MakeTestCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:test"
    help: ClassVar[str] = "Generate a feature test (pytest + TestClient)"
    _target_subdir: ClassVar[str] = "tests/feature"

    def _render(self, name: str) -> str:
        # Strip a leading ``test_`` so the function name doesn't read as
        # ``def test_test_foo`` when the user names the file ``test_foo``.
        snake = Str.snake(name).removeprefix("test_")
        return _TEMPLATE.format(name=name, snake=snake or "smoke")
