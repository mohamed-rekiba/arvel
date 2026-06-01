"""make:* scaffolding commands.

 Running arvel <command> Foo writes file at canonical path
 Generated file imports right base class
 Generated file is syntactically valid Python
 Running the command twice fails with exit 1
 --force overwrites existing file
 Path-traversal-like name exits 2
 every make:* command provides a real per-command template

The old per-table generators ( / x) are now handled by
``arvel vendor:publish``; coverage lives in ``test_vendor_publish.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest
from arvel.console import Application, Command
from arvel.console.commands.make_cast import MakeCastCommand
from arvel.console.commands.make_channel import MakeChannelCommand
from arvel.console.commands.make_command import MakeCommandCommand
from arvel.console.commands.make_factory import MakeFactoryCommand
from arvel.console.commands.make_listener import MakeListenerCommand
from arvel.console.commands.make_mail import MakeMailCommand
from arvel.console.commands.make_notification import MakeNotificationCommand
from arvel.console.commands.make_observer import MakeObserverCommand
from arvel.console.commands.make_resource import MakeResourceCommand
from arvel.console.commands.make_test import MakeTestCommand
from arvel.console.commands.make_view import MakeViewCommand
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# Each row: command_cls, cli_name, name_arg, expected_relative_path, expected_substring
# expected_substring is a snippet that confirms the stub speaks to the real
# framework API (an import, decorator, or method signature unique to that primitive).
NEW_STUB_GENERATORS: list[tuple[type[Command], str, str, str, str]] = [
    (
        MakeTestCommand,
        "make:test",
        "TestSomething",
        "tests/feature/test_something.py",
        "TestClient",
    ),
    (
        MakeFactoryCommand,
        "make:factory",
        "PostFactory",
        "database/factories/post_factory.py",
        "from arvel",
    ),
    (
        MakeListenerCommand,
        "make:listener",
        "SendWelcomeEmail",
        "app/listeners/send_welcome_email.py",
        "from arvel.events import Event, Listener",
    ),
    (
        MakeNotificationCommand,
        "make:notification",
        "WelcomeNotification",
        "app/notifications/welcome_notification.py",
        "from arvel.notifications import Notification",
    ),
    (
        MakeMailCommand,
        "make:mail",
        "WelcomeMail",
        "app/mail/welcome_mail.py",
        "from arvel.mail import Content, Envelope, Mailable",
    ),
    (
        MakeCommandCommand,
        "make:command",
        "ImportUsersCommand",
        "app/console/commands/import_users_command.py",
        "from arvel.console import Command, Context",
    ),
    (
        MakeResourceCommand,
        "make:resource",
        "UserResource",
        "app/http/resources/user_resource.py",
        "from arvel",
    ),
    (
        MakeCastCommand,
        "make:cast",
        "EncryptedString",
        "app/casts/encrypted_string.py",
        "TypeDecorator",
    ),
    (
        MakeObserverCommand,
        "make:observer",
        "UserObserver",
        "app/observers/user_observer.py",
        "from arvel.database import Observer",
    ),
    (
        MakeChannelCommand,
        "make:channel",
        "OrderChannel",
        "app/broadcasting/channels/order_channel.py",
        "@Broadcast.channel",
    ),
]


@pytest.mark.parametrize(
    ("command_cls", "cli_name", "arg", "expected_path", "expected_import_substring"),
    NEW_STUB_GENERATORS,
)
def test_new_make_creates_file_at_canonical_path(
    command_cls: type[Command],
    cli_name: str,
    arg: str,
    expected_path: str,
    expected_import_substring: str,
    tmp_path: Path,
) -> None:
    """/ / : file at expected path with framework-aware content."""
    app = _app(command_cls())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, [cli_name, arg])
        assert result.exit_code == 0, result.output
        path = Path(expected_path)
        assert path.exists()
        content = path.read_text()
        assert expected_import_substring in content


@pytest.mark.parametrize(
    ("command_cls", "cli_name", "arg", "expected_path"),
    [(c, n, a, p) for c, n, a, p, _ in NEW_STUB_GENERATORS],
)
def test_new_make_generated_file_is_valid_python(
    command_cls: type[Command],
    cli_name: str,
    arg: str,
    expected_path: str,
    tmp_path: Path,
) -> None:
    """every generated stub parses as Python (or as Jinja for views)."""
    app = _app(command_cls())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, [cli_name, arg])
        source = Path(expected_path).read_text()
        if expected_path.endswith(".py"):
            ast.parse(source)


def test_make_view_emits_jinja_file(tmp_path: Path) -> None:
    """/ : make:view writes a .html.jinja file."""
    app = _app(MakeViewCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:view", "welcome"])
        assert result.exit_code == 0, result.output
        assert Path("resources/views/welcome.html.jinja").exists()


@pytest.mark.parametrize(
    ("command_cls", "cli_name", "arg", "expected_path"),
    [(c, n, a, p) for c, n, a, p, _ in NEW_STUB_GENERATORS],
)
def test_new_make_no_overwrite_without_force(
    command_cls: type[Command],
    cli_name: str,
    arg: str,
    expected_path: str,
    tmp_path: Path,
) -> None:
    """second invocation without --force fails."""
    app = _app(command_cls())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        first = runner.invoke(app.typer_app, [cli_name, arg])
        assert first.exit_code == 0, first.output
        second = runner.invoke(app.typer_app, [cli_name, arg])
        assert second.exit_code != 0


@pytest.mark.parametrize(
    "command_cls",
    [c for c, *_ in NEW_STUB_GENERATORS],
)
def test_new_make_rejects_unsafe_name(
    command_cls: type[Command],
    tmp_path: Path,
) -> None:
    """/ SR-023-003: path-traversal-like name rejected with exit 2."""
    app = _app(command_cls())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, [command_cls.name, "../EvilName"])
        assert result.exit_code == 2


# ─── Migration table generators ──────────────────────────────────────────────
#
# The old per-table generators (make:cache-table, make:queue-table,
# make:session-table, make:queue-failed-table, make:notifications-table) are
# replaced by ``arvel vendor:publish``. Each feature provider registers its
# canonical migration stub via ``self.publishes(...)`` in ``boot()``; the
# consumer publishes them as a group with ``--tag`` or ``--provider``.
#
# Coverage for the new flow lives in ``test_vendor_publish.py``.
