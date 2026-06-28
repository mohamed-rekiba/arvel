"""Closure console commands — `Console.command("greet {name}", fn)` in routes/console.py."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from arvel import Console
from arvel.console.closure import ClosureCommand, run_closure_command
from arvel.kernel import set_application
from arvel.kernel.application import Application


class Greeter:  # module-level so get_type_hints resolves the annotation (as in a real app)
    text = "Hi"


@pytest.fixture
def app() -> Iterator[Application]:
    application = Application()
    set_application(application)
    yield application
    set_application(None)


def test_signature_parsing() -> None:
    cmd = ClosureCommand("notify {user} {title?} {--loud}", lambda: None)
    assert cmd.name == "notify"
    assert cmd.arguments() == [
        ("user", False, False),  # required positional
        ("title", False, True),  # optional positional
        ("loud", True, True),  # boolean option
    ]


def test_console_command_registers_on_the_app(app: Application) -> None:
    async def greet(name: str) -> None: ...

    returned = Console.command("greet {name}", greet)
    assert app.console_commands["greet"] is returned
    assert isinstance(returned, ClosureCommand)


def test_run_closure_passes_cli_args_and_runs_handler(app: Application) -> None:
    ran: list[str] = []

    async def greet(name: str) -> None:
        ran.append(name)

    Console.command("greet {name}", greet)
    run_closure_command("greet", {"name": "Ada"})  # dispatch through the (active) app
    assert ran == ["Ada"]


def test_run_closure_autowires_container_deps_alongside_cli_args(app: Application) -> None:
    app.instance(Greeter, Greeter())  # a typed container binding
    seen: dict[str, Any] = {}

    async def greet(
        name: str, greeter: Greeter
    ) -> None:  # name from CLI, greeter autowired by type
        seen.update(name=name, greeting=greeter.text)

    Console.command("greet {name}", greet)
    run_closure_command("greet", {"name": "Bob"})
    assert seen == {"name": "Bob", "greeting": "Hi"}


def test_lazy_builds_a_click_command_from_the_signature() -> None:
    from arvel.console.lazy import LazyGroup

    closure = ClosureCommand("ship {env} {--force}", lambda: None)
    command = LazyGroup._closure_command("ship", closure)
    params = {p.name: p for p in command.params}
    assert {"env", "force"} <= set(params)
    assert params["env"].required is True  # {env} → required argument
    assert params["force"].is_flag is True  # {--force} → boolean option


def test_malformed_signature_required_after_optional_raises_clear_error() -> None:
    from arvel.console.lazy import LazyGroup

    # an optional positional must come last; a required arg after it is invalid (also illegal in Laravel)
    with pytest.raises(ValueError, match="cannot follow an optional"):
        LazyGroup._closure_command("weird", ClosureCommand("weird {a?} {b}", lambda: None))


def test_required_argument_is_enforced() -> None:
    from click.testing import CliRunner

    from arvel.console.lazy import LazyGroup

    command = LazyGroup._closure_command("greet", ClosureCommand("greet {name}", lambda: None))
    result = CliRunner().invoke(command, [])  # required {name} omitted → usage error, not None
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_optional_positional_argument_omitted_or_given(app: Application) -> None:
    from click.testing import CliRunner

    from arvel.console.lazy import LazyGroup

    seen: list[str] = []

    async def ping(name: str = "world") -> None:
        seen.append(name)

    Console.command("ping {name?}", ping)
    command = LazyGroup._closure_command("ping", app.console_commands["ping"])
    # {name?} is an optional POSITIONAL: a value is accepted positionally, omitting it uses the default
    assert CliRunner().invoke(command, ["Bob"]).exit_code == 0
    assert seen == ["Bob"]
    CliRunner().invoke(command, [])  # omitted → handler default (not None, not an --option)
    assert seen == ["Bob", "world"]
    # and it must NOT have become an option
    assert all(not getattr(p, "is_flag", False) for p in command.params if p.name == "name")
    assert any(type(p).__name__ == "TyperArgument" and p.name == "name" for p in command.params)
