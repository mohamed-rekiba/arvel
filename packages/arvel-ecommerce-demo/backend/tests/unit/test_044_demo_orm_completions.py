"""QA-Pre tests for WI-arvel-044 demo fixes.

Verifies that demo checkout uses lock_for_update() and product_service
uses where_json_path() instead of where_raw for JSONB slug queries.
"""

from __future__ import annotations

from pathlib import Path

_DEMO = Path(__file__).parents[2]

_ORDER_SERVICE = _DEMO / "app/services/order_service.py"
_PRODUCT_SERVICE = _DEMO / "app/services/product_service.py"


def _src(path: Path) -> str:
    return path.read_text()


# ── FR-007: Demo checkout uses lock_for_update() (F-020) ───────────────────────


class TestCheckoutUsesLockForUpdate:
    """AC-007a/b: checkout() must use lock_for_update() and remove gap comment."""

    def test_checkout_calls_lock_for_update(self) -> None:
        """checkout() must use lock_for_update() to prevent TOCTOU race."""
        src = _src(_ORDER_SERVICE)
        assert "lock_for_update()" in src, (
            "F-020: order_service.checkout() must call lock_for_update() "
            "before reading product stock. WI-043 fixed the ORM; remove the gap workaround."
        )

    def test_checkout_gap_comment_removed(self) -> None:
        """Framework gap G-003 comment must be removed after the fix."""
        src = _src(_ORDER_SERVICE)
        assert "G-003" not in src, (
            "F-020: Gap comment G-003 must be removed from order_service.py "
            "since WI-043 closed the underlying ORM gap."
        )


# ── FR-008: Demo JSONB queries use where_json_path() (F-025) ───────────────────


class TestProductServiceUsesWhereJsonPath:
    """AC-008a/b/c: product_service.py must use where_json_path(), not where_raw."""

    def test_no_where_raw_for_slug(self) -> None:
        """JSONB slug queries must use where_json_path(), not where_raw."""
        src = _src(_PRODUCT_SERVICE)
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            if "where_raw" in line and "slug->>'en'" in line:
                raise AssertionError(
                    f"F-025: product_service.py line {i} uses where_raw for slug. "
                    "Replace with where_json_path('slug', 'en', value)."
                )

    def test_no_gap_g001_comments(self) -> None:
        """All G-001 gap comments must be removed after where_json_path() migration."""
        src = _src(_PRODUCT_SERVICE)
        assert "G-001" not in src, (
            "F-025: Gap comment G-001 must be removed from product_service.py "
            "since WI-043 added where_json_path() to the framework."
        )

    def test_uses_where_json_path(self) -> None:
        """product_service.py must call where_json_path() for slug lookups."""
        src = _src(_PRODUCT_SERVICE)
        assert "where_json_path" in src, (
            "F-025: product_service.py must use where_json_path() for JSONB slug queries."
        )
