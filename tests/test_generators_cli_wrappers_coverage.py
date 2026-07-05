"""arvel.console.generators — the ``make:*`` typer command wrappers (they call the unit-tested
``generate`` core and echo the created path / exit 1 on collision)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import generators

runner = CliRunner()

# (app, arg, expected relative path)
_CASES = [
    (generators.make_event_app, "OrderPlaced", "app/events/order_placed.py"),
    (generators.make_listener_app, "NotifyTeam", "app/listeners/notify_team.py"),
    (generators.make_cast_app, "Money", "app/casts/money.py"),
    (generators.make_observer_app, "PostObserver", "app/observers/post_observer.py"),
    (generators.make_enum_app, "Status", "app/enums/status.py"),
    (generators.make_exception_app, "DomainError", "app/exceptions/domain_error.py"),
    (generators.make_test_app, "widget", "tests/test_widget.py"),
    (generators.make_migration_app, "create_posts_table", None),
]


@pytest.mark.parametrize(("app", "arg", "rel"), _CASES)
def test_make_command_wrapper_creates_a_file(
    app: object, arg: str, rel: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [arg])  # type: ignore[arg-type]
    assert result.exit_code == 0, result.output
    assert "created" in result.output
    if rel is not None:
        assert (tmp_path / rel).is_file()


def test_make_command_wrapper_exits_1_on_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(generators.make_event_app, ["Dup"]).exit_code == 0
    second = runner.invoke(generators.make_event_app, ["Dup"])
    assert second.exit_code == 1
    assert "exists" in second.output.lower() or second.output
