"""Kit ORM completions — checkout locking and JSONB slug queries.

Verifies that kit checkout uses lock_for_update() and product_service
uses where_json_path() instead of where_raw for JSONB slug queries.
"""

from __future__ import annotations

from pathlib import Path

_KIT = Path(__file__).parents[2]

_ORDER_SERVICE = _KIT / "app/services/order_service.py"
_PRODUCT_SERVICE = _KIT / "app/services/product_service.py"


def _src(path: Path) -> str:
    return path.read_text()


# ── Kit checkout uses lock_for_update() ────────────────────────────────


class TestCheckoutUsesLockForUpdate:
    """checkout() must use lock_for_update() and remove gap comment."""

    def test_checkout_calls_lock_for_update(self) -> None:
        """checkout() must use lock_for_update() to prevent TOCTOU race."""
        src = _src(_ORDER_SERVICE)
        assert "lock_for_update()" in src, (
            "order_service.checkout() must call lock_for_update() "
            "before reading product stock. Remove the gap workaround."
        )

    def test_checkout_gap_comment_removed(self) -> None:
        """Stale gap comment must be removed from checkout after row locking shipped."""
        src = _src(_ORDER_SERVICE)
        assert "G-003" not in src, (
            "G-003 gap-marker must be removed from order_service.py "
            "now that the underlying ORM gap is closed."
        )


# ── Kit JSONB queries use where_json_path() ────────────────────────────


class TestProductServiceUsesWhereJsonPath:
    """product_service.py must use where_json_path(), not where_raw."""

    def test_no_where_raw_for_slug(self) -> None:
        """JSONB slug queries must use where_json_path(), not where_raw."""
        src = _src(_PRODUCT_SERVICE)
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            if "where_raw" in line and "slug->>'en'" in line:
                raise AssertionError(
                    f"product_service.py line {i} uses where_raw for slug. "
                    "Replace with where_json_path('slug', 'en', value)."
                )

    def test_no_gap_g001_comments(self) -> None:
        """Stale JSONB gap comments removed after where_json_path() migration."""
        src = _src(_PRODUCT_SERVICE)
        assert "G-001" not in src, (
            "G-001 gap-marker must be removed from product_service.py "
            "now that where_json_path() is available."
        )

    def test_uses_where_json_path(self) -> None:
        """product_service.py must call where_json_path() for slug lookups."""
        src = _src(_PRODUCT_SERVICE)
        assert "where_json_path" in src, (
            "product_service.py must use where_json_path() for JSONB slug queries."
        )
