"""`arvel serve` — builds the granian argv for the app's ASGI entrypoint."""

from __future__ import annotations

import sys

from arvel.console.builtins import _serve_command


def test_serve_command_builds_granian_argv() -> None:
    cmd = _serve_command("10.1.2.3", 9000, reload=True, app="asgi:asgi_app")
    assert cmd[:3] == [sys.executable, "-m", "granian"]
    assert cmd[cmd.index("--interface") + 1] == "asgi"
    assert cmd[cmd.index("--host") + 1] == "10.1.2.3"
    assert cmd[cmd.index("--port") + 1] == "9000"
    assert "--reload" in cmd
    assert cmd[-1] == "asgi:asgi_app"


def test_serve_command_omits_reload_by_default() -> None:
    cmd = _serve_command("127.0.0.1", 8000, reload=False, app="asgi:asgi_app")
    assert "--reload" not in cmd
