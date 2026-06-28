"""Views (doc 09) — namespaced view loaders (pkg::name). Test-first."""

from __future__ import annotations

from pathlib import Path

import pytest

from arvel.views import View, ViewFactory


def _dirs(tmp_path: Path) -> tuple[str, str]:
    main = tmp_path / "views"
    main.mkdir()
    (main / "home.html").write_text("main home")
    pkg = tmp_path / "pkg_views"
    pkg.mkdir()
    (pkg / "panel.html").write_text("admin panel {{ name }}")
    return str(main), str(pkg)


async def test_namespaced_template_resolves(tmp_path: Path) -> None:
    main, pkg = _dirs(tmp_path)
    factory = ViewFactory(paths=main)
    factory.add_namespace("admin", pkg)

    rendered = await factory.render(View("admin::panel.html", {"name": "Ada"}))
    assert rendered == "admin panel Ada"


async def test_main_paths_still_resolve_after_namespacing(tmp_path: Path) -> None:
    main, pkg = _dirs(tmp_path)
    factory = ViewFactory(paths=main)
    factory.add_namespace("admin", pkg)

    rendered = await factory.render(View("home.html", {}))
    assert rendered == "main home"


async def test_unknown_namespace_raises(tmp_path: Path) -> None:
    from jinja2 import TemplateNotFound

    main, _ = _dirs(tmp_path)
    factory = ViewFactory(paths=main)
    with pytest.raises(TemplateNotFound):
        await factory.render(View("missing::thing.html", {}))
