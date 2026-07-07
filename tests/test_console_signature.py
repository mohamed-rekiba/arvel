"""Signature grammar (CLI-4): {arg}/{arg?}/{arg=default}/{arg*}/{--flag}/{--opt=}/{--opt=*}/
{--S|shortcut} parse into a typed spec and map to real Typer params."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from click.testing import CliRunner

from arvel.console.closure import SignatureArg, parse_signature
from arvel.kernel import set_application
from arvel.kernel.application import Application


@pytest.fixture
def app() -> Iterator[Application]:
    application = Application()
    set_application(application)
    yield application
    set_application(None)


def test_parse_every_signature_form() -> None:
    tokens = parse_signature(
        "report:send {user} {title?} {count=1} {tags*} {--force} {--tag=} {--id=*} {--Q|queue}"
    )
    assert tokens == [
        SignatureArg(name="user"),
        SignatureArg(name="title", optional=True),
        SignatureArg(name="count", optional=True, default="1"),
        SignatureArg(name="tags", optional=True, variadic=True),
        SignatureArg(name="force", is_option=True, optional=True),
        SignatureArg(name="tag", is_option=True, optional=True, takes_value=True),
        SignatureArg(name="id", is_option=True, optional=True, variadic=True, takes_value=True),
        SignatureArg(name="queue", is_option=True, optional=True, shortcut="Q"),
    ]


def test_command_name_is_the_first_word_not_a_token() -> None:
    tokens = parse_signature("app:command")
    assert tokens == []


def test_typer_params_built_from_every_form() -> None:
    from arvel.console.lazy import LazyGroup

    class Descriptor:
        signature = "widget:make {name} {qty=1} {tags*} {--force} {--tag=} {--id=*} {--Q|queue}"
        description = ""

    command = LazyGroup._command_class_command("widget:make", Descriptor(), lambda *_a, **_k: None)
    params = {p.name: p for p in command.params}
    assert {"name", "qty", "tags", "force", "tag", "id", "queue"} <= set(params)
    assert params["name"].required is True
    assert params["qty"].default == "1"
    assert params["force"].is_flag is True
    assert "-Q" in params["queue"].opts


def test_command_class_with_no_tokens_builds_a_bare_command() -> None:
    from click.testing import CliRunner

    from arvel.console.lazy import LazyGroup

    class Descriptor:
        signature = "ping"  # no {args} at all
        description = ""

    ran: list[str] = []
    command = LazyGroup._command_class_command(
        "ping", Descriptor(), lambda descriptor: ran.append(descriptor.signature)
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 0, result.output
    assert ran == ["ping"]


def test_required_after_optional_is_rejected() -> None:
    from arvel.console.lazy import LazyGroup

    class Descriptor:
        signature = "bad {a?} {b}"
        description = ""

    with pytest.raises(ValueError, match="cannot follow an optional"):
        LazyGroup._command_class_command("bad", Descriptor(), lambda *_a, **_k: None)


def test_default_value_argument_is_used_when_omitted(app: Application) -> None:
    from arvel.console.lazy import LazyGroup

    seen: list[str] = []

    async def ping(name: str) -> None:
        seen.append(name)

    from arvel import Console

    Console.command("ping {name=world}", ping)
    command = LazyGroup._closure_command("ping", app.console_commands["ping"])
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 0, result.output
    assert seen == ["world"]


def test_variadic_option_collects_multiple_values() -> None:
    from arvel.console.lazy import LazyGroup

    class Descriptor:
        signature = "notify {--id=*}"
        description = ""

    seen: dict[str, object] = {}

    def _run(descriptor: object, **kwargs: object) -> None:
        seen.update(kwargs)

    command = LazyGroup._command_class_command("notify", Descriptor(), _run)
    result = CliRunner().invoke(command, ["--id", "1", "--id", "2"])
    assert result.exit_code == 0, result.output
    assert seen["id"] == ["1", "2"]


def test_get_command_returns_a_directly_added_command_before_consulting_the_manifest() -> None:
    import click

    from arvel.console.lazy import LazyGroup

    group = LazyGroup(name="arvel")

    @click.command("foo")
    def foo() -> None: ...

    group.add_command(foo, name="foo")
    assert group.get_command(None, "foo") is foo  # super().get_command() short-circuits


def test_get_command_returns_none_for_a_totally_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.kernel as kernel_module
    from arvel.console.lazy import LazyGroup

    monkeypatch.setattr(kernel_module, "discover_app_commands", lambda: {})
    group = LazyGroup(name="arvel")
    assert group.get_command(None, "nope-not-a-command") is None


def test_get_command_builds_a_closure_command_from_a_discovered_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.kernel as kernel_module
    from arvel.console.closure import ClosureCommand
    from arvel.console.lazy import LazyGroup

    seen: list[str] = []
    closure = ClosureCommand("greet {name}", lambda name: seen.append(name))
    monkeypatch.setattr(kernel_module, "discover_app_commands", lambda: {"greet": closure})

    group = LazyGroup(name="arvel")
    command = group.get_command(None, "greet")
    assert command is not None
    assert command.name == "greet"


def test_get_command_degrades_to_none_on_a_malformed_closure_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.kernel as kernel_module
    from arvel.console.closure import ClosureCommand
    from arvel.console.lazy import LazyGroup

    bad = ClosureCommand("weird {a?} {b}", lambda: None)  # required after optional
    monkeypatch.setattr(kernel_module, "discover_app_commands", lambda: {"weird": bad})

    group = LazyGroup(name="arvel")
    assert group.get_command(None, "weird") is None  # warns + returns None, doesn't crash --help


def test_get_command_builds_a_command_class_command_from_a_discovered_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.kernel as kernel_module
    from arvel.console.lazy import LazyGroup

    class Descriptor:
        signature = "widget:make {name}"
        description = "make a widget"

    monkeypatch.setattr(
        kernel_module, "discover_app_commands", lambda: {"widget:make": Descriptor()}
    )
    monkeypatch.setattr(kernel_module, "run_command_class", lambda *_a, **_k: None)

    group = LazyGroup(name="arvel")
    command = group.get_command(None, "widget:make")
    assert command is not None
    assert command.name == "widget:make"


def test_get_command_degrades_to_none_on_a_malformed_command_class_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.kernel as kernel_module
    from arvel.console.lazy import LazyGroup

    class BadDescriptor:
        signature = "bad {a?} {b}"  # required after optional
        description = ""

    monkeypatch.setattr(kernel_module, "discover_app_commands", lambda: {"bad": BadDescriptor()})

    group = LazyGroup(name="arvel")
    assert group.get_command(None, "bad") is None  # warns + returns None, doesn't crash --help
