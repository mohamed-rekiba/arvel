# CSRF Protection

Cross-site request forgery tricks an authenticated user's browser into submitting a state-changing
request they didn't intend. arvel guards against it automatically for the **web** group — you rarely
touch it, but understanding the mechanism helps when a request is unexpectedly rejected.

## How it works

The `ValidateCsrfToken` middleware (wired into the `web` group) rejects any state-changing request
whose CSRF token doesn't match the session. **Safe methods — `GET`, `HEAD`, `OPTIONS` — are exempt.**
For the rest, two gates must both pass:

- **Provenance.** A request that carries an `Origin` header (browsers send it on unsafe requests)
  must come from the app's own host or a configured trusted origin; `Referer` is the fallback when
  `Origin` is absent. A request with neither header (curl, a native API client) is judged by the
  token alone.
- **Token.** The submitted token — from the `X-CSRF-TOKEN` (or `X-XSRF-TOKEN`) header, or the
  `_token` field of a form/JSON body — must match the session's `_token`. A mismatch or missing
  token raises a **419** (page-expired).

## Tokens in forms

The middleware seeds the session token on each web request, so a template can render it. Use the
`csrf_field()` helper to emit a hidden input, or `csrf_token()` for the raw value:

```html
<form method="POST" action="/posts">
  {{ csrf_field() }}          <!-- <input type="hidden" name="_token" value="..."> -->
  ...
</form>
```

## Tokens for SPAs

On the way out, the middleware mirrors the token into a JS-readable `XSRF-TOKEN` cookie. A decoupled
single-page app reads that cookie and echoes it back as the `X-XSRF-TOKEN` header — no server-rendered
meta tag needed. The cookie is intentionally **not** `HttpOnly` (it's the double-submit token, not a
secret — the session cookie stays `HttpOnly`) and inherits the session's Secure flag.

## Exempting URIs

Endpoints that legitimately receive unauthenticated state-changing requests — a webhook a third
party posts to — should be exempt. Two ways, which combine (merged, not replaced):

```python
# config/session.py
config = {"csrf_except": ["webhooks/*", "stripe/callback"]}   # URI globs (no leading slash)
```

```python
# or in a ValidateCsrfToken subclass
class VerifyCsrfToken(ValidateCsrfToken):
    except_ = ["webhooks/*"]
```

Patterns are matched against the request path with `fnmatch`.

!!! warning "Exempting a route is not authenticating it"
    Skipping CSRF only removes the token check — it doesn't make the endpoint safe to call. An exempt
    route must verify the caller itself: a webhook should check the provider's **signature**, an API
    endpoint a **bearer token** or **API key**. Never exempt a route that mutates state on the basis
    of the request alone.

## Trusted origins

To accept state-changing requests from another origin you control (a separate frontend host), list
it — the provenance gate then allows it:

```python
# config/session.py
config = {"trusted_origins": ["https://app.example.com", "partner.example"]}
```
