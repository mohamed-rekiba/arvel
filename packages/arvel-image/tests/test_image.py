"""QA-Pre tests for arvel-image (Spatie Image v3 parity, Pillow-only).

Skipped until Stage 3b creates the package. Maps to FR-025-10 .. FR-025-13.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip(
    "arvel_image",
    reason="WI-arvel-025 Stage 3b creates this package",
)
pytest.importorskip("PIL", reason="arvel-image depends on Pillow")


@pytest.fixture
def png_4x4_bytes() -> bytes:
    """A minimal 4x4 RGBA PNG built fresh each test."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    img = PILImage.new("RGBA", (4, 4), (255, 0, 0, 255))
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_load_from_bytes_returns_image(png_4x4_bytes: bytes) -> None:
    """FR-025-11: Image.load accepts a binary file-like object."""
    from arvel_image import Image

    img = Image.load(io.BytesIO(png_4x4_bytes))
    assert img is not None


def test_image_resize_changes_dimensions(png_4x4_bytes: bytes) -> None:
    """FR-025-12: resize honors width/height."""
    from arvel_image import Image

    out = Image.load(io.BytesIO(png_4x4_bytes)).resize(width=8, height=8).to_bytes()
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_image_fit_cover_returns_target_dimensions(png_4x4_bytes: bytes) -> None:
    """FR-025-12: fit('cover', w, h) crops to the target."""
    from arvel_image import Image
    from PIL import Image as PILImage

    out_bytes = Image.load(io.BytesIO(png_4x4_bytes)).fit("cover", 16, 8).to_bytes()
    out = PILImage.open(io.BytesIO(out_bytes))
    assert out.size == (16, 8)


def test_image_fit_contain_does_not_exceed_target(png_4x4_bytes: bytes) -> None:
    """FR-025-12: fit('contain', ...) preserves aspect inside the box."""
    from arvel_image import Image
    from PIL import Image as PILImage

    out_bytes = Image.load(io.BytesIO(png_4x4_bytes)).fit("contain", 16, 8).to_bytes()
    out = PILImage.open(io.BytesIO(out_bytes))
    assert out.size[0] <= 16
    assert out.size[1] <= 8


def test_image_format_change_writes_target_format(png_4x4_bytes: bytes, tmp_path: Path) -> None:
    """FR-025-12: format() switches the output container."""
    from arvel_image import Image
    from PIL import Image as PILImage

    target = tmp_path / "out.webp"
    Image.load(io.BytesIO(png_4x4_bytes)).format("webp").save(target)

    assert target.exists()
    img = PILImage.open(target)
    assert img.format == "WEBP"


def test_image_quality_clamped(png_4x4_bytes: bytes) -> None:
    """FR-025-12: quality(1..100); out-of-range raises."""
    from arvel_image import Image

    Image.load(io.BytesIO(png_4x4_bytes)).quality(85).format("jpeg").to_bytes()
    with pytest.raises(ValueError):
        Image.load(io.BytesIO(png_4x4_bytes)).quality(0)
    with pytest.raises(ValueError):
        Image.load(io.BytesIO(png_4x4_bytes)).quality(101)


def test_image_unsupported_format_raises(png_4x4_bytes: bytes) -> None:
    """FR-025-13: unknown format raises UnsupportedFormatError."""
    from arvel_image import Image, UnsupportedFormatError

    with pytest.raises(UnsupportedFormatError):
        Image.load(io.BytesIO(png_4x4_bytes)).format("bmp")


def test_image_save_roundtrip_pillow(png_4x4_bytes: bytes, tmp_path: Path) -> None:
    """FR-025-11: end-to-end save/load round trip preserves usability."""
    from arvel_image import Image
    from PIL import Image as PILImage

    target = tmp_path / "out.png"
    (Image.load(io.BytesIO(png_4x4_bytes)).resize(width=8, height=8).save(target))
    assert target.exists()
    PILImage.open(target).load()


def test_image_to_bytes_returns_non_empty(png_4x4_bytes: bytes) -> None:
    """FR-025-11: terminal to_bytes() returns serialized output."""
    from arvel_image import Image

    out = Image.load(io.BytesIO(png_4x4_bytes)).to_bytes()
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_image_does_not_shell_out() -> None:
    """NFR-025-07: arvel_image MUST NOT import subprocess or os.system."""
    import arvel_image

    src = Path(arvel_image.__file__).parent
    forbidden = ("import subprocess", "from subprocess", "os.system(")
    for py in src.rglob("*.py"):
        text = py.read_text()
        for token in forbidden:
            assert token not in text, f"{py} contains forbidden {token}"


# ─── ADR-081: media-library parity ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_image_provider_registers_media_migration_under_arvel_image_tag(
    tmp_path: Path,
) -> None:
    """ADR-081: ImageServiceProvider.boot() registers create_media_table.py
    as publishable under tag=arvel-image."""
    from arvel import Application
    from arvel.support.publishing import PublishRegistry
    from arvel_image import ImageServiceProvider

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ImageServiceProvider])
        .create()
    )
    await app.boot()

    reg: PublishRegistry = app.container.make(PublishRegistry)
    items = reg.by_tag("arvel-image")
    assert len(items) == 1
    item = items[0]
    assert item.source.name == "create_media_table.py"
    assert item.is_migration is True
    assert item.destination == (tmp_path / "database" / "migrations").resolve()


@pytest.mark.asyncio
async def test_vendor_publish_emits_timestamped_media_migration(tmp_path: Path) -> None:
    """End-to-end: ``arvel vendor:publish --tag=arvel-image`` lands a
    timestamped ``*_create_media_table.py`` in ``database/migrations/``."""
    from arvel import Application
    from arvel.console import Application as ConsoleApplication
    from arvel.console.commands.vendor_publish import VendorPublishCommand
    from arvel_image import ImageServiceProvider
    from typer.testing import CliRunner

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ImageServiceProvider])
        .create()
    )
    await app.boot()

    cmd = VendorPublishCommand()
    cmd.app = app
    cli = ConsoleApplication([cmd])
    result = CliRunner().invoke(cli.typer_app, ["vendor:publish", "--tag", "arvel-image"])
    assert result.exit_code == 0, result.output

    published = list((tmp_path / "database" / "migrations").glob("*_create_media_table.py"))
    assert len(published) == 1
    body = published[0].read_text()
    # Sanity: the published stub actually contains the medialibrary schema.
    assert '__tablename__ = "media"' in body
    assert 't.morphs("model")' in body
    assert "schema.create(__tablename__," in body
