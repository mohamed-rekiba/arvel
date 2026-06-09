"""is_new is a real recency flag, not a hardcoded badge.

The logic lives on the ProductCatalog.is_new accessor — a product is "new" only
while it's within catalog.new_product_days of created_at. Exercised through the
accessor's getter directly, so no DB / docker and no config load is needed
(config() falls back to the 30-day default).
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _is_new(created_at: datetime | None) -> bool:
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    sys.modules.pop("config", None)
    model = importlib.import_module("app.models.product_catalog")
    getter = model.ProductCatalog.is_new.fget
    return bool(getter(SimpleNamespace(created_at=created_at)))


def test_recent_product_is_new() -> None:
    assert _is_new(datetime.now(UTC) - timedelta(days=1)) is True


def test_old_product_is_not_new() -> None:
    assert _is_new(datetime.now(UTC) - timedelta(days=90)) is False


def test_naive_created_at_is_handled() -> None:
    assert _is_new(datetime.now(UTC).replace(tzinfo=None)) is True


def test_missing_created_at_is_not_new() -> None:
    assert _is_new(None) is False


def _cart_item_subtotal(unit_price: Any, quantity: Any) -> float:
    backend = Path(__file__).resolve().parents[2]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    model = importlib.import_module("app.models.cart_item")
    getter = model.CartItem.subtotal.fget
    return float(getter(SimpleNamespace(unit_price_snapshot=unit_price, quantity=quantity)))


def test_cart_item_subtotal_multiplies_snapshot_by_quantity() -> None:
    assert _cart_item_subtotal(9.99, 3) == 29.97


def test_cart_item_subtotal_handles_zero_quantity() -> None:
    assert _cart_item_subtotal(9.99, 0) == 0.0
