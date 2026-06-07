"""Auth-subsystem ORM models.

Arvent ActiveRecord models for the framework's auth tables.

``User``, ``PasswordReset``, and ``PersonalAccessToken`` are loaded lazily
so apps that define their own versions (with different fields, PKs, or table
names) can import ``arvel.auth.models.RefreshToken`` without triggering a
SQLAlchemy MetaData conflict on the other tables.

``RefreshToken`` is always eagerly imported because the framework's auth
services own it — apps are not expected to override it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.auth.models.refresh_token import RefreshToken

if TYPE_CHECKING:
    from arvel.auth.models.password_reset import PasswordReset
    from arvel.auth.models.personal_access_token import PersonalAccessToken
    from arvel.auth.models.user import User


def __getattr__(name: str) -> object:
    if name == "User":
        from arvel.auth.models.user import User  # noqa: PLC0415

        return User
    if name == "PasswordReset":
        from arvel.auth.models.password_reset import PasswordReset  # noqa: PLC0415

        return PasswordReset
    if name == "PersonalAccessToken":
        from arvel.auth.models.personal_access_token import PersonalAccessToken  # noqa: PLC0415

        return PersonalAccessToken
    msg = f"module 'arvel.auth.models' has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["PasswordReset", "PersonalAccessToken", "RefreshToken", "User"]
