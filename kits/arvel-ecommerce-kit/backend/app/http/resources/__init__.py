"""HTTP resource transformers — JsonResource subclasses for API response shaping."""

from __future__ import annotations

from app.http.resources.category_resource import CategoryResource
from app.http.resources.product_resource import ProductResource

__all__ = ["CategoryResource", "ProductResource"]
