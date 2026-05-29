"""AuthBroker — pluggable authentication broker.

The broker is the object the framework resolves at ``"auth.broker"`` in the
container. The default implementation delegates to ``AuthService`` and uses
``RefreshToken`` for persistence.  Apps that need custom behaviour can swap in
a different class via::

    # config/auth.py
    broker_class = "app.auth.custom_broker.CustomAuthBroker"
"""

from __future__ import annotations

from arvel.auth.auth_service import AuthService
from arvel.auth.models.refresh_token import RefreshToken


class AuthBroker(AuthService):
    """Default auth broker.

    Identical to ``AuthService`` but explicitly names ``RefreshToken`` as the
    model it uses for refresh-token persistence. Subclass and override
    ``refresh_token_model`` to swap the storage model.
    """

    refresh_token_model: type[RefreshToken] = RefreshToken


__all__ = ["AuthBroker"]
