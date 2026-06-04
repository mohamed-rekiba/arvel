"""ImageServiceProvider._register_collections_from_config — config-driven preset registration."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("arvel_image", reason="arvel_image is the package under test")

if TYPE_CHECKING:
    from arvel_image.media.collection import MediaCollection


@pytest.fixture
def clean_presets(monkeypatch: pytest.MonkeyPatch) -> Iterator[set[str]]:
    """Track preset names registered during the test and remove them afterwards.

    The provider registers presets via ``register_collection_preset`` into a
    module-level dict; isolating tests means wrapping that call so cleanup
    knows what to undo.
    """
    from arvel_image.media import presets as _presets_mod

    added: set[str] = set()
    original = _presets_mod.register_collection_preset

    def _tracking_register(name: str, collection: Any) -> None:
        added.add(name)
        original(name, collection)

    monkeypatch.setattr(_presets_mod, "register_collection_preset", _tracking_register)
    yield added
    # Best-effort cleanup; deleting through public API would need another helper.
    registry = _presets_mod.__dict__.get("_presets", {})
    for name in added:
        registry.pop(name, None)


@pytest.fixture
def fake_config_module() -> Iterator[Any]:
    """Inject a fake ``config.image`` module; remove it after the test.

    Yielded as ``Any`` so tests can dynamically assign ``collections`` —
    that's the entire point of the fixture.
    """
    # `config` package + nested `image` module — provider does
    # `importlib.import_module("config.image")`.
    pkg = ModuleType("config")
    pkg.__path__ = []  # mark as package so `config.image` resolves
    mod = ModuleType("config.image")
    sys.modules["config"] = pkg
    sys.modules["config.image"] = mod
    yield mod
    sys.modules.pop("config.image", None)
    sys.modules.pop("config", None)


async def _boot(tmp_path: Path) -> Any:
    from arvel import Application
    from arvel_image import ImageServiceProvider

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ImageServiceProvider])
        .create()
    )
    await app.boot()
    return app


# ── happy path: full config translates to MediaCollection ───────────────────


@pytest.mark.asyncio
async def test_config_with_full_collection_translates_to_preset(
    tmp_path: Path, fake_config_module: Any, clean_presets: set[str]
) -> None:
    """All optional kwargs (disk / mimes / max size / max files / conversions) propagate."""
    fake_config_module.collections = {
        "hero": {
            "disk": "s3",
            "allowed_mimetypes": ["image/jpeg", "image/PNG"],
            "max_size_bytes": 2_000_000,
            "max_files": 5,
            "conversions": {
                "thumb": {"width": 100, "height": 100, "fit": "cover", "quality": 70},
                "card": {
                    "width": 400,
                    "height": 300,
                    "fit": "contain",
                    "quality": 90,
                    "responsive": True,
                },
            },
        }
    }
    await _boot(tmp_path)

    from arvel_image.media.presets import get_collection_preset

    preset: MediaCollection = get_collection_preset("hero")
    assert preset.name == "hero"
    assert preset.disk == "s3"
    # Mimes are lower-cased on assignment.
    assert preset.accept_mime_types_list == ["image/jpeg", "image/png"]
    assert preset.max_file_size_bytes == 2_000_000
    assert preset.keep_latest_n == 5

    by_name = {c.name: c for c in preset.conversions}
    assert set(by_name) == {"thumb", "card"}
    assert by_name["card"].responsive_images_enabled is True
    assert by_name["thumb"].responsive_images_enabled is False


# ── only conversions, no other kwargs ───────────────────────────────────────


@pytest.mark.asyncio
async def test_config_with_only_conversions_registers_them(
    tmp_path: Path, fake_config_module: Any, clean_presets: set[str]
) -> None:
    fake_config_module.collections = {
        "minimal": {
            "conversions": {
                "thumb": {"width": 64, "height": 64},
            }
        }
    }
    await _boot(tmp_path)

    from arvel_image.media.presets import get_collection_preset

    preset = get_collection_preset("minimal")
    assert preset.disk is None
    assert preset.accept_mime_types_list is None
    assert preset.max_file_size_bytes is None
    assert preset.keep_latest_n is None
    assert len(preset.conversions) == 1
    assert preset.conversions[0].name == "thumb"


# ── conversion defaults: fit='contain', quality=85 ──────────────────────────


@pytest.mark.asyncio
async def test_conversion_fit_defaults_to_contain(
    tmp_path: Path, fake_config_module: Any, clean_presets: set[str]
) -> None:
    fake_config_module.collections = {
        "defaults": {"conversions": {"shrink": {"width": 200, "height": 200}}}
    }
    await _boot(tmp_path)

    from arvel_image import Image
    from arvel_image.media.presets import get_collection_preset
    from PIL import Image as PILImage

    preset = get_collection_preset("defaults")
    src_img = PILImage.new("RGB", (400, 400), (100, 200, 50))
    from io import BytesIO

    buf = BytesIO()
    src_img.save(buf, format="PNG")
    out = preset.conversions[0].apply(Image.load(buf.getvalue()))
    rebuilt = PILImage.open(BytesIO(out.format("png").to_bytes()))
    # 'contain' on a square preserves aspect — same dims.
    assert rebuilt.size == (200, 200)


# ── empty / missing config branches ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_config_module_is_a_noop(tmp_path: Path, clean_presets: set[str]) -> None:
    """When ``config.image`` doesn't exist, the provider silently skips."""
    # Make sure no fake config module is in sys.modules.
    sys.modules.pop("config.image", None)
    sys.modules.pop("config", None)
    await _boot(tmp_path)

    assert clean_presets == set()


@pytest.mark.asyncio
async def test_empty_collections_is_a_noop(
    tmp_path: Path, fake_config_module: Any, clean_presets: set[str]
) -> None:
    """An empty ``collections = {}`` registers nothing without raising."""
    fake_config_module.collections = {}
    await _boot(tmp_path)

    assert clean_presets == set()


@pytest.mark.asyncio
async def test_no_collections_attr_is_a_noop(
    tmp_path: Path, fake_config_module: Any, clean_presets: set[str]
) -> None:
    """``config.image`` without a ``collections`` attribute registers nothing."""
    # Don't set `collections` on the module.
    await _boot(tmp_path)

    assert clean_presets == set()
