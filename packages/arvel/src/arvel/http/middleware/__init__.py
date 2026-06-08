"""Route-level middleware Protocol and built-in middlewares.

This is a thin re-export shim — historically all middleware lived in a single
file (``arvel.http.middleware``). converted it to a package so
``database_transaction`` could live alongside as a sibling module without
mixing concerns. The public symbols (``Cors``, ``Throttle``, ``Authenticate``,
``VerifyCsrf``, ``Middleware``, ``CallNext``) are unchanged.
"""

from __future__ import annotations

from arvel.http._middleware_core import (
    Authenticate,
    CallNext,
    Cors,
    Middleware,
    Throttle,
    VerifyCsrf,
)
from arvel.http.exceptions import CsrfMismatchException
from arvel.http.middleware.method_spoof import MethodSpoofMiddleware
from arvel.http.middleware.security_headers import SecurityHeadersMiddleware
from arvel.http.middleware.signed import SignedMiddleware
from arvel.http.middleware.trust_proxies import TrustProxiesMiddleware

__all__ = [
    "Authenticate",
    "CallNext",
    "Cors",
    "CsrfMismatchException",
    "MethodSpoofMiddleware",
    "Middleware",
    "SecurityHeadersMiddleware",
    "SignedMiddleware",
    "Throttle",
    "TrustProxiesMiddleware",
    "VerifyCsrf",
]
