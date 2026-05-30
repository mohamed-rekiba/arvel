# Password Reset

Most applications need a "forgot your password?" flow. Arvel ships one out of the box — token generation, email delivery, reset endpoint, and token cleanup are all handled for you.

## Using the built-in flow

If you ran `arvel auth:install` and registered `AuthServiceProvider`, the password-reset flow is already wired. Two endpoints are available immediately:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/forgot-password` | Request a reset link (sends `PasswordResetMailable`) |
| `POST` | `/api/auth/reset-password` | Complete the reset with the signed token |

The `PasswordResetMailable` sends a link containing a one-time signed token. Clicking it lands the user on your front-end reset form; the form submits the token and new password to `POST /api/auth/reset-password`.

See [Authentication](authentication.md#quick-start) for the one-command setup.

## How it works

1. Your front-end `POST`s `{ "email": "user@example.com" }` to `/api/auth/forgot-password`.
2. Arvel looks up the user by email. If found, it generates a random 60-character token, stores its SHA-256 hash in `password_reset_tokens`, and dispatches `PasswordResetMailable`.
3. If the email isn't registered, Arvel returns the same `202 Accepted` — no enumeration.
4. The user clicks the link in the email and submits `{ "email": ..., "token": ..., "password": ..., "password_confirmation": ... }` to `/api/auth/reset-password`.
5. Arvel verifies the token hash, checks expiry, hashes the new password with bcrypt, updates the user, burns the token, and revokes all existing refresh tokens for that user.

## Manual setup (without AuthServiceProvider)

If you're not using `AuthServiceProvider`, you can call `PasswordService` directly.

### Migrations

```bash
uv run arvel make:migration create_password_reset_tokens_table
```

```python
# database/migrations/<timestamp>_create_password_reset_tokens_table.py
from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def build(t: Blueprint) -> None:
        t.string("email").primary()
        t.string("token_hash")
        t.timestamp("created_at")
        t.index(["created_at"])

    schema.create("password_reset_tokens", build)


async def down(schema: Schema) -> None:
    schema.drop("password_reset_tokens")
```

```bash
uv run arvel migrate
```

### Request a reset

```python
from arvel.auth import PasswordService
from arvel import FormRequest
from pydantic import BaseModel, EmailStr


class ForgotPasswordPayload(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(FormRequest[ForgotPasswordPayload]):
    async def authorize(self, request) -> bool:
        return True


@Route.post("/forgot-password", status_code=202)
async def forgot(form: ForgotPasswordRequest, passwords: PasswordService) -> dict:
    await passwords.send_reset_link(form.validated().email)
    return {"status": "If that email is registered, a reset link is on its way."}
```

`send_reset_link` returns silently regardless of whether the email exists — this prevents account enumeration.

### Process the reset

```python
from pydantic import Field, model_validator


class ResetPasswordPayload(BaseModel):
    email: EmailStr
    token: str
    password: str = Field(min_length=12)
    password_confirmation: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordPayload":
        if self.password != self.password_confirmation:
            raise ValueError("Passwords don't match.")
        return self


class ResetPasswordRequest(FormRequest[ResetPasswordPayload]):
    async def authorize(self, request) -> bool:
        return True


@Route.post("/reset-password")
async def reset(form: ResetPasswordRequest, passwords: PasswordService) -> dict:
    payload = form.validated()
    await passwords.reset(email=payload.email, token=payload.token, password=payload.password)
    return {"status": "Password updated. You can sign in now."}
```

`passwords.reset(...)` raises `PasswordResetTokenInvalidError` if the token is unknown, expired, or the user no longer exists. Map it to a `400` in your exception handler:

```python
from arvel.auth.exceptions import PasswordResetTokenInvalidError
from arvel.http.exceptions import HttpException


@app.exception_handler(PasswordResetTokenInvalidError)
async def handle_invalid_token(request, exc):
    raise HttpException(400, "Password reset link is invalid or expired.")
```

## Customizing the email

Override `PasswordResetMailable` in your service provider:

```python
from arvel.mail.mailable import Mailable
from arvel.auth import AuthServiceProvider


class MyPasswordResetMailable(Mailable):
    def __init__(self, user, reset_url: str) -> None:
        self.user = user
        self.reset_url = reset_url

    def build(self) -> "MyPasswordResetMailable":
        return (
            self
            .subject("Reset your password")
            .view("emails.reset-password", {"name": self.user.name, "url": self.reset_url})
        )


class MyAuthServiceProvider(AuthServiceProvider):
    def make_password_reset_mailable_class(self):
        return MyPasswordResetMailable
```

## Token lifetime

```env
AUTH_PASSWORDS_EXPIRE_MINUTES=60        # default 60
AUTH_PASSWORDS_THROTTLE_MINUTES=1       # one reset link per minute per email
```

The throttle prevents reset-link spam. If a second request arrives within the window, Arvel silently ignores it (no error, no new email).

## Security notes

- Always serve reset links over HTTPS.
- Tokens are stored as SHA-256 hashes. Even if the DB is compromised, the plaintext tokens can't be recovered.
- Enforce password complexity at the form-request level (`Field(min_length=12)`, dictionary checks, [Have I Been Pwned](https://haveibeenpwned.com/Passwords)).
- The built-in flow revokes all existing refresh tokens on successful reset, which logs out all other sessions automatically.

## Where to next?

- [Authentication](authentication.md) — the login flow and `auth:install`.
- [Email Verification](verification.md) — confirming email addresses after registration.
- [Hashing](hashing.md) — how new passwords are stored.
- [Mail](mail.md) — customizing the reset email template.
