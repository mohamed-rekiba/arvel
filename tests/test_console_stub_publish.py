"""`stub:publish` — publish the generator stubs so a developer can customize them; generators
prefer an app-published stub over the built-in template once one exists."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.console.generators import generate, generate_migration, generate_test

runner = CliRunner()


def test_stub_publish_writes_every_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(build_cli(), ["stub:publish"])
    assert result.exit_code == 0, result.output
    stubs = tmp_path / "stubs"
    assert (stubs / "model.stub").is_file()
    assert (stubs / "migration.create.stub").is_file()
    assert (stubs / "migration.generic.stub").is_file()
    assert (stubs / "test.stub").is_file()


def test_stub_publish_skips_existing_unless_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(build_cli(), ["stub:publish"])
    (tmp_path / "stubs" / "model.stub").write_text("# customized\n")
    result = runner.invoke(build_cli(), ["stub:publish"])
    assert "skipped" in result.output
    assert (tmp_path / "stubs" / "model.stub").read_text() == "# customized\n"
    result = runner.invoke(build_cli(), ["stub:publish", "--force"])
    assert "skipped" not in result.output
    assert (tmp_path / "stubs" / "model.stub").read_text() != "# customized\n"


def test_generate_prefers_the_published_model_stub(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "model.stub").write_text("class {name}:\n    custom = True\n")
    target = generate("model", "Widget", base=tmp_path)
    assert target.read_text() == "class Widget:\n    custom = True\n"


def test_generate_migration_prefers_the_published_create_stub(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "migration.create.stub").write_text("# custom create {cls} {table}\n")
    target = generate_migration("create_widgets_table", base=tmp_path)
    assert target.read_text() == "# custom create CreateWidgetsTable widgets\n"


def test_generate_test_prefers_the_published_stub(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "test.stub").write_text("def test_{name}():\n    assert 1 == 1\n")
    target = generate_test("Widget", base=tmp_path)
    assert target.read_text() == "def test_widget():\n    assert 1 == 1\n"


def test_generate_falls_back_to_the_builtin_template_without_a_published_stub(
    tmp_path: Path,
) -> None:
    target = generate("model", "Widget", base=tmp_path)
    assert "class Widget(Model)" in target.read_text()
