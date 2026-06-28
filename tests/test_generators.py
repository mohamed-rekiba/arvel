"""C8a — make:* code generators."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.console.generators import generate
from arvel.console.lazy import LazyGroup


def test_generate_model_writes_stub(tmp_path: Path) -> None:
    target = generate("model", "BlogPost", base=tmp_path)
    assert target == tmp_path / "app/models/blog_post.py"
    assert "class BlogPost(Model):" in target.read_text()
    assert (tmp_path / "app/models/__init__.py").exists()


@pytest.mark.parametrize(
    ("kind", "name", "expected"),
    [
        ("model", "Post", "class Post(Model):"),
        ("controller", "PostController", "class PostController(Controller):"),
        ("middleware", "Auth", "class Auth(Middleware):"),
        ("request", "StorePost", "class StorePost(FormRequest):"),
    ],
)
def test_generated_stubs_are_valid_python(
    kind: str, name: str, expected: str, tmp_path: Path
) -> None:
    target = generate(kind, name, base=tmp_path)
    source = target.read_text()
    assert expected in source
    compile(source, str(target), "exec")  # syntactically valid


def test_generate_refuses_overwrite(tmp_path: Path) -> None:
    generate("model", "Dup", base=tmp_path)
    with pytest.raises(FileExistsError):
        generate("model", "Dup", base=tmp_path)


def test_make_commands_registered_in_manifest() -> None:
    manifest = set(LazyGroup.commands_manifest)
    assert {"make:model", "make:controller", "make:middleware", "make:request"} <= manifest


def test_make_model_via_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(build_cli(), ["make:model", "Widget"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "app/models/widget.py").exists()
