"""``make:controller --resource`` scaffold.

The base ``make:controller`` already exists ;
this iteration adds three flags:

- ``--resource`` : generate the seven canonical CRUD method stubs
- ``--api`` : drop ``create`` and ``edit`` (HTML form methods)
- ``--model=Post``: import ``Post`` from ``app.models.<snake>`` and type
 the member-method parameter accordingly

The generated file must pass ``ruff`` immediately (lint + format).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

from arvel.console import Application, Command
from arvel.console.commands.make_controller import MakeControllerCommand
from click.testing import CliRunner as ClickCliRunner
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


def _ruff_format_check(path: Path) -> bool:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "format", "--check", str(path)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _ruff_lint_check(path: Path) -> bool:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "check", str(path)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


# ───────────────────────────── --resource ─────────────────────────────


class TestResourceFlag:
    """--resource generates all seven RESTful method stubs."""

    def test_resource_creates_file_at_canonical_path(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                app.typer_app, ["make:controller", "PostController", "--resource"]
            )
            assert result.exit_code == 0, result.output
            assert Path("app/http/controllers/post_controller.py").exists()

    def test_resource_includes_all_seven_methods(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(app.typer_app, ["make:controller", "PostController", "--resource"])
            content = Path("app/http/controllers/post_controller.py").read_text()
            for method in ("index", "create", "store", "show", "edit", "update", "destroy"):
                assert f"async def {method}" in content, f"missing method {method}: {content}"

    def test_resource_methods_raise_not_implemented(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(app.typer_app, ["make:controller", "PostController", "--resource"])
            content = Path("app/http/controllers/post_controller.py").read_text()
            # Every body should be a NotImplementedError raise — no fake returns.
            assert content.count("raise NotImplementedError") == 7

    def test_resource_has_class_inheriting_controller(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(app.typer_app, ["make:controller", "PostController", "--resource"])
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "class PostController(Controller):" in content


# ───────────────────────────── --api ─────────────────────────────


class TestApiFlag:
    """--api omits create and edit (the HTML form methods)."""

    def test_api_drops_create_and_edit(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--api"],
            )
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "async def create" not in content
            assert "async def edit" not in content

    def test_api_keeps_remaining_five_methods(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--api"],
            )
            content = Path("app/http/controllers/post_controller.py").read_text()
            for method in ("index", "store", "show", "update", "destroy"):
                assert f"async def {method}" in content
            assert content.count("raise NotImplementedError") == 5

    def test_api_without_resource_is_rejected(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(app.typer_app, ["make:controller", "PostController", "--api"])
            assert result.exit_code != 0
            assert "--api" in result.output and "--resource" in result.output


# ───────────────────────────── --model=Post ─────────────────────────────


class TestModelFlag:
    """--model generates the model, imports it, and types the member parameter."""

    def test_model_imports_named_class(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--model"],
            )
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "from app.models.post import Post" in content

    def test_model_generates_the_model_file(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--model"],
            )
            assert result.exit_code == 0, result.output
            assert Path("app/models/post.py").exists()

    def test_model_name_overrides_derived_name(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "BlogController", "--resource", "--model-name", "Article"],
            )
            content = Path("app/http/controllers/blog_controller.py").read_text()
            assert "from app.models.article import Article" in content
            assert Path("app/models/article.py").exists()

    def test_model_types_member_method_param(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--model"],
            )
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "async def show(self, post: Post)" in content
            assert "async def edit(self, post: Post)" in content
            assert "async def update(self, post: Post)" in content
            assert "async def destroy(self, post: Post)" in content

    def test_model_without_resource_generates_basic_controller_and_model(
        self, tmp_path: Path
    ) -> None:
        # --model no longer requires --resource: it generates the model and a
        # basic controller (which has no member methods to bind the model to).
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(app.typer_app, ["make:controller", "PostController", "--model"])
            assert result.exit_code == 0, result.output
            assert Path("app/models/post.py").exists()
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "from app.models" not in content

    def test_model_works_with_api(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--api", "--model"],
            )
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "from app.models.post import Post" in content
            assert "async def show(self, post: Post)" in content
            assert "async def create" not in content
            assert "async def edit" not in content

    def test_model_snake_cases_import_path(self, tmp_path: Path) -> None:
        # MultiWord model → multi_word module.
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "BlogPostController", "--resource", "--model"],
            )
            content = Path("app/http/controllers/blog_post_controller.py").read_text()
            assert "from app.models.blog_post import BlogPost" in content
            assert "async def show(self, blog_post: BlogPost)" in content


# ───────────────────────────── Quality of generated file ─────────────────────────────


class TestGeneratedFileQuality:
    """generated file passes ruff (format + lint) immediately."""

    def test_resource_file_passes_ruff_format(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(app.typer_app, ["make:controller", "PostController", "--resource"])
            assert _ruff_format_check(Path("app/http/controllers/post_controller.py"))

    def test_resource_file_passes_ruff_lint(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(app.typer_app, ["make:controller", "PostController", "--resource"])
            assert _ruff_lint_check(Path("app/http/controllers/post_controller.py"))

    def test_resource_api_file_passes_ruff(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--api"],
            )
            path = Path("app/http/controllers/post_controller.py")
            assert _ruff_format_check(path)
            assert _ruff_lint_check(path)

    def test_resource_with_model_file_passes_ruff(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--model"],
            )
            path = Path("app/http/controllers/post_controller.py")
            assert _ruff_format_check(path)
            assert _ruff_lint_check(path)


# ───────────────────────────── Backward compat ─────────────────────────────


class TestBackwardCompat:
    """Without --resource, the existing behavior holds."""

    def test_default_make_controller_unchanged(self, tmp_path: Path) -> None:
        # Existing -005-03: app/http/controllers/<snake>.py with the
        # 5-method legacy template still wins when no flags are passed.
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
            assert result.exit_code == 0
            content = Path("app/http/controllers/article_controller.py").read_text()
            # Legacy template returns dicts; the new resource template raises.
            assert "raise NotImplementedError" not in content

    def test_force_overwrites_with_resource(self, tmp_path: Path) -> None:
        app = _app(MakeControllerCommand())
        with cast("ClickCliRunner", runner).isolated_filesystem(temp_dir=tmp_path):
            Path("app/http/controllers").mkdir(parents=True, exist_ok=True)
            Path("app/http/controllers/post_controller.py").write_text("# old")
            result = runner.invoke(
                app.typer_app,
                ["make:controller", "PostController", "--resource", "--force"],
            )
            assert result.exit_code == 0
            content = Path("app/http/controllers/post_controller.py").read_text()
            assert "# old" not in content
            assert "async def index" in content
