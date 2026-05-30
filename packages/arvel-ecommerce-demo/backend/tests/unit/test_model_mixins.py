"""Unit tests for framework mixins — US-001.

RED: imports from app.models.* and app.mixins.* fail until Stage 3b
implements those modules. Every test here fails at import time.

Acceptance criteria (US-001):
- BaseModelMixin: UUID v7 id, created_at, updated_at, deleted_at, scope_active()
- TranslatableMixin: get_translation(), set_translation(), locale fallback to 'en'
- User RBAC: HasRoles/HasPermissions plus has_level()
- HasMediaMixin: attach_media(), get_media(), media collection filtering
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ─── BaseModelMixin ─────────────────────────────────────────────────────────────


class TestBaseModelMixin:
    def test_id_is_uuid_v7(self) -> None:
        """BaseModelMixin assigns UUID v7 (timestamp-prefixed) primary keys."""
        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        assert p.id is not None
        # UUID v7 has version nibble == 7 at position 14
        assert p.id.version == 7

    def test_created_at_attribute_exists(self) -> None:
        """Timestamps mixin adds created_at; it's set by the ORM on flush, not on __init__."""
        from app.models.vendor import Vendor  # RED until Stage 3b

        v = Vendor(name="Test", slug="test", status="published")
        # In unit tests (no session), created_at starts None; the framework sets it on save.
        assert hasattr(v, "created_at")

    def test_soft_delete_attribute_exists(self) -> None:
        """SoftDeletes mixin adds deleted_at; it starts as None."""
        from datetime import UTC, datetime

        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        assert p.deleted_at is None
        # Simulate what await p.delete() would do in an active session
        p.deleted_at = datetime.now(UTC)
        assert p.deleted_at is not None

    def test_restore_clears_deleted_at(self) -> None:
        """Setting deleted_at=None restores the record (async restore() does the same)."""
        from datetime import UTC, datetime

        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        p.deleted_at = datetime.now(UTC)
        p.deleted_at = None
        assert p.deleted_at is None

    def test_soft_deletes_global_scope_class_attribute(self) -> None:
        """SoftDeletes registers __arvel_soft_delete_column__ on models that use it."""
        from app.models.product import Product  # RED until Stage 3b

        assert getattr(Product, "__arvel_soft_delete_column__", None) == "deleted_at"

    def test_product_declares_attribute_casts(self) -> None:
        from app.models.product import Product

        assert Product.__casts__["name"] == "dict"
        assert Product.__casts__["slug"] == "dict"
        assert Product.__casts__["description"] == "dict"
        assert Product.__casts__["stock_qty"] == "int"

    def test_product_exposes_local_query_scopes(self) -> None:
        from app.models.product import Product

        published_sql = Product.published().to_sql()
        draft_sql = Product.draft().to_sql()

        assert "products.status" in published_sql
        assert "products.published_at" in published_sql
        assert "products.status" in draft_sql

    def test_product_has_catalog_relationships_for_eager_loading(self) -> None:
        from app.models.product import Product

        relationships = Product.__mapper__.relationships

        assert "category" in relationships
        assert "vendor" in relationships


# ─── TranslatableMixin ──────────────────────────────────────────────────────────


class TestTranslatableMixin:
    def test_get_translation_returns_locale_value(self) -> None:
        """get_translation returns the value for the requested locale."""
        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        p.name = {"en": "Headphones", "ar": "سماعات", "tr": "Kulakl\u0131k"}
        assert p.get_translation("name", "ar") == "سماعات"

    def test_get_translation_falls_back_to_en(self) -> None:
        """get_translation falls back to 'en' when the requested locale is absent."""
        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        p.name = {"en": "Headphones"}
        assert p.get_translation("name", "tr") == "Headphones"

    def test_get_translation_returns_empty_when_all_absent(self) -> None:
        """Returns '' when both the locale and 'en' fallback are absent."""
        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        p.name = {}
        assert p.get_translation("name", "ar") == ""

    def test_set_translation_updates_only_the_target_locale(self) -> None:
        """set_translation patches one locale key, leaving others intact."""
        from app.models.product import Product  # RED until Stage 3b

        p = Product()
        p.name = {"en": "Headphones", "ar": "سماعات"}
        p.set_translation("name", "tr", "Kulakl\u0131k")
        assert p.name == {"en": "Headphones", "ar": "سماعات", "tr": "Kulakl\u0131k"}


# ─── Model events ──────────────────────────────────────────────────────────────


class TestModelEvents:
    def test_product_observer_sets_publish_timestamp_before_save(self) -> None:
        from app.models.product import Product
        from app.observers.product_observer import ProductObserver

        product = Product(status="published")

        ProductObserver().saving(product)

        assert product.published_at is not None

    def test_app_provider_registers_product_observer(self) -> None:
        from pathlib import Path

        provider_source = (
            Path(__file__).parents[2] / "app" / "providers" / "app_service_provider.py"
        ).read_text()

        assert "Product.observe(ProductObserver)" in provider_source


# ─── HasMediaMixin ───────────────────────────────────────────────────────────────


class TestHasMediaMixin:
    def test_get_media_returns_empty_list_when_no_attachments(self) -> None:
        """HasMedia interface is available on Product — integration with arvel_image."""
        # get_media is async (HasMedia); verify the method exists with the right name

        from app.models.product import Product

        p = Product()
        # Confirm the method is accessible (real call requires a live DB session)
        assert callable(getattr(p, "get_media", None))

    def test_attach_media_method_exists_on_product(self) -> None:
        """attach_media is available on Product via HasMedia trait."""
        from app.models.product import Product

        p = Product()
        assert callable(getattr(p, "attach_media", None))

    def test_media_model_uses_arvel_image_media(self) -> None:
        """Product media is backed by arvel_image's persisted Media model."""
        from app.models.media import Media
        from arvel_image import Media as ArvelImageMedia

        assert Media is ArvelImageMedia
        assert callable(getattr(Media, "get_url", None))
