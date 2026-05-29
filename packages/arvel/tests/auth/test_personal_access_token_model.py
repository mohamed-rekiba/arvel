"""PersonalAccessToken model behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from arvel.auth.models.personal_access_token import PersonalAccessToken


def _token(
    *,
    abilities: list[str] | None = None,
    expires_at: datetime | None = None,
) -> PersonalAccessToken:
    return PersonalAccessToken(
        tokenable_type="User",
        tokenable_id="user-1",
        name="api",
        token="a" * 64,
        abilities=abilities or ["articles.read"],
        expires_at=expires_at,
    )


def test_personal_access_token_hides_token_and_checks_abilities() -> None:
    token = _token()

    assert token.id
    assert token.can("articles.read") is True
    assert token.can("articles.write") is False
    assert "token" not in token.to_dict()


def test_personal_access_token_wildcard_allows_any_ability() -> None:
    token = _token(abilities=["*"])

    assert token.can("anything") is True


def test_personal_access_token_expiry_handles_none_naive_and_aware_dates() -> None:
    never = _token(expires_at=None)
    naive_past = _token(expires_at=datetime(2020, 1, 1, tzinfo=UTC).replace(tzinfo=None))
    aware_future = _token(expires_at=datetime.now(tz=UTC) + timedelta(days=1))

    assert never.is_expired is False
    assert naive_past.is_expired is True
    assert aware_future.is_expired is False
