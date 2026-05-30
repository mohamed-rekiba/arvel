"""QA-Pre tests: demo imports from framework, local copies deleted.

Covers FR-032-01, FR-032-02, FR-032-04.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent.parent


def test_locale_negotiation_local_copy_deleted() -> None:
    """FR-032-01: locale_negotiation.py must not exist after extraction."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "locale_negotiation.py"
    assert not local_file.exists(), (
        "locale_negotiation.py still exists — delete it and import from arvel"
    )


def test_security_headers_local_copy_deleted() -> None:
    """FR-032-04: security_headers.py must not exist after extraction."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "security_headers.py"
    assert not local_file.exists(), (
        "security_headers.py still exists — delete it and import from arvel"
    )


def test_demo_middleware_init_imports_set_locale_from_framework() -> None:
    """FR-032-02h: demo must import SetLocaleMiddleware from arvel.i18n.middleware."""
    import app.http.middleware
    from arvel.i18n.middleware import SetLocaleMiddleware

    importlib.reload(app.http.middleware)

    assert hasattr(app.http.middleware, "SetLocaleMiddleware"), (
        "demo's app.http.middleware must export SetLocaleMiddleware from arvel"
    )
    assert app.http.middleware.SetLocaleMiddleware is SetLocaleMiddleware, (
        "SetLocaleMiddleware in demo must be the arvel version, not a local copy"
    )


def test_demo_middleware_init_imports_security_headers_from_framework() -> None:
    """FR-032-04h: demo must import SecurityHeadersMiddleware from arvel."""
    import app.http.middleware
    from arvel.http.middleware.security_headers import SecurityHeadersMiddleware

    importlib.reload(app.http.middleware)

    assert hasattr(app.http.middleware, "SecurityHeadersMiddleware"), (
        "demo's app.http.middleware must export SecurityHeadersMiddleware from arvel"
    )
    assert app.http.middleware.SecurityHeadersMiddleware is SecurityHeadersMiddleware, (
        "SecurityHeadersMiddleware must be the arvel version, not a local copy"
    )


def test_locale_negotiation_middleware_class_not_in_demo() -> None:
    """FR-032-01a: LocaleNegotiationMiddleware class must not be defined in the demo."""
    local_file = _BACKEND_ROOT / "app" / "http" / "middleware" / "locale_negotiation.py"
    if local_file.exists():
        source = local_file.read_text()
        assert "class LocaleNegotiationMiddleware" not in source, (
            "LocaleNegotiationMiddleware class must be removed from the demo"
        )
