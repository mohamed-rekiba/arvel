"""Views (doc 09) — the Vite manifest reader: hashed asset tags from manifest.json. Test-first."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arvel.views.vite import Vite


def _manifest(tmp_path: Path) -> str:
    data = {
        "resources/js/app.js": {
            "file": "assets/app.abc123.js",
            "css": ["assets/app.def456.css"],
        }
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return str(path)


async def test_tags_emit_script_and_css(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    html = await vite.tags("resources/js/app.js")
    assert '<link rel="stylesheet" href="/build/assets/app.def456.css">' in html
    assert '<script type="module" src="/build/assets/app.abc123.js"></script>' in html


async def test_asset_resolves_hashed_url(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    assert await vite.asset("resources/js/app.js") == "/build/assets/app.abc123.js"


async def test_unknown_entry_raises_clear_error(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    with pytest.raises(KeyError, match="missing"):
        await vite.tags("resources/js/missing.js")


async def test_manifest_is_read_off_the_event_loop(tmp_path: Path) -> None:
    """The manifest read goes through anyio.to_thread.run_sync, not a direct blocking call."""
    import arvel.views.vite as vite_module

    calls: list[Any] = []
    original = vite_module.run_sync

    async def _spy(fn: Any, *args: Any) -> Any:
        calls.append(fn)
        return await original(fn, *args)

    vite_module.run_sync = _spy
    try:
        vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
        await vite.asset("resources/js/app.js")
    finally:
        vite_module.run_sync = original
    assert calls


async def test_vite_global_renders_unescaped_html(tmp_path: Path, monkeypatch: Any) -> None:
    """The ``vite()`` template global must return Markup so the trusted tags render as HTML — not
    escaped into ``&lt;script&gt;`` by the autoescaping environment (the documented usage has no
    ``| safe``)."""
    build = tmp_path / "public" / "build"
    build.mkdir(parents=True)
    (build / "manifest.json").write_text(
        json.dumps(
            {
                "resources/js/app.js": {
                    "file": "assets/app.abc123.js",
                    "css": ["assets/app.def456.css"],
                }
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    from arvel.views import ViewFactory

    factory = ViewFactory("resources/views")
    template = factory.env.from_string('{{ vite("resources/js/app.js") }}')
    out = await template.render_async()

    assert '<script type="module" src="/build/assets/app.abc123.js"></script>' in out
    assert "&lt;script" not in out  # would be escaped without the Markup wrapper
