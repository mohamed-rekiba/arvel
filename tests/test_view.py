"""Phase 7 — View factory (Jinja2 async) + view() helper."""

from __future__ import annotations

from pathlib import Path

from arvel.views import View, ViewFactory, view


def test_view_helper_builds_template_name() -> None:
    v = view("pages.home", {"x": 1})
    assert v.template == "pages/home.html"
    assert v.data == {"x": 1}


def test_top_level_view_helper_is_not_shadowed_by_the_submodule() -> None:
    """Regression: `from arvel import view` must resolve to the callable helper even after the views
    submodule is imported (the view provider imports it at boot). The helper used to live at
    `arvel.view`, colliding with the `arvel.view` submodule, so the documented `from arvel import view`
    returned the module and 500'd ('module object is not callable') in any app using views."""
    import arvel.views  # noqa: F401 — force the submodule to load, as the provider does at boot
    from arvel import view as top_level_view

    assert callable(top_level_view)
    assert top_level_view("pages.home").template == "pages/home.html"


async def test_factory_renders_template(tmp_path: Path) -> None:
    (tmp_path / "hello.html").write_text("<h1>Hi {{ name }}</h1>")
    factory = ViewFactory(str(tmp_path))
    html = await factory.render(View("hello.html", {"name": "Ada"}))
    assert html == "<h1>Hi Ada</h1>"


async def test_autoescape_is_on(tmp_path: Path) -> None:
    (tmp_path / "e.html").write_text("{{ body }}")
    factory = ViewFactory(str(tmp_path))
    html = await factory.render(View("e.html", {"body": "<script>x</script>"}))
    assert "&lt;script&gt;" in html  # escaped


async def test_extends_and_blocks(tmp_path: Path) -> None:
    (tmp_path / "layout.html").write_text("<body>{% block content %}{% endblock %}</body>")
    (tmp_path / "page.html").write_text(
        '{% extends "layout.html" %}{% block content %}<p>{{ msg }}</p>{% endblock %}'
    )
    factory = ViewFactory(str(tmp_path))
    html = await factory.render(View("page.html", {"msg": "hello"}))
    assert html == "<body><p>hello</p></body>"


def test_share_adds_globals(tmp_path: Path) -> None:
    factory = ViewFactory(str(tmp_path))
    factory.share(app_name="arvel")
    assert factory.env.globals["app_name"] == "arvel"
