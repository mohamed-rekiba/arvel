"""Route-level middleware Protocol and built-in middlewares.

This is a thin re-export shim — historically all middleware lived in a single
file (``arvel.http.middleware``). WI-arvel-003 converted it to a package so
``database_transaction`` could live alongside as a sibling module without
mixing concerns. The public symbols (``Cors``, ``Throttle``, ``Authenticate``,
``VerifyCsrf``, ``Middleware``, ``CallNext``) are unchanged.
"""

from __future__ import annotations

from arvel.http._middleware_core import (
    Authenticate,
    CallNext,
    Cors,
    CsrfMismatchException,
    Middleware,
    Throttle,
    VerifyCsrf,
)
from arvel.http.middleware.method_spoof import MethodSpoofMiddleware
from arvel.http.middleware.security_headers import SecurityHeadersMiddleware
from arvel.http.middleware.signed import SignedMiddleware

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
    "VerifyCsrf",
]
