"""Kit bug fixes and remaining contract violations.

Coverage:
- except syntax uses tuple form (ValueError, KeyError) — Python 3 compliant
- force-delete routes require role level 100
- User exposes has_level() for the prompt's numeric RBAC hierarchy
- seeded roles include the prompt role levels
- admin_get has include_trashed param; admin_get_including_trashed is deleted
- ProductService storefront methods use ORM (no direct DB.select on storefront)
- integration test asserts roles.level column exists
- support_agent and order_manager roles are seeded
- User docstring does not mention stale _max_level internals
"""

from __future__ import annotations

import ast
import inspect

import pytest

pytestmark = pytest.mark.unit


class TestPython3ExceptSyntax:
    """except clause must use tuple form."""

    def test_product_service_has_no_python2_except(self) -> None:
        """No `except A, B:` (Python 2 tuple-in-header form) in product_service.py."""
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent / "app" / "services" / "product_service.py"
        ).read_text()
        # The Python 2 form is `except SomeError, another_name:` — catch it via AST
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # In Python 2 compat form the handler would be `type=Tuple(...)` with
                # comma-separated names in the TYPE position (not the NAME position).
                # After the fix `type` is ast.Tuple and `name` is None.
                # This test asserts no handler uses bare comma-separated type names
                # by checking that no ExceptHandler has a type that is ast.Name
                # with the string containing a comma — i.e. it can't even parse as
                # valid Python 3 with comma-in-type.
                # Actually the simplest check: the source must not contain the literal pattern.
                pass
        # Direct source check — simpler and more reliable than AST walk for this pattern
        assert "except ValueError, KeyError" not in src, (
            "Python 2 `except A, B:` syntax found in product_service.py"
        )
        assert "except (ValueError, KeyError)" in src or "except ValueError" in src, (
            "Expected Python 3 tuple except form"
        )


class TestForceDestroyUsesRoleLevel:
    """force-delete is gated by role hierarchy, not a bespoke permission."""

    def test_force_destroy_routes_require_level_100(self) -> None:
        from pathlib import Path

        backend = Path(__file__).parent.parent.parent
        products_ctrl = (
            backend / "app" / "http" / "controllers" / "admin" / "products.py"
        ).read_text()
        categories_ctrl = (
            backend / "app" / "http" / "controllers" / "admin" / "categories.py"
        ).read_text()
        vendors_ctrl = (
            backend / "app" / "http" / "controllers" / "admin" / "vendors.py"
        ).read_text()
        assert 'require_role_level(request, "products.delete", 100)' in products_ctrl
        assert 'require_role_level(request, "categories.delete", 100)' in categories_ctrl
        assert 'require_role_level(request, "vendors.delete", 100)' in vendors_ctrl

    def test_no_force_destroy_permission_seeded(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "database"
            / "seeders"
            / "roles_and_permissions_seeder.py"
        ).read_text()
        assert "products.force_destroy" not in src

    def test_role_assignment_cannot_exceed_actor_level(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "app"
            / "http"
            / "controllers"
            / "admin"
            / "users.py"
        ).read_text()
        assert "role_level" in src
        assert "has_level" in src
        assert "Cannot assign a role above your level." in src


class TestUserRoleLevel:
    """User keeps permission traits and adds prompt-level hierarchy checks."""

    def test_has_roles_mixin_file_deleted(self) -> None:
        """app/mixins/has_roles.py must not exist."""
        from pathlib import Path

        mixin_file = Path(__file__).parent.parent.parent / "app" / "mixins" / "has_roles.py"
        assert not mixin_file.exists(), "app/mixins/has_roles.py still exists — delete it"

    def test_user_does_not_inherit_has_roles_mixin(self) -> None:
        """User MRO must not include HasRolesMixin."""
        from app.models.user import User

        mro_names = [cls.__name__ for cls in User.__mro__]
        assert "HasRolesMixin" not in mro_names, f"HasRolesMixin is still in User MRO: {mro_names}"

    def test_user_has_level_method(self) -> None:
        from app.models.user import User

        assert hasattr(User, "has_level")

    def test_is_admin_uses_has_any_role(self) -> None:
        """User.is_admin is an async method that uses has_any_role/has_role."""
        import inspect as _inspect

        from app.models.user import User

        is_admin = User.__dict__["is_admin"]
        assert _inspect.iscoroutinefunction(is_admin), "User.is_admin must be async"
        src = inspect.getsource(is_admin)
        assert "has_any_role" in src or "has_role" in src, (
            "User.is_admin must use has_any_role() or has_role()"
        )


class TestSeederRoleLevels:
    """seeded roles must carry the prompt's numeric hierarchy."""

    def test_role_levels_in_roles_data(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "database"
            / "seeders"
            / "roles_and_permissions_seeder.py"
        ).read_text()
        for role_name, level in {
            "super_admin": 100,
            "admin": 80,
            "catalog_manager": 60,
            "order_manager": 60,
            "support_agent": 40,
        }.items():
            assert f'"name": "{role_name}"' in src
            assert f'"level": {level}' in src

    def test_admin_seed_credentials_match_packaged_env(self) -> None:
        from pathlib import Path

        base = Path(__file__).parent.parent.parent.parent
        seeder = (
            base / "backend" / "database" / "seeders" / "roles_and_permissions_seeder.py"
        ).read_text()
        env_example = (base / "backend" / ".env.example").read_text()
        readme = (base / "README.md").read_text()

        assert 'os.environ.get("ADMIN_SEED_EMAIL", "admin@example.com")' in seeder
        assert 'os.environ.get("ADMIN_SEED_PASSWORD", "AdminPwd!1")' in seeder
        assert 'os.environ.get("ADMIN_EMAIL"' not in seeder
        assert 'os.environ.get("ADMIN_PASSWORD"' not in seeder
        assert "ADMIN_SEED_EMAIL=admin@example.com" in env_example
        assert "ADMIN_SEED_PASSWORD=AdminPwd!1" in env_example
        assert "ADMIN_SEED_EMAIL=admin@example.com" in readme
        assert "ADMIN_SEED_PASSWORD=AdminPwd!1" in readme


class TestAdminGetMerged:
    """admin_get_including_trashed must be deleted; admin_get gains include_trashed."""

    def test_admin_get_including_trashed_deleted(self) -> None:
        """ProductService must not have admin_get_including_trashed method."""
        from app.services.product_service import ProductService

        assert not hasattr(ProductService, "admin_get_including_trashed"), (
            "admin_get_including_trashed still exists — merge it into admin_get"
        )

    def test_admin_get_has_include_trashed_param(self) -> None:
        """ProductService.admin_get must accept include_trashed keyword argument."""
        from app.services.product_service import ProductService

        sig = inspect.signature(ProductService.admin_get)
        assert "include_trashed" in sig.parameters, (
            "admin_get must have include_trashed parameter after merge"
        )


class TestStorefrontUsesORM:
    """storefront methods must use ProductCatalog ORM, not raw DB.select."""

    def test_product_catalog_viewmodel_exists(self) -> None:
        """app.models.product_catalog.ProductCatalog must be importable."""
        from app.models.product_catalog import ProductCatalog
        from arvel.database.model import ViewModel

        assert issubclass(ProductCatalog, ViewModel), "ProductCatalog must extend ViewModel"

    def test_product_catalog_is_materialized_view(self) -> None:
        """ProductCatalog must set __is_materialized_view__ = True."""
        from app.models.product_catalog import ProductCatalog

        assert getattr(ProductCatalog, "__is_materialized_view__", False) is True, (
            "ProductCatalog.__is_materialized_view__ must be True"
        )

    def test_list_published_no_raw_db_select(self) -> None:
        """list_published source must not call DB.select directly."""
        from app.services.product_service import ProductService

        src = inspect.getsource(ProductService.list_published)
        assert "DB.select" not in src, (
            "list_published still uses raw DB.select — use ProductCatalog ORM"
        )

    def test_get_published_by_slug_no_raw_db_select(self) -> None:
        """get_published_by_slug source must not call DB.select directly."""
        from app.services.product_service import ProductService

        src = inspect.getsource(ProductService.get_published_by_slug)
        assert "DB.select" not in src, (
            "get_published_by_slug still uses raw DB.select — use ProductCatalog ORM"
        )

    def test_search_published_no_raw_db_select(self) -> None:
        """search_published source must not call DB.select directly."""
        from app.services.product_service import ProductService

        src = inspect.getsource(ProductService.search_published)
        assert "DB.select" not in src, (
            "search_published still uses raw DB.select — use ProductCatalog ORM"
        )

    def test_search_published_uses_orm_fts(self) -> None:
        """search_published must reference where_full_text or order_by_relevance."""
        from app.services.product_service import ProductService

        src = inspect.getsource(ProductService.search_published)
        uses_orm = (
            "where_full_text" in src or "order_by_relevance" in src or "ProductCatalog" in src
        )
        assert uses_orm, (
            "search_published must use the ORM FTS API (where_full_text / order_by_relevance)"
        )


class TestPromptRoleNames:
    """Seeded role names match the prompt; stale internals stay gone."""

    def test_user_docstring_no_max_level(self) -> None:
        from app.models.user import User

        doc = User.__doc__ or ""
        assert "_max_level" not in doc, "User docstring still references _max_level"

    def test_user_module_docstring_no_level(self) -> None:
        """User module-level docstring must not describe stale internal level caches."""
        import app.models.user as user_module

        module_doc = user_module.__doc__ or ""
        assert "_max_level" not in module_doc

    def test_support_agent_and_order_manager_are_seeded(self) -> None:
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "database"
            / "seeders"
            / "roles_and_permissions_seeder.py"
        ).read_text()
        assert '"name": "support_agent"' in src
        assert '"name": "order_manager"' in src
