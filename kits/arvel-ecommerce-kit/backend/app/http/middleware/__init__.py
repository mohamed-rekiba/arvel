"""HTTP middleware for the e-commerce kit."""

from __future__ import annotations

from arvel.auth.middleware.csrf_double_submit import CsrfDoubleSubmitMiddleware
from arvel.http.middleware.security_headers import SecurityHeadersMiddleware
from arvel.i18n.middleware import SetLocaleMiddleware

__all__ = [
    "CsrfDoubleSubmitMiddleware",
    "SecurityHeadersMiddleware",
    "SetLocaleMiddleware",
]
