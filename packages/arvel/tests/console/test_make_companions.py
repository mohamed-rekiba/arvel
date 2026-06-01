"""make:* name completion + companion generation.

Two capabilities added on top of the base generators:

- **Name completion** — typing the bare root completes the conventional
  suffix (``make:controller Post`` → ``PostController``), idempotently.
- **Companion generation** — ``make:controller`` and ``make:model`` scaffold
  the related artifacts in one command, all named from the same root.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from arvel.console import Application, Command
from arvel.console.commands.make_controller import MakeControllerCommand
from arvel.console.commands.make_model import MakeModelCommand
from arvel.console.commands.make_policy import MakePolicyCommand
from arvel.console.commands.make_service import MakeServiceCommand
from arvel.support.str import Str
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ───────────────────────────── Str.plural ─────────────────────────────


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("post", "posts"),
        ("category", "categories"),
        ("comments", "comments"),  # already plural
        ("blog_post", "blog_posts"),
        ("", ""),
    ],
)
def test_str_plural(word: str, expected: str) -> None:
    assert Str.plural(word) == expected


# ───────────────────────── name completion ─────────────────────────


def test_controller_bare_name_gets_suffix(tmp_path: Path) -> None:
    app = _app(MakeControllerCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:controller", "Post"])
        assert result.exit_code == 0, result.output
        content = Path("app/http/controllers/post_controller.py").read_text()
        assert "class PostController" in content


def test_controller_full_name_is_idempotent(tmp_path: Path) -> None:
    app = _app(MakeControllerCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:controller", "PostController"])
        assert result.exit_code == 0, result.output
        assert Path("app/http/controllers/post_controller.py").exists()
        assert "class PostController" in Path("app/http/controllers/post_controller.py").read_text()


def test_service_bare_name_gets_suffix(tmp_path: Path) -> None:
    app = _app(MakeServiceCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:service", "Payment"])
        assert result.exit_code == 0, result.output
        assert Path("app/services/payment_service.py").exists()
        assert "class PaymentService" in Path("app/services/payment_service.py").read_text()


def test_policy_bare_name_gets_suffix(tmp_path: Path) -> None:
    app = _app(MakePolicyCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:policy", "Post"])
        assert result.exit_code == 0, result.output
        assert Path("app/policies/post_policy.py").exists()


# ──────────────────── make:controller companions ────────────────────


def test_controller_observer_policy_requests(tmp_path: Path) -> None:
    app = _app(MakeControllerCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app.typer_app,
            [
                "make:controller",
                "Post",
                "--resource",
                "--model",
                "--observer",
                "--policy",
                "--requests",
            ],
        )
        assert result.exit_code == 0, result.output
        assert Path("app/http/controllers/post_controller.py").exists()
        assert Path("app/models/post.py").exists()
        assert Path("app/observers/post_observer.py").exists()
        assert Path("app/policies/post_policy.py").exists()
        assert Path("app/http/requests/store_post_request.py").exists()
        assert Path("app/http/requests/update_post_request.py").exists()


# ──────────────────────── make:model hub ────────────────────────


def test_model_all_scaffolds_full_set(tmp_path: Path) -> None:
    app = _app(MakeModelCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:model", "Comment", "--all"])
        assert result.exit_code == 0, result.output
        assert Path("app/models/comment.py").exists()
        assert Path("database/factories/comment_factory.py").exists()
        assert Path("database/seeders/comment_seeder.py").exists()
        assert Path("app/policies/comment_policy.py").exists()
        assert Path("app/observers/comment_observer.py").exists()
        assert Path("app/http/resources/comment_resource.py").exists()
        assert Path("app/http/requests/store_comment_request.py").exists()
        assert Path("app/http/requests/update_comment_request.py").exists()
        assert Path("app/http/controllers/comment_controller.py").exists()
        assert Path("tests/feature/test_comment.py").exists()
        migrations = list(Path("database/migrations").glob("*_create_comments_table.py"))
        assert migrations, "expected a create_comments_table migration"


def test_model_individual_companion_flags(tmp_path: Path) -> None:
    app = _app(MakeModelCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:model", "Tag", "-mf"])
        assert result.exit_code == 0, result.output
        assert Path("app/models/tag.py").exists()
        assert Path("database/factories/tag_factory.py").exists()
        assert list(Path("database/migrations").glob("*_create_tags_table.py"))


def test_model_existing_companion_is_skipped_not_failed(tmp_path: Path) -> None:
    app = _app(MakeModelCommand())
    with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
        Path("app/policies").mkdir(parents=True, exist_ok=True)
        Path("app/policies/widget_policy.py").write_text("# pre-existing")
        result = runner.invoke(app.typer_app, ["make:model", "Widget", "--policy"])
        assert result.exit_code == 0, result.output
        assert "Exists" in result.output
        assert Path("app/policies/widget_policy.py").read_text() == "# pre-existing"
