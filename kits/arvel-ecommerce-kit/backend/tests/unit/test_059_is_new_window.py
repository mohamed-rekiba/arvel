"""is_new is a real recency flag, not a hardcoded badge.

product_to_storefront should mark a product "new" only while it's within the
recency window of its created_at. Behavioral test with a stub catalog row — no
DB / docker.
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast


def _product_service() -> Any:
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    sys.modules.pop("config", None)
    return importlib.import_module("app.services.product_service")


def _stub(created_at: datetime | None) -> Any:
    # Empty media skips the image branch; the rest are the fields the serializer reads.
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        media=[],
        name={"en": "Thing"},
        slug={"en": "thing"},
        description={"en": ""},
        category_name={},
        category_slug={},
        parent_category_name={},
        parent_category_slug={},
        price=10,
        stock_qty=5,
        category_id=None,
        category_parent_id=None,
        vendor_id=None,
        vendor_name="",
        vendor_slug="",
        created_at=created_at,
    )


def test_recent_product_is_new() -> None:
    svc = _product_service()
    row = _stub(datetime.now(UTC) - timedelta(days=1))
    result = svc.ProductService.product_to_storefront(cast("Any", row), "en")
    assert result["is_new"] is True


def test_old_product_is_not_new() -> None:
    svc = _product_service()
    row = _stub(datetime.now(UTC) - timedelta(days=90))
    result = svc.ProductService.product_to_storefront(cast("Any", row), "en")
    assert result["is_new"] is False


def test_naive_created_at_is_handled() -> None:
    svc = _product_service()
    row = _stub(datetime.now(UTC).replace(tzinfo=None))
    result = svc.ProductService.product_to_storefront(cast("Any", row), "en")
    assert result["is_new"] is True
