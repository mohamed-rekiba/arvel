"""Materialized-view refresh pipeline hardening."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
SUPPORT_FILE = BASE_DIR / "app" / "support" / "products_catalog.py"
BOOTSTRAP_FILE = BASE_DIR / "app" / "bootstrap.py"
PRODUCT_SERVICE_FILE = BASE_DIR / "app" / "services" / "product_service.py"
PROVIDERS_FILE = BASE_DIR / "bootstrap" / "providers.py"
KERNEL_FILE = BASE_DIR / "app" / "console" / "kernel.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_refresh_helper_uses_lock_and_runtime_refresh() -> None:
    src = _src(SUPPORT_FILE)
    assert "Cache.lock(_REFRESH_LOCK, ttl=_REFRESH_LOCK_TTL_SECONDS)" in src
    assert '_REFRESH_LOCK = "ecommerce:products-catalog:refresh"' in src
    assert "_REFRESH_LOCK_TTL_SECONDS = 600" in src
    assert "return -1" in src
    assert "refresh_products_catalog()" in src
    assert "ProductCatalog.refresh_view" not in src


def test_seed_bootstrap_uses_shared_refresh_helper() -> None:
    src = _src(BOOTSTRAP_FILE)
    assert "from app.support.products_catalog import refresh_products_catalog" in src
    assert "await refresh_products_catalog()" in src
    assert "ProductCatalog.refresh_view" not in src


def test_product_service_uses_shared_refresh_helper() -> None:
    src = _src(PRODUCT_SERVICE_FILE)
    assert "from app.support.products_catalog import refresh_products_catalog" in src
    assert "await refresh_products_catalog()" in src


def test_scheduler_provider_is_registered() -> None:
    src = _src(PROVIDERS_FILE)
    assert "SchedulerServiceProvider" in src
    assert "SchedulerServiceProvider," in src


def test_scheduler_refreshes_every_ten_minutes_without_overlap() -> None:
    src = _src(KERNEL_FILE)
    assert "schedule.call(refresh_products_catalog_schedule)" in src
    assert '.name("products-catalog.refresh")' in src
    assert ".everyTenMinutes()" in src
    assert ".withoutOverlapping(ttl_minutes=10)" in src
    assert ".onOneServer(ttl_seconds=60)" in src
