# CSRF Protection

Cross-site request forgery (CSRF) is an attack where a malicious site tricks an authenticated user's browser into making a state-changing request to your application. Arvel ships two CSRF strategies — pick the one that matches your architecture:

| Strategy | Use when |
|---|---|
| **`CsrfDoubleSubmitMiddleware`** | SPA + API (JWT auth, stateless) |
| **`Csrf`** | Server-rendered HTML forms (session auth) |

## Double-submit cookie (SPA / API auth)

For SPAs that authenticate via JWT, `CsrfDoubleSubmitMiddleware` uses the double-submit cookie pattern:

1. After login, the auth layer sets a `_csrf` cookie (not HttpOnly — JavaScript must read it).
2. Your SPA reads the cookie and includes its value in every state-changing request as the `X-CSRF-TOKEN` header.
3. `CsrfDoubleSubmitMiddleware` compares the cookie value and the header with a constant-time compare. A mismatch raises `CsrfMismatchException` → `403 Forbidden`.

An attacker can forge a request with the right cookie OR the right header — but not both, because the cookie is scoped to your origin and a cross-origin request can't read it.

### With AuthServiceProvider (automatic)

If you registered `AuthServiceProvider`, the middleware is already active on all auth endpoints. Nothing extra to do.

### Manual setup

```python
from arvel.auth.middleware.csrf_double_submit import CsrfDoubleSubmitMiddleware

app = Application.configure(".").create()
app.add_middleware(
    CsrfDoubleSubmitMiddleware,
    csrf_cookie="_csrf",        # cookie name (default)
    csrf_header="X-CSRF-TOKEN", # header name (default)
)
```

Exempt paths (e.g. login and register endpoints that create the cookie in the first place) are skipped automatically based on the prefix. You can add your own:

```python
CsrfDoubleSubmitMiddleware(exempt=["/api/webhooks/stripe", "/api/external/"])
```

### SPA integration

After login, read the `_csrf` cookie and attach it to every mutating request:

```typescript
function getCsrf(): string {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("_csrf="))
        ?.split("=")[1] ?? "";
}

await fetch("/api/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-TOKEN": getCsrf() },
});
```

Most SPA HTTP clients (axios, TanStack Query) let you set a global request interceptor so you don't repeat this on every call.

## Session-based CSRF (server-rendered forms)

For server-rendered apps that use session authentication, the `Csrf` middleware handles protection automatically.

### How it works

When the `Csrf` middleware is active and a session exists:

1. On every request, Arvel ensures a `_csrf_token` exists in the session. If missing, it generates a 32-byte URL-safe random token.
2. The token is exposed to your views via the `csrf_token()` helper and rendered into every form as a hidden field.
3. On `POST`, `PUT`, `PATCH`, or `DELETE` requests, Arvel reads the submitted token (from form data or the `X-CSRF-TOKEN` header) and compares it against the session token.
4. If the tokens don't match, the request is rejected with a `419 Page Expired` response.

### Enabling protection

Add the middleware to your web routes:

```python
from arvel.http.middleware import Csrf


with Route.group(middleware=[Csrf()]):
    @Route.post("/profile")
    async def update_profile(): ...
```

Or globally for all web routes via your provider:

```python
class HttpServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Route.use([Csrf()])
```

API routes (which authenticate via Bearer tokens, not sessions) **don't need** CSRF — they're not vulnerable to it. Apply the middleware only to session-authenticated routes.

### Including the token in forms

```html
<form method="post" action="/profile">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
    <input type="text" name="name">
    <button type="submit">Save</button>
</form>
```

If you're using Jinja2 templates, the `csrf_token()` helper is registered globally.

For Single-Page Apps that talk to session-authenticated endpoints, expose the token via a meta tag and read it in JavaScript:

```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

```js
const token = document.querySelector('meta[name="csrf-token"]').content;

fetch('/profile', {
  method: 'POST',
  headers: { 'X-CSRF-TOKEN': token, 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: 'Alice' }),
});
```

### Excluding URIs from CSRF

Some endpoints need to accept requests from third parties — webhooks from Stripe, GitHub, etc. Exclude them:

```python
Csrf(except_=["/webhooks/*", "/api/external/billing"])
```

Patterns support shell-style wildcards.

### Token rotation

Tokens rotate on session regeneration (login, logout, privilege change). The currently rendered form continues to work until the session itself rotates.

To force rotation manually:

```python
from arvel.facades import Session

Session.regenerate_token()
```

### When tokens fail

A `419 Page Expired` response indicates a token mismatch. Common causes:

- The user's session expired between page load and form submission.
- The user has two tabs open, logged out of one (rotating the token), then submitted from the other.
- A reverse proxy is stripping the `X-CSRF-TOKEN` header.
- The form was submitted across an HTTPS/HTTP boundary (token wasn't sent due to `Secure` cookie flag).

For SPAs, intercept `419` responses and re-fetch the token from the meta tag (or a dedicated `/_csrf` endpoint) before retrying.

### Security notes

- Use HTTPS in production. CSRF tokens depend on session cookies, and session cookies depend on transport security.
- Set `Session.cookie_samesite = "lax"` (the default) — it provides defense in depth without breaking common navigation patterns.
- Don't use `GET` for state-changing operations. The CSRF middleware doesn't protect `GET` requests, and search-engine crawlers will happily follow links.

## Where to next?

- [Authentication](authentication.md) — session-based auth.
- [Middleware](middleware.md) — how `Csrf` fits into the pipeline.
- [Session](session.md) — session storage configuration.
