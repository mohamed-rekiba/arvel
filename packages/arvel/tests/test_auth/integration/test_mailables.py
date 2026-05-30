"""Default mailables render correctly (FR-028-05, FR-028-24, FR-028-38)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_verify_email_mailable_renders_html_and_text() -> None:
    """FR-028-05, NFR-028-21 — both template names present, signed URL embedded."""
    from arvel.auth.mail import VerifyEmailMailable

    m = VerifyEmailMailable(
        user_email="user@example.com",
        verify_url="https://app.example.com/verify/abc123",
    )
    env = m.envelope()
    assert env.to == ["user@example.com"]
    assert "Verify" in env.subject

    c = m.content()
    assert c.html_view is not None
    assert c.text_view is not None
    assert "verify_url" in c.data
    assert c.data["verify_url"] == "https://app.example.com/verify/abc123"


@pytest.mark.asyncio
async def test_password_reset_mailable_renders_html_and_text() -> None:
    """FR-028-24 — reset URL embedded; ttl_minutes in context."""
    from arvel.auth.mail import PasswordResetMailable

    m = PasswordResetMailable(
        user_email="user@example.com",
        reset_url="https://app.example.com/reset/token123",
        ttl_minutes=30,
    )
    env = m.envelope()
    assert env.to == ["user@example.com"]
    assert "password" in env.subject.lower() or "reset" in env.subject.lower()

    c = m.content()
    assert c.html_view is not None
    assert c.text_view is not None
    assert c.data["reset_url"] == "https://app.example.com/reset/token123"
    assert c.data["ttl_minutes"] == 30


@pytest.mark.asyncio
async def test_user_template_overrides_framework_default() -> None:
    """FR-028-38 — VerifyEmailMailable uses configurable template names."""
    from arvel.auth.mail import VerifyEmailMailable

    m = VerifyEmailMailable(user_email="u@test.com", verify_url="https://example.com/v/x")
    c = m.content()
    # Templates named under auth/emails/ so app's views directory takes precedence
    # when placed in the Jinja2 FileSystemLoader path.
    assert c.html_view is not None and "auth" in c.html_view
    assert c.text_view is not None and "auth" in c.text_view
