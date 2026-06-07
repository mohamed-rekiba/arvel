"""Lazy-import surface of ``arvel.auth.models``.

Apps that override ``User`` / ``PasswordReset`` / ``PersonalAccessToken``
need to import ``RefreshToken`` without triggering a SQLAlchemy MetaData
conflict on the overridden tables, so the other three are loaded on first
attribute access.
"""

from __future__ import annotations

import pytest


def test_user_resolves_via_getattr() -> None:
    from arvel.auth import models
    from arvel.auth.models.user import User as Direct

    assert models.User is Direct


def test_password_reset_resolves_via_getattr() -> None:
    from arvel.auth import models
    from arvel.auth.models.password_reset import PasswordReset as Direct

    assert models.PasswordReset is Direct


def test_personal_access_token_resolves_via_getattr() -> None:
    from arvel.auth import models
    from arvel.auth.models.personal_access_token import PersonalAccessToken as Direct

    assert models.PersonalAccessToken is Direct


def test_unknown_attribute_raises_attribute_error() -> None:
    from arvel.auth import models

    with pytest.raises(AttributeError, match="no attribute 'DoesNotExist'"):
        _ = models.DoesNotExist


def test_refresh_token_is_eagerly_importable() -> None:
    from arvel.auth.models import RefreshToken

    assert RefreshToken.__name__ == "RefreshToken"
