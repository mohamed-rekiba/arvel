"""Prompt media contract tests for product images."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
ROUTES_FILE = BASE_DIR / "routes" / "api.py"
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
        'Column("metadata", JSONB',
        't.datetime("deleted_at")',
    ):
        assert column in src
    assert 't.index(["model_type", "model_id"], name="media_model_type_model_id_index")' in src


def test_demo_media_model_uses_arvel_image_media() -> None:
    src = _src(MEDIA_MODEL)

    assert "from arvel_image import Media" in src


def test_media_service_persists_images_and_serializes_conversions() -> None:
    src = _src(MEDIA_SERVICE)

    assert "product.add_media(contents, file_name=filename).to_media_collection" in src
    assert '"thumbnail"' in src
    assert '"card"' in src
    assert '"full"' in src
    assert '"responsive_images": media.responsive_images or {}' in src


def test_image_config_matches_runtime_conversion_runner() -> None:
    src = _src(IMAGE_CONFIG)

    assert 'env("STORAGE_DEFAULT", "local")' in src
    assert '"thumbnail"' in src
    assert '"card"' in src
    assert '"full"' in src
    assert "RabbitMQ" not in src
    assert "conversions_queue" not in src


def test_admin_media_routes_cover_upload_list_and_delete() -> None:
    src = _src(ROUTES_FILE)

    assert '@Route.post(\n    "/api/admin/products/{product_id}/media"' in src
    assert '@Route.get(\n    "/api/admin/products/{product_id}/media"' in src
    assert '@Route.delete(\n    "/api/admin/products/{product_id}/media/{media_id}"' in src
    assert "await attach_product_image(product, file)" in src
    assert "await list_product_images(product)" in src
    assert "await delete_product_image(product, media_id)" in src
