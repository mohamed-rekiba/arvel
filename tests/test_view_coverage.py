"""Coverage — View.render/to_response through a container-bound factory (doc 09)."""

from __future__ import annotations

from pathlib import Path

from arvel.kernel import Application, set_application
from arvel.views import ViewFactory, view


async def test_view_render_and_to_response(tmp_path: Path) -> None:
    (tmp_path / "hi.html").write_text("<p>{{ name }}</p>")
    app = Application()
    app.instance("view", ViewFactory(str(tmp_path)))
    set_application(app)
    try:
        rendered = await view("hi", {"name": "Ada"}).render()
        assert rendered == "<p>Ada</p>"
        response = await view("hi", {"name": "Bo"}).to_response()
        assert response.content == "<p>Bo</p>"
        assert "text/html" in response.headers["content-type"]
    finally:
        set_application(None)
