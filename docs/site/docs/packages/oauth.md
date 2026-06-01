# arvel-oauth

<a name="introduction"></a>
## Introduction

`arvel-oauth` provides OAuth2/OIDC social login for Arvel. It handles the authorization-code flow (with PKCE and state cookies), links the external identity to a local user, and issues a JWT session via `AuthService`.

OAuth (Open Authorization) lets users log in with an external identity provider. OIDC (OpenID Connect) is an identity layer on top of OAuth2.

<a name="installation"></a>
## Installation

```bash
uv add "arvel[oauth]"
```

Register the provider and publish the migration:

```python
# bootstrap/providers.py
from arvel_oauth import OAuthServiceProvider

providers = [OAuthServiceProvider]
```

```bash
arvel vendor:publish --tag=arvel-oauth   # or: arvel oauth:install
arvel migrate
```

`OAuthServiceProvider` binds `OAuthConfig` and `OAuthManager` as singletons and publishes the `oauth_accounts` table migration.

<a name="supported-providers"></a>
## Supported Providers

| Name | Class | Notes |
|---|---|---|
| `google` | `GoogleProvider` | OIDC userinfo; requests offline access |
| `github` | `GitHubProvider` | Not OIDC; PKCE follows `OAUTH_USE_PKCE` (default on) |
| `microsoft` | `MicrosoftProvider` | Entra ID; tenant from `OAUTH_MICROSOFT_TENANT` |
| `apple` | `AppleProvider` | Uses a JWT client secret; identity from the verified `id_token` |
| `oidc` | `OIDCProvider` | Generic; discovers config from the issuer's `.well-known` endpoint |

<a name="configuration"></a>
## Configuration

`OAuthConfig` reads `OAUTH_*` environment variables. A provider counts as "configured" once its credentials are set — client id + secret for Google/GitHub/Microsoft, client id + private key for Apple, and issuer URL + client id for OIDC.

| Env var | Default |
|---|---|
| `OAUTH_USE_PKCE` | `true` |
| `OAUTH_SUCCESS_REDIRECT_URL` | `/` |
| `OAUTH_ERROR_REDIRECT_URL` | `/login` |
| `OAUTH_ALLOW_HTTP_ISSUER` | `false` |
| `OAUTH_GOOGLE_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | `""` |
| `OAUTH_GITHUB_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | `""` |
| `OAUTH_MICROSOFT_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` / `_TENANT` | `""` / `common` |
| `OAUTH_APPLE_CLIENT_ID` / `_TEAM_ID` / `_KEY_ID` / `_PRIVATE_KEY` / `_REDIRECT_URI` | `""` |
| `OAUTH_OIDC_ISSUER_URL` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URI` | `""` |

<a name="mounting-the-routes"></a>
## Mounting the Routes

The package does **not** auto-mount routes. Build a controller and register the two endpoints yourself:

```python
from fastapi import APIRouter
from arvel_oauth.http import OAuthController, register_oauth_routes

controller = OAuthController(manager=manager, config=config, auth=auth_service)

router = APIRouter()
register_oauth_routes(router, controller=controller, prefix="/auth")
app.include_router(router)
```

This registers:

- `GET /auth/{provider}/redirect` — start the flow (sets state/PKCE cookies, redirects to the provider).
- `GET /auth/{provider}/callback` — exchange the code, link the account, issue a session, redirect to the success URL.

`{provider}` must be one of `google`, `github`, `microsoft`, `apple`, `oidc`.

<a name="linking-accounts-directly"></a>
## Linking Accounts Directly

To handle the exchange yourself, use the linker — it finds or creates the local user and the `oauth_accounts` row:

```python
from arvel_oauth import OAuthAccountLinker

account = await OAuthAccountLinker(session).link(oauth_user, token)
```

<a name="data-model"></a>
## Data Model

`OAuthAccount` (table `oauth_accounts`) stores the link: `user_id` (FK to `users.id`), a unique `(provider, provider_id)`, and the OAuth tokens encrypted via the `Crypt` facade.

> [!WARNING]
> Token encryption needs `APP_KEY` set when the column is read or written. Run `arvel key:generate` first.

<a name="gotchas"></a>
## Gotchas

- `InvalidOAuthState` is exported but isn't raised by the controller — a bad/missing state surfaces as a `ValidationException`.
- The Apple "configured" check looks at `client_id` + `private_key` only; set `team_id` and `key_id` too for the flow to work.
- The generic OIDC provider is resolved through `manager.oidc()` (it performs discovery), not the synchronous `manager.provider("oidc")`.
