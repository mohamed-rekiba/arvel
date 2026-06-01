# arvel-oauth

<p>
<a href="https://pypi.org/project/arvel-oauth/">
    <img src="https://img.shields.io/pypi/v/arvel-oauth?color=%2334D058&label=pypi" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

OAuth2 / OIDC social login for [Arvel](https://arvel.dev) — Google, GitHub, Microsoft, Apple, and any
generic OIDC issuer.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/oauth" target="_blank">https://arvel.dev/packages/oauth</a>

---

## What it does

- Runs the authorization-code flow with PKCE (`S256`) and a signed state cookie.
- Links the external identity to your existing `User` model through an installable migration.
- Issues a JWT session via the framework's `AuthService` after a successful exchange.
- Encrypts provider tokens at rest (AES-256-GCM, keyed from `APP_KEY`).

## Install

```bash
uv add "arvel[oauth]"
# or: pip install arvel-oauth
```

Register the provider in `bootstrap/providers.py`:

```python
from arvel_oauth import OAuthServiceProvider

providers = [
    # ...other providers...
    OAuthServiceProvider,
]
```

Publish the migration and run it:

```bash
arvel vendor:publish --tag=arvel-oauth   # or: arvel oauth:install
arvel migrate
```

`OAuthServiceProvider` binds `OAuthConfig` and `OAuthManager` as singletons and ships the
`oauth_accounts` table migration.

## Supported providers

| Name | Class | Notes |
|---|---|---|
| `google` | `GoogleProvider` | OIDC userinfo; requests offline access |
| `github` | `GitHubProvider` | Not OIDC; PKCE follows `OAUTH_USE_PKCE` (default on) |
| `microsoft` | `MicrosoftProvider` | Entra ID; tenant from `OAUTH_MICROSOFT_TENANT` |
| `apple` | `AppleProvider` | JWT client secret; identity from the verified `id_token` |
| `oidc` | `OIDCProvider` | Generic; discovers config from the issuer's `.well-known` endpoint |

## Configure

`OAuthConfig` reads `OAUTH_*` environment variables. Set the credentials for the providers you use:

```dotenv
OAUTH_GOOGLE_CLIENT_ID=...
OAUTH_GOOGLE_CLIENT_SECRET=...
OAUTH_GOOGLE_REDIRECT_URI=https://app.example.com/auth/google/callback

# Shared flow settings (defaults shown)
OAUTH_USE_PKCE=true
OAUTH_SUCCESS_REDIRECT_URL=/
OAUTH_ERROR_REDIRECT_URL=/login
```

A provider counts as "configured" once its credentials are present — client id + secret for
Google / GitHub / Microsoft, client id + private key for Apple, and issuer URL + client id for OIDC.

## Mounting the routes

The package does **not** auto-mount routes. Build a controller and register the redirect + callback
endpoints yourself:

```python
from arvel_oauth.http import OAuthController, register_oauth_routes

controller = OAuthController(manager=manager, config=config, auth=auth_service)
register_oauth_routes(router, controller)
```

See the [full guide](https://arvel.dev/packages/oauth) for the controller wiring and the complete HTTP flow.

## License

MIT — see [LICENSE](../../LICENSE).
