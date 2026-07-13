"""make:* CLI command wrappers — exercise each typer command function (not just the generate() core),
so the scaffolds run through the real `_run` path (writes a file, echoes, errors on overwrite)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import typer

from arvel.console import generators as g

# (command function, name, expected relative path)
_COMMANDS = [
    (g.make_model, "Post", "app/models/post.py"),
    (g.make_controller, "PostController", "app/controllers/post_controller.py"),
    (g.make_middleware, "Throttle", "app/middleware/throttle.py"),
    (g.make_request, "StorePost", "app/requests/store_post.py"),
    (g.make_job, "SendReport", "app/jobs/send_report.py"),
    (g.make_policy, "PostPolicy", "app/policies/post_policy.py"),
    (g.make_notification, "InvoicePaid", "app/notifications/invoice_paid.py"),
    (g.make_mail, "OrderShipped", "app/mail/order_shipped.py"),
    (g.make_rule, "Uppercase", "app/rules/uppercase.py"),
    (g.make_seeder, "PostSeeder", "database/seeders/post_seeder.py"),
    (g.make_factory, "PostFactory", "database/factories/post_factory.py"),
    (g.make_provider, "RouteProvider", "app/providers/route_provider.py"),
    (g.make_command, "SyncOrders", "app/commands/sync_orders.py"),
]


@pytest.mark.parametrize("fn,name,rel", _COMMANDS)
def test_make_command_writes_a_parseable_file(
    fn: object, name: str, rel: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fn(name)  # type: ignore[operator]  # the typer command is still a plain callable
    target = tmp_path / rel
    assert target.exists()
    ast.parse(target.read_text())  # generated stub is valid Python


def test_make_migration_command_writes_timestamped_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    g.make_migration("create_widgets_table")
    matches = list((tmp_path / "database" / "migrations").glob("*_create_widgets_table.py"))
    assert len(matches) == 1
    assert "class CreateWidgetsTable(Migration)" in matches[0].read_text()


def test_make_command_exits_on_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    g.make_model("Dup")
    with pytest.raises(typer.Exit):  # second run hits the FileExistsError -> typer.Exit(1)
        g.make_model("Dup")
