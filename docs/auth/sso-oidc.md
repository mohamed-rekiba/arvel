# Single sign-on (OIDC)

When your company runs Keycloak (or Auth0, Okta, Entra…), you don't want to store passwords at all —
you want the identity provider to do the proving and just *tell* you who showed up. With OpenID
Connect the IdP hands the user a signed **JWT**; your app's only job is to **validate** that token and
trust its claims. arvel's `oidc` guard does exactly that, and — because it reads the token's claims —
it feeds *both* halves of this section at once: the `sub` claim becomes the user's
[identity](identities.md), and the `groups`/roles claim drives [authorization](idp-roles.md).

This page covers configuring the guard for Keycloak, what it validates, and how a token becomes a
logged-in, authorized user.

!!! note "Needs the `[jwt]` extra"
    The OIDC guard validates JWTs with pyjwt — `uv add 'arvel[jwt]'`.

## Two modes: obtaining a token vs validating one

SSO has two distinct jobs, and arvel gives you a piece for each — don't confuse them:

| You need to… | Use | Extra |
|---|---|---|
| **Obtain** a token by logging the user in through the provider (the "Login with Keycloak" browser redirect → callback → code exchange) | `OAuthProvider` — the OAuth2 authorization-code client | `[oauth]` |
| **Validate** a token a client already presents (an API/resource server checking a bearer JWT) | `OidcGuard` — the `oidc` guard below | `[jwt]` |

OIDC is OAuth2 plus an identity layer, so the two work together: `OAuthProvider` runs the redirect
dance and hands you an `id_token`; the `oidc` guard's verifier validates it. **The rest of this page
is the validation side.** For the interactive redirect/callback login flow, see
[OAuth2 social login](oauth.md).

## Configure the guard

Point `auth.oidc` at your realm. The guard fetches the IdP's public keys from `jwks_uri` and checks
every token's signature, issuer, and audience against these values:

```python
# config/auth.py
auth = {
    "oidc": {
        "jwks_uri": "https://keycloak.acme.com/realms/acme/protocol/openid-connect/certs",
        "issuer":   "https://keycloak.acme.com/realms/acme",
        "audience": "acme-web",          # your client_id
        "provider": "keycloak",          # used as Principal.provider (and the identity link key)
    },
}
```

`jwks_uri`, `issuer`, and `audience` are **required** — if any is missing the guard raises a clear
`ValueError` at build time rather than quietly rejecting every login (fail loud, not silent).

## A token becomes a `Principal`

Resolve the guard and verify an incoming request. The client sends the IdP's token as
`Authorization: Bearer <jwt>`; the guard validates it and returns a `Principal`:

```python
from arvel.auth.guards import GuardManager

guard = GuardManager().guard("oidc")
principal = await guard.verify(request)
# Principal(
#   provider="keycloak",
#   subject="f:1d2c…:ada",                 # the stable `sub` — the identity key
#   claims={"email": "ada@acme.com", "email_verified": True, "groups": ["/eng/backend"]},
# )
# → None if the token is missing, malformed, expired, or fails signature/iss/aud checks
```

## The full login flow

Validate the token, then turn the `Principal` into your `User` with the
[user provider](identities.md):

```python
guard = GuardManager().guard("oidc")
users = app.make("auth.user_provider")          # configured from auth.user_model + trusted providers

async def sso_login(request):
    principal = await guard.verify(request)
    if principal is None:
        return "Invalid token", 401
    user = await users.resolve(principal)        # finds-or-links-or-creates by `sub` / verified email
    if user is None:
        return "No account", 403
    auth.login(user)                             # session established
    return redirect("/dashboard")
```

For the first-time-SSO case to link onto an existing password account, add `"keycloak"` to
`trusted_email_providers` (see [Identities & account linking](identities.md)) — Keycloak's
`email_verified` claim is what makes that safe.

## Testing without a network

`OidcGuard` takes an **injectable verifier** — a callable `token -> claims | None`. The default is the
JWKS verifier above, but in tests you inject a fake so there's no IdP to reach:

```python
from arvel.auth.oidc import OidcGuard

async def fake_verifier(token):
    return {"sub": "kc-1", "email": "ada@acme.com", "email_verified": True, "groups": ["/eng"]}

principal = await OidcGuard(fake_verifier, provider="keycloak").verify(request_with_bearer)
```

## Common mistakes & gotchas

- **Decoding without validating.** Never trust an unvalidated JWT. The guard *only* returns claims
  that passed signature + `iss` + `aud` + `exp` — a bare `jwt.decode` without verification is a
  forged-token hole. Use the guard; don't hand-roll it.
- **Tokens with no `exp`.** The verifier **requires** `exp` (plus `iss`/`aud`/`sub`), so a token
  missing an expiry is rejected rather than treated as living forever.
- **A tenant-influenced `jwks_uri`.** Keep `jwks_uri` a trusted, operator-set constant — never derive
  it from the request, or you've built an SSRF and a "trust any issuer" hole.
- **Using `email` as the identity key.** The join key is `sub` (`subject_claim`); emails change. Email
  is only for *linking* a verified address to an existing account.
- **Confusing the access token and the id token.** Send whichever your IdP signs and you've
  configured `audience` for (for Keycloak, typically the access token); both validate the same way.

## How it works

The `oidc` guard pulls the `Bearer` token from the `Authorization` header and runs it through a
`ClaimsVerifier`. The default `jwks_verifier` builds a `PyJWKClient` **once** (it caches the IdP's
signing keys with a TTL — no per-request fetch) and calls `jwt.decode` with the configured `issuer`,
`audience`, a small clock `leeway`, and `options={"require": ["exp", "iss", "aud", "sub"]}`; any
`PyJWTError` becomes `None` (fail closed, no leaked reason). pyjwt is imported lazily inside the
verifier, so the OIDC guard never pulls crypto into arvel's light core.

## See also

- [Guards & drivers](guards.md) — the guard contract the `oidc` driver implements.
- [Identities & account linking](identities.md) — turning the validated `sub` into a `User`.
- [Mapping IdP groups to roles](idp-roles.md) — turning the `groups` claim into authorization.
