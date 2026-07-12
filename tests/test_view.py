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


async def test_request_scoped_shares_are_isolated_between_concurrent_renders(
    tmp_path: Path,
) -> None:
    """Flash data (`errors`/`old`) is request-scoped: two in-flight requests sharing through the
    same bound factory must each render their OWN values, even when their share/render steps
    interleave. Storing them in `env.globals` leaks one user's flash into another's response."""
    import asyncio

    (tmp_path / "who.html").write_text("{{ errors['who'] }}")
    factory = ViewFactory(str(tmp_path))

    a_shared = asyncio.Event()
    b_shared = asyncio.Event()

    async def request_a() -> str:
        factory.share_request(errors={"who": "A"})
        a_shared.set()
        await b_shared.wait()  # B shares before A renders
        return await factory.render(View("who.html"))

    async def request_b() -> str:
        await a_shared.wait()
        factory.share_request(errors={"who": "B"})
        b_shared.set()
        return await factory.render(View("who.html"))

    html_a, html_b = await asyncio.gather(request_a(), request_b())
    assert html_a == "A"
    assert html_b == "B"


async def test_request_scoped_share_does_not_touch_env_globals(tmp_path: Path) -> None:
    factory = ViewFactory(str(tmp_path))
    factory.share_request(errors={"x": ["nope"]})
    assert "errors" not in factory.env.globals


async def test_view_data_overrides_request_scoped_share(tmp_path: Path) -> None:
    (tmp_path / "v.html").write_text("{{ msg }}")
    factory = ViewFactory(str(tmp_path))
    factory.share_request(msg="shared")
    assert await factory.render(View("v.html", {"msg": "local"})) == "local"
