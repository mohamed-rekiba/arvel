"""Kit imports middleware from the framework; local copies deleted."""

from __future__ import annotations

import importlib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent.parent


def test_locale_negotiation_local_copy_deleted() -> None:
    """locale_negotiation.py must not exist after extraction."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "locale_negotiation.py"
    assert not local_file.exists(), (
        "locale_negotiation.py still exists — delete it and import from arvel"
    )


def test_security_headers_local_copy_deleted() -> None:
    """security_headers.py must not exist after extraction."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "security_headers.py"
    assert not local_file.exists(), (
        "security_headers.py still exists — delete it and import from arvel"
    )


def test_kit_middleware_init_imports_set_locale_from_framework() -> None:
    """Kit must import SetLocaleMiddleware from arvel.i18n.middleware."""
    import app.http.middleware
    from arvel.i18n.middleware import SetLocaleMiddleware

    importlib.reload(app.http.middleware)

    assert hasattr(app.http.middleware, "SetLocaleMiddleware"), (
        "kit's app.http.middleware must export SetLocaleMiddleware from arvel"
    )
    assert app.http.middleware.SetLocaleMiddleware is SetLocaleMiddleware, (
        "SetLocaleMiddleware in kit must be the arvel version, not a local copy"
    )


def test_kit_middleware_init_imports_security_headers_from_framework() -> None:
    """Kit must import SecurityHeadersMiddleware from arvel."""
    import app.http.middleware
    from arvel.http.middleware.security_headers import SecurityHeadersMiddleware

    importlib.reload(app.http.middleware)

    assert hasattr(app.http.middleware, "SecurityHeadersMiddleware"), (
        "kit's app.http.middleware must export SecurityHeadersMiddleware from arvel"
    )
    assert app.http.middleware.SecurityHeadersMiddleware is SecurityHeadersMiddleware, (
        "SecurityHeadersMiddleware must be the arvel version, not a local copy"
    )


def test_locale_negotiation_middleware_class_not_in_kit() -> None:
    """LocaleNegotiationMiddleware must not be defined in the kit."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "locale_negotiation.py"
    if local_file.exists():
        source = local_file.read_text()
        assert "class LocaleNegotiationMiddleware" not in source, (
            "LocaleNegotiationMiddleware class must be removed from the kit"
        )
