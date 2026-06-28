"""Views (doc 09) — the Vite manifest reader: hashed asset tags from manifest.json. Test-first."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_tags_emit_script_and_css(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    html = vite.tags("resources/js/app.js")
    assert '<link rel="stylesheet" href="/build/assets/app.def456.css">' in html
    assert '<script type="module" src="/build/assets/app.abc123.js"></script>' in html


def test_asset_resolves_hashed_url(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    assert vite.asset("resources/js/app.js") == "/build/assets/app.abc123.js"


def test_unknown_entry_raises_clear_error(tmp_path: Path) -> None:
    vite = Vite(manifest_path=_manifest(tmp_path), base="/build")
    with pytest.raises(KeyError, match="missing"):
        vite.tags("resources/js/missing.js")
