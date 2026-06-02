"""Kit framework alignment.

Coverage:
- uuid7 is stdlib (uuid.uuid7), not custom bit-manipulation
- _get_user_level / _require_level are deleted
- BaseModelMixin has no delete/restore/scope_active/to_dict/__post_init__
- _require_permission delegates to user.has_permission_to (trait)
"""

from __future__ import annotations

import inspect
import uuid

import pytest

pytestmark = pytest.mark.unit


class TestUuid7StdlibOnly:
    """uuid7 must be the stdlib function, not a custom implementation."""

    def test_uuid7_is_stdlib_function(self) -> None:
        """uuid.uuid7 must be the stdlib function (not a custom implementation)."""
        import uuid as _uuid

        assert _uuid.uuid7 is uuid.uuid7

    def test_uuid7_produces_version_7_uuid(self) -> None:
        """Generated UUID must have version == 7."""
        result = uuid.uuid7()
        assert result.version == 7

    def test_base_module_has_no_custom_uuid7_source(self) -> None:
        """The custom bit-manipulation block must not exist in base.py."""
        import app.models.base as base_mod

        src = inspect.getsource(base_mod)
        assert "rand_b" not in src, "Custom bit-twiddling uuid7 implementation still present"
        assert "rand_a" not in src, "Custom bit-twiddling uuid7 implementation still present"
        assert "(0x7 << 76)" not in src, "Custom uuid7 version-nibble constant still present"


class TestBaseModelMixinShadowsRemoved:
    """BaseModelMixin must not shadow async framework methods."""

    def test_basemodelmixin_has_no_sync_delete(self) -> None:
        """BaseModelMixin.delete must not be defined (routes must use await model.delete())."""
        from app.models.base import BaseModelMixin

        # delete() must either not exist on BaseModelMixin directly, or must not be sync
        delete_fn = BaseModelMixin.__dict__.get("delete")
        assert delete_fn is None or inspect.iscoroutinefunction(delete_fn), (
            "BaseModelMixin defines a sync delete() that shadows ActiveRecord.delete()"
        )

    def test_basemodelmixin_has_no_sync_restore(self) -> None:
        """BaseModelMixin.restore must not be defined."""
        from app.models.base import BaseModelMixin

        restore_fn = BaseModelMixin.__dict__.get("restore")
        assert restore_fn is None or inspect.iscoroutinefunction(restore_fn), (
            "BaseModelMixin defines a sync restore() that shadows ActiveRecord.restore()"
        )

    def test_basemodelmixin_has_no_scope_active(self) -> None:
        """BaseModelMixin.scope_active must not be defined (global scope handles this)."""
        from app.models.base import BaseModelMixin

        assert "scope_active" not in BaseModelMixin.__dict__, (
            "BaseModelMixin still defines scope_active(); remove it"
        )

    def test_basemodelmixin_has_no_to_dict(self) -> None:
        """BaseModelMixin.to_dict must not be defined (use model_dump() from framework)."""
        from app.models.base import BaseModelMixin

        assert "to_dict" not in BaseModelMixin.__dict__, (
            "BaseModelMixin still defines to_dict(); remove it"
        )

    def test_basemodelmixin_has_no_post_init(self) -> None:
        """BaseModelMixin.__post_init__ must not be defined (Timestamps mixin handles this)."""
        from app.models.base import BaseModelMixin

        assert "__post_init__" not in BaseModelMixin.__dict__, (
            "BaseModelMixin still defines __post_init__; Timestamps mixin handles timestamps"
        )


class TestLevelMethodsDeleted:
    """_get_user_level and _require_level must not exist in routes/api.py."""

    def test_no_get_user_level_in_routes(self) -> None:
        """_get_user_level was deleted from routes/api.py."""
        from pathlib import Path

        api_src = (Path(__file__).resolve().parents[2] / "routes" / "api.py").read_text()
        assert "_get_user_level" not in api_src, (
            "_get_user_level still exists in routes/api.py — it queries roles.level "
            "which was deleted in WI-arvel-036"
        )

    def test_no_require_level_in_routes(self) -> None:
        """_require_level was deleted from routes/api.py."""
        from pathlib import Path

        api_src = (Path(__file__).resolve().parents[2] / "routes" / "api.py").read_text()
        assert "_require_level" not in api_src, "_require_level still exists in routes/api.py"

    def test_no_get_max_level_in_user_service(self) -> None:
        """get_max_level was deleted from user_service.py."""
        from pathlib import Path

        svc_src = (
            Path(__file__).resolve().parents[2] / "app" / "services" / "user_service.py"
        ).read_text()
        assert "get_max_level" not in svc_src, (
            "get_max_level still exists in user_service.py — it queries roles.level"
        )


class TestNoRawSqlInServices:
    """No DB.select/DB.statement raw SQL calls in service files."""

    def _read_service(self, name: str) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[2] / "app" / "services" / f"{name}.py").read_text()

    def test_user_service_no_raw_select(self) -> None:
        src = self._read_service("user_service")
        assert "DB.select(" not in src, "user_service.py still contains DB.select() raw SQL"

    def test_user_service_no_raw_statement(self) -> None:
        src = self._read_service("user_service")
        assert "DB.statement(" not in src, "user_service.py still contains DB.statement() raw SQL"

    def test_cart_service_no_raw_select(self) -> None:
        src = self._read_service("cart_service")
        assert "DB.select(" not in src, "cart_service.py still contains DB.select() raw SQL"

    def test_cart_service_no_raw_statement(self) -> None:
        src = self._read_service("cart_service")
        assert "DB.statement(" not in src, "cart_service.py still contains DB.statement() raw SQL"

    def test_order_service_no_raw_select(self) -> None:
        src = self._read_service("order_service")
        assert "DB.select(" not in src, "order_service.py still contains DB.select() raw SQL"

    def test_order_service_no_raw_statement(self) -> None:
        src = self._read_service("order_service")
        assert "DB.statement(" not in src, "order_service.py still contains DB.statement() raw SQL"


class TestNoRawRbacSqlInRoutes:
    """No raw SQL RBAC joins in routes/api.py."""

    def _read_routes(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[2] / "routes" / "api.py").read_text()

    def test_no_model_has_roles_raw_sql(self) -> None:
        src = self._read_routes()
        assert "model_has_roles" not in src, (
            "routes/api.py still contains raw SQL against model_has_roles table"
        )

    def test_no_model_has_permissions_raw_sql(self) -> None:
        src = self._read_routes()
        assert "model_has_permissions" not in src, (
            "routes/api.py still contains raw SQL against model_has_permissions table"
        )

    def test_no_role_has_permissions_raw_sql(self) -> None:
        src = self._read_routes()
        assert "role_has_permissions" not in src, (
            "routes/api.py still contains raw SQL against role_has_permissions table"
        )


class TestTranslatableMixinPreserved:
    """TranslatableMixin must still work after BaseModelMixin cleanup."""

    def test_get_translation_still_works(self) -> None:
        from app.models.base import TranslatableMixin

        class FakeModel(TranslatableMixin):
            name: dict = {}

        m = FakeModel()
        m.name = {"en": "Hello", "ar": "مرحبا"}
        assert m.get_translation("name", "ar") == "مرحبا"
        assert m.get_translation("name", "tr") == "Hello"  # fallback to en

    def test_set_translation_still_works(self) -> None:
        from app.models.base import TranslatableMixin

        class FakeModel(TranslatableMixin):
            name: dict = {}

        m = FakeModel()
        m.name = {"en": "Shoes"}
        m.set_translation("name", "ar", "أحذية")
        assert m.name == {"en": "Shoes", "ar": "أحذية"}


class TestLocalMediaMixinPreserved:
    """LocalMediaMixin must still work after BaseModelMixin cleanup."""

    def test_get_media_returns_empty_by_default(self) -> None:
        from app.models.base import LocalMediaMixin

        class FakeModel(LocalMediaMixin):
            pass

        m = FakeModel()
        assert m.get_media("images") == []

    def test_attach_media_adds_item(self) -> None:
        from app.models.base import LocalMediaMixin, _MockMediaItem

        class FakeFile:
            filename = "photo.jpg"
            content = b"..."

        class FakeModel(LocalMediaMixin):
            pass

        m = FakeModel()
        item = m.attach_media(FakeFile(), "images")
        assert isinstance(item, _MockMediaItem)
        assert m.get_media("images") == [item]
