# OAuth2 social login

"Log in with Google." "Continue with GitHub." "Sign in with your company account." All of these are
the OAuth2 **authorization-code flow**: instead of taking a password, you bounce the user to a
provider, they approve, and the provider sends them back with a short-lived `code` that you exchange
for tokens. arvel's `OAuthProvider` is the client for that flow — it builds the outbound redirect and
performs the code exchange. This page covers configuring a provider, the redirect/callback dance, and
turning the result into a logged-in [`User`](identities.md).

!!! note "Install the extra"
    OAuth uses httpx-oauth (and authlib), in the `[oauth]` extra:

    ```bash
    uv add 'arvel[oauth]'
    ```

## OAuth vs OIDC — which piece do I want?

They're related but do different jobs; arvel gives you one for each:

| Goal | Use |
|---|---|
| **Obtain** a token by logging the user in through the provider (this page) | `OAuthProvider` — `[oauth]` |
| **Validate** a token a client already presents (an API checking a bearer JWT) | [`OidcGuard`](sso-oidc.md) — `[jwt]` |

OIDC is OAuth2 plus an identity layer, so for an OIDC provider (Keycloak, Google, Entra) the two
combine: `OAuthProvider` runs the redirect and returns an `id_token`; the OIDC verifier validates it.

## Configure a provider

Give `OAuthProvider` the client credentials and the provider's two endpoints:

```python
from arvel.auth.oauth import OAuthProvider

google = OAuthProvider(
    client_id=env("GOOGLE_CLIENT_ID"),
    client_secret=env("GOOGLE_CLIENT_SECRET"),
    authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    access_token_endpoint="https://oauth2.googleapis.com/token",
    scopes=["openid", "email", "profile"],
)
```

Already using one of httpx-oauth's provider-specific clients? Pass it straight in and skip the
endpoints:

```python
from httpx_oauth.clients.github import GitHubOAuth2

github = OAuthProvider(client=GitHubOAuth2(env("GH_CLIENT_ID"), env("GH_CLIENT_SECRET")))
```

## The flow: two routes

OAuth login is always a *start* route (send them to the provider) and a *callback* route (handle the
return). Use **`authorize_pkce`** — it builds the outbound URL *and* returns a one-time
`code_verifier` to stash in the session; `access_token` then replays that verifier to complete the
exchange:

```python
REDIRECT_URI = "https://acme.com/auth/google/callback"

async def oauth_start(request):
    url, verifier = await google.authorize_pkce(REDIRECT_URI, state=issue_state())  # CSRF state + PKCE
    request.session["_pkce_verifier"] = verifier         # stash for the callback
    return redirect(url)                                  # → the provider's consent screen

async def oauth_callback(request):
    check_state(request.query("state"))                  # verify the state you issued
    verifier = request.session.pop("_pkce_verifier", None)
    if verifier is None:                                 # no verifier → don't exchange (fail closed)
        return "Expired login", 400
    token = await google.access_token(request.query("code"), REDIRECT_URI, code_verifier=verifier)
    # token → {"access_token": ..., "id_token": ..., "expires_in": ..., ...}
```

Two independent defences are in play. **`state`** is yours to generate and check — it ties the
callback to the request you started (CSRF). **PKCE** (`authorize_pkce` sends an S256
`code_challenge`; `access_token` sends the matching `code_verifier`) binds the authorization *code*
to the client that began the flow, so an intercepted code can't be redeemed by anyone else. Keep
both. The plain `authorization_url`/`access_token` (without a verifier) still exist for non-PKCE
providers, but prefer PKCE wherever the provider supports it.

## Completing the login

What you do with `token` depends on the provider:

**OIDC providers (Keycloak, Google, Entra…)** return an `id_token` JWT. Validate it exactly like the
[OIDC guard](sso-oidc.md) does, then resolve it to a user and log in:

```python
from arvel.auth.oidc import jwks_verifier
from arvel.auth.identity import Principal

verify = jwks_verifier(jwks_uri=JWKS_URI, issuer=ISSUER, audience=CLIENT_ID)

async def oauth_callback(request):
    check_state(request.query("state"))
    token = await google.access_token(request.query("code"), REDIRECT_URI)

    claims = await verify(token["id_token"])      # validated claims, or None
    if claims is None:
        return "Invalid token", 401
    principal = Principal(provider="google", subject=claims["sub"], claims=claims)
    user = await users.resolve(principal)         # find-or-link-or-create (identities.md)
    auth.login(user)
    return redirect("/dashboard")
```

**Plain OAuth2 providers (e.g. GitHub)** don't issue an `id_token` — call the provider's userinfo
endpoint with the `access_token` via `fetch_userinfo`, then build the `Principal` from that response
(`subject` = the provider's stable user id) and `resolve` it the same way:

```python
from arvel.auth.oauth import fetch_userinfo
from arvel.auth.identity import Principal

profile = await fetch_userinfo(token["access_token"], "https://api.github.com/user")
principal = Principal(provider="github", subject=str(profile["id"]), claims=profile)
user = await users.resolve(principal)
```

From there the rest of the section takes over: the [user provider](identities.md) links or creates the
account, and the [claim→role map](idp-roles.md) can turn the provider's groups into roles.

## Common mistakes & gotchas

- **Skipping the `state` check.** Always generate a `state` on start and verify it on callback —
  without it the callback is CSRF-able. arvel passes `state` through; generating/checking it is yours.
- **Losing the PKCE verifier.** `authorize_pkce` returns a `code_verifier` you must stash (session)
  and pass to `access_token` on the callback. If it's missing, don't exchange the code — fail closed.
  Don't reuse a verifier across flows; mint a fresh one per start.
- **Trusting the token without validating.** An OIDC `id_token` must be signature/issuer/audience/
  expiry-checked (use [`jwks_verifier`](sso-oidc.md)) before you trust a single claim. Don't decode
  and believe it.
- **Mismatched `redirect_uri`.** It must byte-for-byte match what you registered with the provider
  *and* what you pass to both `authorization_url` and `access_token` — a mismatch fails the exchange.
- **Using email as the account key.** Link on the provider's stable `sub`/user-id
  (`AuthIdentity.subject`), not the email — see [Identities](identities.md).
- **Requesting more scopes than you need.** Ask only for what you use (`openid email profile` is
  usually enough); over-scoping is a consent-screen and privacy smell.

## How it works

`OAuthProvider` is a thin wrapper over an httpx-oauth `OAuth2` client (imported lazily, so `[oauth]`
stays out of the light core). `authorize_pkce` mints a `code_verifier` and its S256 `code_challenge`
(via `generate_pkce_pair`, stdlib `secrets`/`hashlib`) and delegates to the client to build the
provider URL with your `redirect_uri`, `state`, `scope`, and the challenge; `access_token` performs
the code-for-token exchange, replaying the `code_verifier`, and returns the provider's token response
as a dict. `fetch_userinfo` is a bearer GET of the userinfo endpoint via the framework `http` client
(falling back to a lazy `httpx` client when no app is running). It
deliberately stops there — it *obtains* the token; **you** validate it and call the
[user provider](identities.md). Unlike the
[`oidc` guard](guards.md), it isn't registered in the `GuardManager`, because the interactive flow
needs your two routes and your `state`/session handling around it.

## See also

- [Single sign-on (OIDC / Keycloak)](sso-oidc.md) — validating the token this flow obtains.
- [Identities & account linking](identities.md) — turning the provider's `sub` into a `User`.
- [Mapping IdP groups to roles](idp-roles.md) — turning the provider's groups into authorization.
- [Routes & flows](routes-and-flows.md) — where this sits among the other auth routes.
