# Email Verification

Email verification confirms that a user controls the address they signed up with. Arvel ships a complete verification flow — signed URL generation, email delivery, endpoint, and resend — all wired automatically when you use `AuthServiceProvider`.

## Using the built-in flow

If you ran `arvel auth:install` and registered `AuthServiceProvider`, two endpoints are ready immediately:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/auth/verify/{signed}` | Confirm the email address (signed URL from the email) |
| `POST` | `/api/auth/verify/resend` | Re-send the verification email |

When a user registers via `POST /api/auth/register`, Arvel automatically dispatches `VerifyEmailMailable`. The email contains a signed link that expires in 60 minutes. Clicking the link calls `GET /api/auth/verify/{signed}`, which marks `email_verified_at` on the user.

See [Authentication](authentication.md#quick-start) for the one-command setup.

## Requiring a verified email

Use the `Verified` middleware on any route that needs a confirmed address:

```python
from arvel.auth.middleware import Authenticated, Verified

with Route.group(middleware=[Authenticated, Verified]):
    @Route.get("/billing")
    async def billing(): ...
```

Unverified users get a `403 Forbidden` response pointing them to the resend endpoint.

## Manual setup (without AuthServiceProvider)

If you're not using `AuthServiceProvider`, add `email_verified_at` to your User model and call `VerifyEmailMailable` directly.

### User model

```python
from datetime import UTC, datetime as _datetime
from sqlalchemy.orm import Mapped
from arvel.database import Model, datetime, id_, string


class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = id_()
    email: Mapped[str] = string(255, unique=True)
    email_verified_at: Mapped[_datetime | None] = datetime(nullable=True)
```

### Send the verification email

```python
from arvel.auth.mail import VerifyEmailMailable
from arvel.facades import Mail


await Mail.send(VerifyEmailMailable(user=user, base_url="https://yourapp.com"))
```

`VerifyEmailMailable` generates a signed URL automatically. It embeds the user ID and a hash of the email address, then signs the whole URL with the app key.

### The verification endpoint

```python
from arvel.auth.email_verification_service import EmailVerificationService


@Route.get("/email/verify/{signed}")
async def verify(signed: str, verifier: EmailVerificationService) -> dict:
    await verifier.verify(signed)
    return {"status": "Email verified."}
```

`EmailVerificationService.verify(signed)` decodes the token, validates the HMAC + expiry, looks up the user, and sets `email_verified_at`. It raises `EmailVerificationError` on any failure.

### Resend

```python
@Route.post("/email/verify/resend", middleware=[Authenticated])
async def resend(request: Request) -> dict:
    user = request.state.user
    if user.email_verified_at is not None:
        return {"status": "Already verified."}
    await Mail.send(VerifyEmailMailable(user=user, base_url="https://yourapp.com"))
    return {"status": "Verification email sent."}
```

A resend rate limit applies automatically when routing through `AuthController` — 3 resend attempts per hour per user. When calling `VerifyEmailMailable` directly, add your own guard if needed.

## Customizing the email

Override `VerifyEmailMailable` in your service provider:

```python
from arvel.mail.mailable import Mailable
from arvel.auth import AuthServiceProvider


class MyVerifyEmailMailable(Mailable):
    def __init__(self, user, verify_url: str) -> None:
        self.user = user
        self.verify_url = verify_url

    def build(self) -> "MyVerifyEmailMailable":
        return (
            self
            .subject("Confirm your email address")
            .view("emails.verify", {"name": self.user.name, "url": self.verify_url})
        )


class MyAuthServiceProvider(AuthServiceProvider):
    def make_verify_email_mailable_class(self):
        return MyVerifyEmailMailable
```

## Signed URL expiry

```env
AUTH_VERIFICATION_EXPIRE_MINUTES=60    # default 60
```

## Where to next?

- [Authentication](authentication.md) — the full login flow and `auth:install`.
- [Password Reset](passwords.md) — the parallel signed-URL flow.
- [Mail](mail.md) — customizing email templates.
