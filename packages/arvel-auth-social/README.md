# arvel-auth-social

OAuth2/OIDC social login for [Arvel](https://github.com/mohamed-rekiba/arvel) —
Google, GitHub, Microsoft, Apple, and any generic OIDC issuer.

- PKCE (S256) enforced by default for providers that support it.
- Social identities linked to your existing `User` model via an installable migration.
- Provider tokens encrypted at rest (AES-256-GCM, keyed from `APP_KEY`).

## Install

```bash
uv add arvel-auth-social
```

Register the provider and publish the migration:

```python
# bootstrap/app.py
from arvel_auth_social import SocialAuthServiceProvider

app.register(SocialAuthServiceProvider)
```

```bash
arvel auth:social:install
arvel migrate
```

## Configure

Set the credentials for the providers you use:

```dotenv
SOCIAL_GOOGLE_CLIENT_ID=...
SOCIAL_GOOGLE_CLIENT_SECRET=...
SOCIAL_GOOGLE_REDIRECT_URI=https://app.example.com/auth/google/callback
```

See `docs/site/docs/social-auth.md` for the full provider table and HTTP flow.
