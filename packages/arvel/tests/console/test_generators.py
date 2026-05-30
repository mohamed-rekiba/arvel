"""S-005-03 — Code generators (make:* commands).

AC covered:
  AC-005-003-01  generator creates file at the canonical Article X path relative to CWD
  AC-005-003-02  generator exits non-zero without --force when file already exists
  AC-005-004-01  generated file contains the class name derived from the CLI argument
  AC-005-004-02  generated file passes ruff format --check
  AC-005-004-03  generated file passes ruff check (no linting errors)
  AC-005-005-01  make:model generates model at app/models/<snake_case>.py
  AC-005-005-02  make:service generates service at app/services/<snake_case>.py
  AC-005-005-03  make:controller generates controller at app/http/controllers/<snake_case>.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# RED: arvel.console.commands.* does not exist yet
from arvel.console import Application, Command
from arvel.console.commands.make_controller import (
    MakeControllerCommand,
)
from arvel.console.commands.make_event import MakeEventCommand
from arvel.console.commands.make_job import MakeJobCommand
from arvel.console.commands.make_middleware import (
    MakeMiddlewareCommand,
)
from arvel.console.commands.make_model import MakeModelCommand
from arvel.console.commands.make_policy import MakePolicyCommand
from arvel.console.commands.make_provider import (
    MakeProviderCommand,
)
from arvel.console.commands.make_request import MakeRequestCommand
from arvel.console.commands.make_seeder import MakeSeederCommand
from arvel.console.commands.make_service import MakeServiceCommand
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ─── Helpers ─────────────────────────────────────────────────────────────────


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


# ─── AC-005-003-01: file created at canonical path ───────────────────────────


def test_make_controller_creates_file_at_canonical_path(tmp_path: Path) -> None:
    """AC-005-003-01: make:controller creates app/http/controllers/<Name>.py."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
        assert result.exit_code == 0
        assert Path("app/http/controllers/article_controller.py").exists()


def test_make_model_creates_file_at_canonical_path(tmp_path: Path) -> None:
    """AC-005-005-01: make:model creates app/models/<Name>.py."""
    app = _app(MakeModelCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:model", "Article"])
        assert result.exit_code == 0
        assert Path("app/models/article.py").exists()


def test_make_service_creates_file_at_canonical_path(tmp_path: Path) -> None:
    """AC-005-005-02: make:service creates app/services/<Name>.py."""
    app = _app(MakeServiceCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:service", "ArticleService"])
        assert result.exit_code == 0
        assert Path("app/services/article_service.py").exists()


# ─── AC-005-003-02: no-overwrite guard ───────────────────────────────────────


def test_make_controller_exits_nonzero_when_file_exists(tmp_path: Path) -> None:
    """AC-005-003-02: generator exits non-zero if target exists and --force not set."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("app/http/controllers").mkdir(parents=True, exist_ok=True)
        Path("app/http/controllers/article_controller.py").write_text("# existing")
        result = runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
        assert result.exit_code != 0


def test_make_controller_force_overwrites_existing_file(tmp_path: Path) -> None:
    """AC-005-003-02: --force flag allows overwriting an existing file."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("app/http/controllers").mkdir(parents=True, exist_ok=True)
        Path("app/http/controllers/article_controller.py").write_text("# old content")
        result = runner.invoke(app.typer_app, ["make:controller", "ArticleController", "--force"])
        assert result.exit_code == 0
        content = Path("app/http/controllers/article_controller.py").read_text()
        assert "# old content" not in content


# ─── AC-005-004-01: class name derived from CLI argument ─────────────────────


def test_generated_controller_contains_class_name(tmp_path: Path) -> None:
    """AC-005-004-01: generated file contains a class matching the CLI argument."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
        content = Path("app/http/controllers/article_controller.py").read_text()
        assert "class ArticleController" in content


def test_generated_model_contains_class_name(tmp_path: Path) -> None:
    """AC-005-004-01: generated model file contains the correct class name."""
    app = _app(MakeModelCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:model", "Article"])
        content = Path("app/models/article.py").read_text()
        assert "class Article" in content


def test_generated_model_defaults_to_guard_all(tmp_path: Path) -> None:
    """Generated models must require explicit fillable fields before mass assignment."""
    app = _app(MakeModelCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["make:model", "Article"])
        assert result.exit_code == 0
        content = Path("app/models/article.py").read_text()
        assert '__guarded__ = ["*"]' in content


# ─── AC-005-004-02: generated file passes ruff format --check ────────────────


def test_generated_controller_passes_ruff_format(tmp_path: Path) -> None:
    """AC-005-004-02: generated controller is properly formatted by ruff."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
        assert _ruff_format_check(Path("app/http/controllers/article_controller.py"))


def test_generated_model_passes_ruff_format(tmp_path: Path) -> None:
    """AC-005-004-02: generated model is properly formatted by ruff."""
    app = _app(MakeModelCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:model", "Article"])
        assert _ruff_format_check(Path("app/models/article.py"))


# ─── AC-005-004-03: generated file passes ruff check ────────────────────────


def test_generated_controller_passes_ruff_lint(tmp_path: Path) -> None:
    """AC-005-004-03: generated controller has no ruff linting errors."""
    app = _app(MakeControllerCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:controller", "ArticleController"])
        assert _ruff_lint_check(Path("app/http/controllers/article_controller.py"))


def test_generated_model_passes_ruff_lint(tmp_path: Path) -> None:
    """AC-005-004-03: generated model has no ruff linting errors."""
    app = _app(MakeModelCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["make:model", "Article"])
        assert _ruff_lint_check(Path("app/models/article.py"))


# ─── Additional generator canonical paths ────────────────────────────────────


@pytest.mark.parametrize(
    ("command_cls", "cli_name", "arg", "expected_path"),
    [
        (MakeServiceCommand, "make:service", "ArticleService", "app/services/article_service.py"),
        (MakeJobCommand, "make:job", "PublishPost", "app/jobs/publish_post.py"),
        (MakeEventCommand, "make:event", "PostPublished", "app/events/post_published.py"),
        (
            MakeMiddlewareCommand,
            "make:middleware",
            "Authenticate",
            "app/http/middleware/authenticate.py",
        ),
        (MakePolicyCommand, "make:policy", "PostPolicy", "app/policies/post_policy.py"),
        (
            MakeProviderCommand,
            "make:provider",
            "SearchServiceProvider",
            "app/providers/search_service_provider.py",
        ),
        (
            MakeRequestCommand,
            "make:request",
            "StorePostRequest",
            "app/http/requests/store_post_request.py",
        ),
        (MakeSeederCommand, "make:seeder", "PostSeeder", "database/seeders/post_seeder.py"),
    ],
)
def test_generator_canonical_path(
    command_cls: type,
    cli_name: str,
    arg: str,
    expected_path: str,
    tmp_path: Path,
) -> None:
    """AC-005-003-01: each make:* generator writes to the correct Article X path."""
    app = _app(command_cls())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, [cli_name, arg])
        assert result.exit_code == 0, result.output
        assert Path(expected_path).exists(), f"Expected {expected_path} to exist"
