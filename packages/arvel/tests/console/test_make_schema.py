"""``arvel make:schema`` — generate Pydantic schemas from a model (lesson L6).

Covers:

* Introspecting an SQLA-mapped class and emitting ``Read`` / ``Create`` /
  ``Update`` schemas at the canonical path.
* Excluding server-managed fields (autoincrement PK, ``created_at``,
  ``updated_at``, ``deleted_at``, ``__hidden__`` columns) from ``Create``.
* Mapping common SQLA types (``Integer``, ``String``, ``Boolean``,
  ``DateTime``) to the matching Python annotations.
* Emitting valid, ruff-clean Python.
* Surfacing a useful diagnostic when the model can't be imported.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from arvel.console import Application
from arvel.console.commands.make_schema import MakeSchemaCommand
from typer.testing import CliRunner

runner = CliRunner()


def _app() -> Application:
    return Application(commands=[MakeSchemaCommand()])


def _write_model(model_dir: Path, snake: str, body: str) -> None:
    """Write a model module the command can import via ``app.models.<snake>``."""
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "__init__.py").write_text("")
    (model_dir / f"{snake}.py").write_text(body)


_USER_MODEL = textwrap.dedent(
    '''
    """User — ORM model."""

    from __future__ import annotations

    from typing import ClassVar

    from arvel.database import Model, Timestamps, id_, string


    class User(Model, Timestamps):
        __tablename__ = "users_schema_test"
        __hidden__: ClassVar[list[str]] = ["password"]

        id: int = id_()
        name: str = string(255)
        email: str = string(254, unique=True)
        billing_email: str = string(254)
        password: str = string(255)
    '''
).lstrip()


def test_make_schema_creates_file_at_canonical_path(tmp_path: Path) -> None:
    """make:schema User writes app/schemas/user_schema.py."""
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        # Need the empty app/__init__.py so app.models.user is importable.
        Path("app/__init__.py").write_text("")
        result = runner.invoke(app.typer_app, ["make:schema", "User"])
        assert result.exit_code == 0, result.output
        assert Path("app/schemas/user_schema.py").exists()


def test_generated_file_emits_three_classes(tmp_path: Path) -> None:
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        runner.invoke(app.typer_app, ["make:schema", "User"])
        content = Path("app/schemas/user_schema.py").read_text()
        assert "class UserRead(BaseModel):" in content
        assert "class UserCreate(BaseModel):" in content
        assert "class UserUpdate(BaseModel):" in content


def test_create_excludes_server_managed_fields(tmp_path: Path) -> None:
    """UserCreate drops ``id`` (autoincrement PK), ``created_at``, ``updated_at``."""
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        runner.invoke(app.typer_app, ["make:schema", "User"])
        content = Path("app/schemas/user_schema.py").read_text()

        # Slice the UserCreate body.
        create_idx = content.index("class UserCreate(BaseModel):")
        update_idx = content.index("class UserUpdate(BaseModel):")
        create_body = content[create_idx:update_idx]

        assert "id:" not in create_body, "autoincrement PK must not appear on Create"
        assert "created_at:" not in create_body
        assert "updated_at:" not in create_body
        assert "password:" not in create_body, "__hidden__ columns must not appear on Create"
        assert "name: str" in create_body
        # ``email`` and ``*_email`` columns are upgraded to ``EmailStr`` at the boundary
        # (ADR-077). Storage stays VARCHAR; the validation lives in the Pydantic schema.
        assert "email: EmailStr" in create_body
        assert "billing_email: EmailStr" in create_body


def test_update_makes_every_field_optional(tmp_path: Path) -> None:
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        runner.invoke(app.typer_app, ["make:schema", "User"])
        content = Path("app/schemas/user_schema.py").read_text()
        update_idx = content.index("class UserUpdate(BaseModel):")
        update_body = content[update_idx:]
        # Every field on Update is ``T | None = None``.
        assert "name: str | None = None" in update_body
        assert "email: EmailStr | None = None" in update_body
        assert "billing_email: EmailStr | None = None" in update_body


def test_read_includes_timestamps_excludes_hidden(tmp_path: Path) -> None:
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        runner.invoke(app.typer_app, ["make:schema", "User"])
        content = Path("app/schemas/user_schema.py").read_text()
        read_idx = content.index("class UserRead(BaseModel):")
        create_idx = content.index("class UserCreate(BaseModel):")
        read_body = content[read_idx:create_idx]

        assert "id: int" in read_body
        assert "created_at: datetime" in read_body
        assert "updated_at: datetime" in read_body
        assert "password:" not in read_body, "Hidden columns must not appear on Read"


def test_generated_file_passes_ruff_check(tmp_path: Path) -> None:
    """Generated schemas must be ruff-clean — no follow-up clean-up needed."""
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        runner.invoke(app.typer_app, ["make:schema", "User"])
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "app/schemas/user_schema.py"],
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, (
            "Generated file is not ruff-clean:\n" + result.stdout + result.stderr
        )


def test_no_force_blocks_overwrite(tmp_path: Path) -> None:
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        Path("app/schemas").mkdir(parents=True)
        Path("app/schemas/user_schema.py").write_text("# existing")
        result = runner.invoke(app.typer_app, ["make:schema", "User"])
        assert result.exit_code != 0
        assert Path("app/schemas/user_schema.py").read_text() == "# existing"


def test_force_overwrites(tmp_path: Path) -> None:
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _write_model(Path("app/models"), "user", _USER_MODEL)
        Path("app/__init__.py").write_text("")
        Path("app/schemas").mkdir(parents=True)
        Path("app/schemas/user_schema.py").write_text("# existing")
        result = runner.invoke(app.typer_app, ["make:schema", "User", "--force"])
        assert result.exit_code == 0
        assert "# existing" not in Path("app/schemas/user_schema.py").read_text()


def test_missing_model_returns_actionable_error(tmp_path: Path) -> None:
    """Diagnostic must tell the user what they need to do next."""
    app = _app()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("app").mkdir()
        Path("app/__init__.py").write_text("")
        result = runner.invoke(app.typer_app, ["make:schema", "Nonexistent"])
        assert result.exit_code != 0
        assert "make:model" in result.output or "make:model" in (result.stderr or "")
