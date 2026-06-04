"""Prompt media contract tests for product images."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
ROUTES_FILE = BASE_DIR / "routes" / "api.py"
ADMIN_PRODUCTS_CTRL = BASE_DIR / "app" / "http" / "controllers" / "admin" / "products.py"
MEDIA_SERVICE = BASE_DIR / "app" / "services" / "media_service.py"
MEDIA_MODEL = BASE_DIR / "app" / "models" / "media.py"
MEDIA_MIGRATION = BASE_DIR / "database" / "migrations" / "2026_05_23_000011_create_media_table.py"
IMAGE_CONFIG = BASE_DIR / "config" / "image.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_media_table_matches_prompt_shape() -> None:
    src = _src(MEDIA_MIGRATION)

    for column in (
        't.string("model_type")',
        't.string("model_id", length=36)',
        't.string("collection_name")',
        't.string("disk")',
        't.string("file_name")',
        't.string("mime_type")',
        't.big_integer("size", unsigned=True)',
        't.jsonb("metadata")',
        't.datetime("deleted_at")',
    ):
        assert column in src
    assert 't.index(["model_type", "model_id"], name="media_model_type_model_id_index")' in src


def test_kit_media_model_uses_arvel_image_media() -> None:
    src = _src(MEDIA_MODEL)

    assert "from arvel_image import Media" in src


def test_media_service_persists_images_and_serializes_conversions() -> None:
    src = _src(MEDIA_SERVICE)

    # Kit delegates ingestion to HasMedia.add_image (the model's __media_collection__
    # is the default — no hard-coded collection name).
    assert "product.add_image(contents, file_name=filename)" in src
    # Media.to_dict() is the single source of truth for the serialized payload —
    # the kit doesn't reach into generated_conversions / responsive_images by hand.
    assert "media.to_dict()" in src
    assert "generated_conversions" not in src
    assert "responsive_images" not in src


def test_image_config_matches_runtime_conversion_runner() -> None:
    src = _src(IMAGE_CONFIG)

    # Disk comes from config.filesystems.default — single source of truth.
    assert "import config.filesystems as fs_cfg" in src
    assert "fs_cfg.default" in src
    assert '"thumbnail"' in src
    assert '"card"' in src
    assert '"full"' in src
    assert "RabbitMQ" not in src
    assert "conversions_queue" not in src


def test_admin_media_routes_bind_to_controller() -> None:
    # routes/api.py is routing-only: media upload/list/delete are bound to the
    # admin products controller, which owns permission checks and handler logic.
    src = _src(ROUTES_FILE)

    assert '"/{product_id}/media"' in src
    assert '"/{product_id}/media/{media_id}"' in src
    assert 'action="media_store"' in src
    assert 'action="media_index"' in src
    assert 'action="media_destroy"' in src


def test_admin_products_controller_owns_media_handlers() -> None:
    src = _src(ADMIN_PRODUCTS_CTRL)

    assert "await attach_product_image(product, file)" in src
    assert "list_product_images(product)" in src
    assert "await delete_product_image(product, media_id)" in src
