"""Tests for CatalogController.
Tests are written RED — arvel.i18n.catalog does not exist yet.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.fixture
def lang_dir(tmp_path: Path) -> Path:
    """Create a tiny lang dir with en.json and es.json."""
    d = tmp_path / "lang"
    d.mkdir()
    (d / "en.json").write_text(json.dumps({"greeting": "Hello"}))
    (d / "es.json").write_text(json.dumps({"greeting": "Hola"}))
    return d


#: 200 on hit


@pytest.mark.asyncio
async def test_200_on_hit(lang_dir: Path) -> None:
    from arvel.i18n.catalog import CatalogController

    ctrl = CatalogController(locales_dir=lang_dir)
    response = await ctrl.serve("en")
    assert response.status_code == 200
    body = json.loads(bytes(response.body))
    assert body["greeting"] == "Hello"


#: 304 on ETag match


@pytest.mark.asyncio
async def test_304_on_etag_match(lang_dir: Path) -> None:
    from arvel.i18n.catalog import CatalogController

    ctrl = CatalogController(locales_dir=lang_dir)
    first = await ctrl.serve("en")
    etag = first.headers.get("etag", "")
    assert etag, "ETag must be present"

    second = await ctrl.serve("en", if_none_match=etag)
    assert second.status_code == 304


def test_etag_weak_prefix_also_matches(lang_dir: Path) -> None:
    """W/ prefix on If-None-Match must still produce 304."""
    import asyncio

    from arvel.i18n.catalog import CatalogController

    async def run() -> None:
        ctrl = CatalogController(locales_dir=lang_dir)
        first = await ctrl.serve("en")
        etag = first.headers["etag"]
        weak = f"W/{etag}" if not etag.startswith("W/") else etag
        second = await ctrl.serve("en", if_none_match=weak)
        assert second.status_code == 304

    asyncio.run(run())


#: 404 unknown locale (no enumeration)


@pytest.mark.asyncio
async def test_404_unknown_locale(lang_dir: Path) -> None:
    from arvel.i18n.catalog import CatalogController

    ctrl = CatalogController(locales_dir=lang_dir)
    response = await ctrl.serve("fr")
    assert response.status_code == 404
    # Must not reveal which locales exist
    body_str = bytes(response.body).decode()
    assert "en" not in body_str
    assert "es" not in body_str


#: asyncio.Lock prevents duplicate reads


@pytest.mark.asyncio
async def test_concurrent_cold_reads_file_read_once(
    lang_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent cold requests for the same locale must read the file only once."""
    from arvel.i18n import catalog as cat_module

    read_count = 0
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_count
        if self.parent == lang_dir:
            read_count += 1
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    ctrl = cat_module.CatalogController(locales_dir=lang_dir)

    # Concurrent cold requests
    await asyncio.gather(ctrl.serve("en"), ctrl.serve("en"))

    assert read_count == 1, f"File read {read_count} times; expected 1"


# Cache-Control and Vary headers


@pytest.mark.asyncio
async def test_cache_control_header(lang_dir: Path) -> None:
    from arvel.i18n.catalog import CatalogController

    ctrl = CatalogController(locales_dir=lang_dir)
    response = await ctrl.serve("en")
    assert "public" in response.headers.get("cache-control", "")
    assert "max-age" in response.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_vary_header(lang_dir: Path) -> None:
    from arvel.i18n.catalog import CatalogController

    ctrl = CatalogController(locales_dir=lang_dir)
    response = await ctrl.serve("en")
    vary = response.headers.get("vary", "")
    assert "Accept-Encoding" in vary
