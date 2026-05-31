# arvel-oauth

OAuth2/OIDC login for [Arvel](https://github.com/mohamed-rekiba/arvel) —
Google, GitHub, Microsoft, Apple, and any generic OIDC issuer.

- PKCE (S256) enforced by default for providers that support it.
- External identities linked to your existing `User` model via an installable migration.
- Provider tokens encrypted at rest (AES-256-GCM, keyed from `APP_KEY`).

## Install

```bash
uv add arvel-oauth
```

Register the provider and publish the migration:

```python
# bootstrap/app.py
from arvel_oauth import OAuthServiceProvider

app.register(OAuthServiceProvider)
```

```bash
arvel oauth:install
arvel migrate
```

## Configure

Set the credentials for the providers you use:

```dotenv
OAUTH_GOOGLE_CLIENT_ID=...
OAUTH_GOOGLE_CLIENT_SECRET=...
OAUTH_GOOGLE_REDIRECT_URI=https://app.example.com/auth/google/callback
```

See `docs/site/docs/oauth.md` for the full provider table and HTTP flow.
