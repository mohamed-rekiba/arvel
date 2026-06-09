"""Catalog / storefront tunables."""

from __future__ import annotations

from arvel.support.env import env as _env

# A product wears the "new" badge for this many days after it's created.
new_product_days: int = _env("CATALOG_NEW_PRODUCT_DAYS", 30)

# Storefront search ignores queries shorter than this (DB full-text needs a stem).
search_min_length: int = _env("CATALOG_SEARCH_MIN_LENGTH", 2)
