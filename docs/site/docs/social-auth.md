# Social Authentication

`arvel-auth-social` adds OAuth2/OIDC social login to Arvel apps. It ships built-in providers for **Google**, **GitHub**, **Microsoft**, and **Apple**, plus a generic **OIDC** provider for any issuer that exposes a `.well-known/openid-configuration` document (Keycloak, Auth0, Okta, …). [PKCE](https://datatracker.ietf.org/doc/html/rfc7636) is on by default, and social identities are linked to your existing user model through an installable migration.

`arvel-auth-social` is a separate workspace package. Install it through the `auth-social` extra:

```bash
uv add "arvel[auth-social]"
```

## Configuration

Every provider is configured through `SOCIAL_*` environment variables. A provider is "configured" only when its credentials are present, so you only set the ones you use.

| Env var | Provider | Purpose |
|---|---|---|
| `SOCIAL_GOOGLE_CLIENT_ID` / `SOCIAL_GOOGLE_CLIENT_SECRET` | Google | OAuth client credentials |
| `SOCIAL_GOOGLE_REDIRECT_URI` | Google | Callback URL registered with Google |
| `SOCIAL_GITHUB_CLIENT_ID` / `SOCIAL_GITHUB_CLIENT_SECRET` | GitHub | OAuth app credentials |
| `SOCIAL_GITHUB_REDIRECT_URI` | GitHub | Callback URL |
| `SOCIAL_MICROSOFT_CLIENT_ID` / `SOCIAL_MICROSOFT_CLIENT_SECRET` | Microsoft | Entra ID app credentials |
| `SOCIAL_MICROSOFT_TENANT` | Microsoft | Tenant id, or `common` (default) |
| `SOCIAL_MICROSOFT_REDIRECT_URI` | Microsoft | Callback URL |
| `SOCIAL_APPLE_CLIENT_ID` | Apple | Services ID |
| `SOCIAL_APPLE_TEAM_ID` / `SOCIAL_APPLE_KEY_ID` | Apple | Used to sign the client-secret JWT |
| `SOCIAL_APPLE_PRIVATE_KEY` | Apple | ES256 private key (PEM) |
| `SOCIAL_APPLE_REDIRECT_URI` | Apple | Callback URL |
| `SOCIAL_OIDC_ISSUER_URL` | OIDC | Issuer base URL for auto-discovery |
| `SOCIAL_OIDC_CLIENT_ID` / `SOCIAL_OIDC_CLIENT_SECRET` | OIDC | Client credentials |
| `SOCIAL_OIDC_REDIRECT_URI` | OIDC | Callback URL |
| `SOCIAL_USE_PKCE` | all | Toggle PKCE globally (default `true`) |
| `SOCIAL_ALLOW_HTTP_ISSUER` | OIDC | Allow `http://` issuers — **dev only** (default `false`) |
| `SOCIAL_SUCCESS_REDIRECT_URL` | flow | Where the callback sends a logged-in user (default `/`) |
| `SOCIAL_ERROR_REDIRECT_URL` | flow | Where the callback sends a denied/failed login (default `/login`) |

Client secrets are read from the environment only — there are no hardcoded values, and they're held as `SecretStr` so they never leak into logs or reprs.

## Install

The package ships a publishable migration that creates the `social_accounts` table:

```bash
arvel auth:social:install
arvel migrate
```

The table has `id`, `user_id` (FK → `users`, cascade delete), `provider`, `provider_id`, `tokens` (encrypted), and timestamps, with a `UNIQUE(provider, provider_id)` constraint so one remote identity maps to exactly one link.

## Resolving providers

`SocialAuthManager` builds a configured provider by name:

```python
from arvel_auth_social import SocialAuthConfig, SocialAuthManager

manager = SocialAuthManager(SocialAuthConfig())

google = manager.provider("google")          # GoogleProvider
oidc = await manager.oidc()                   # OIDCProvider (async — runs discovery)

manager.configured_providers()                # ["google", "github", ...]
```

Asking for a provider you haven't configured raises a descriptive `SocialProviderNotFound` that lists what *is* configured.

## Redirect and callback flow

Register the routes once during boot:

```python
from arvel_auth_social.http import register_social_routes

register_social_routes(router)
```

That mounts two endpoints per provider:

- `GET /auth/{provider}/redirect` — builds the authorization URL, sets the `state` and PKCE `code_verifier` cookies, and redirects to the provider's consent screen.
- `GET /auth/{provider}/callback` — verifies `state`, exchanges the code, fetches the profile, links the account, and issues a session.

```text
GET /auth/google/redirect    → 302 to accounts.google.com/o/oauth2/v2/auth?...
GET /auth/google/callback?code=...&state=...  → 302 to SOCIAL_SUCCESS_REDIRECT_URL
```

If the callback `state` doesn't match the cookie, the flow returns **422** and creates no session. If the provider returns an error (e.g. `error=access_denied`), the user is redirected to `SOCIAL_ERROR_REDIRECT_URL`.

The `state` value is a cryptographically random 32-byte hex string, stored in an `HttpOnly`, `SameSite=Lax` cookie and compared server-side — it's never trusted from the query string alone.

## PKCE

PKCE is enforced by default for every provider that supports it. On redirect, the manager generates a high-entropy verifier (`secrets.token_urlsafe(96)`, ≥128 bits) and sends its S256 challenge — `base64url(sha256(verifier))`, no plain method. The verifier rides along in the callback exchange.

Opt out per-provider only when a provider can't do PKCE:

```python
GitHubProvider(client_id=..., client_secret=..., redirect_uri=..., use_pkce=False)
```

Or globally with `SOCIAL_USE_PKCE=false`. Apple still works under PKCE: its `client_secret` is a signed ES256 JWT (built from `team_id`, `key_id`, and the private key) rather than a static string.

## Generic OIDC

Point the OIDC provider at any compliant issuer and it discovers the endpoints for you:

```bash
SOCIAL_OIDC_ISSUER_URL=https://keycloak.example.com/realms/myrealm
SOCIAL_OIDC_CLIENT_ID=my-app
SOCIAL_OIDC_CLIENT_SECRET=...
SOCIAL_OIDC_REDIRECT_URI=https://app.example.com/auth/oidc/callback
```

```python
oidc = await manager.oidc()
url = oidc.get_authorization_url(state, code_challenge)
```

Discovery fetches `{issuer}/.well-known/openid-configuration` (trailing slashes are normalized) and reads `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint`. An unreachable or malformed document raises `OIDCDiscoveryError` with the issuer URL and HTTP status. Discovery requires **HTTPS** — an `http://` issuer is rejected unless you explicitly set `SOCIAL_ALLOW_HTTP_ISSUER=true` for local development.

## Account linking

`SocialAccountLinker` resolves the identity returned by a provider into a `User`:

- A matching `SocialAccount` reuses the existing user and refreshes its stored tokens.
- A first-time login with a **verified** provider email links to an existing user with that email, or creates a new one.
- An **unverified** email never auto-links to an existing account — a fresh user is created with a provider-namespaced placeholder email to avoid hijacking.

Tokens are stored through an `EncryptedJson` column (AES-256-GCM, keyed from `APP_KEY`) — never plaintext. `provider_id` is stored verbatim, never normalized, to prevent ID-collision attacks. Attempting to link a `(provider, provider_id)` that's already taken raises `DuplicateSocialAccount`.

A user can hold several social accounts (Google + GitHub), each usable independently. Deleting one simply means the next login through that provider creates a new link — no orphaned rows.
