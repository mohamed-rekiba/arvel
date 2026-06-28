"""vendor:publish — copies resources that providers registered via ``publishes()`` into the app."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from arvel.console.publish import _copy, _publish
from arvel.kernel import ServiceProvider
from arvel.kernel.application import Application


def _app_publishing(mapping: dict[str, str], *, tag: str | None = None) -> Application:
    app = Application()

    class PublishingProvider(ServiceProvider):
        def register(self) -> None:
            self.publishes(mapping, tag=tag)

    PublishingProvider(app).register()  # populates app.published (the production path)
    return app


def test_publishes_a_registered_file(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dest = tmp_path / "out" / "config.txt"
    _publish(_app_publishing({str(src): str(dest)}), None, False)
    assert dest.read_text() == "hello"


def test_skips_existing_unless_forced(tmp_path: Path) -> None:
    src = tmp_path / "s.txt"
    src.write_text("new")
    dest = tmp_path / "d.txt"
    dest.write_text("old")
    app = _app_publishing({str(src): str(dest)})
    _publish(app, None, False)
    assert dest.read_text() == "old"  # not overwritten without --force
    _publish(app, None, True)
    assert dest.read_text() == "new"  # --force overwrites


def test_tag_filter_and_unknown_tag(tmp_path: Path) -> None:
    src = tmp_path / "s.txt"
    src.write_text("x")
    dest = tmp_path / "d.txt"
    app = _app_publishing({str(src): str(dest)}, tag="config")
    with pytest.raises(typer.Exit):
        _publish(app, "missing", False)  # unknown tag → exit 1
    _publish(app, "config", False)
    assert dest.exists()


def test_copy_directory_tree(tmp_path: Path) -> None:
    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("a")
    dest_dir = tmp_path / "vendor" / "pkg"
    assert _copy(src_dir, dest_dir, force=False) == "published"
    assert (dest_dir / "a.txt").read_text() == "a"


def test_copy_reports_missing_source(tmp_path: Path) -> None:
    assert _copy(tmp_path / "nope", tmp_path / "d", force=False) == "missing"


def test_registered_in_command_manifest() -> None:
    from arvel.console.lazy import LazyGroup

    assert (
        LazyGroup.commands_manifest["vendor:publish"] == "arvel.console.publish:vendor_publish_app"
    )
