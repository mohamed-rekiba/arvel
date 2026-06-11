"""Framework contracts — small base classes and protocols shared across layers.

Kept dependency-free so any layer (http, auth, observability, context,
maintenance) can import a contract without risking an import cycle.
"""

from __future__ import annotations

from arvel.contracts.middleware import GlobalMiddleware

__all__ = ["GlobalMiddleware"]
