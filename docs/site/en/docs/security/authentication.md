# Authentication

Authentication answers **who is calling**. Arvel’s **`AuthManager`** holds named **`GuardContract`** implementations—**`JwtGuard`** for Bearer tokens, **`ApiKeyGuard`** for header or query API keys—and picks a **default** guard for middleware that does not specify a name.

The stack lines up with Laravel’s idea of guards and drivers, but stays explicit: you register guards when the app boots, resolve them per request, and combine them with **OAuth2/OIDC** flows where users arrive via an identity provider.

## AuthManager

Construct **`AuthManager`** with a mapping of guard names to instances and a **`default`** key. Request middleware asks **`auth_manager.guard()`** (or **`guard("jwt")`**) to obtain the active guard.

```python
from arvel.auth.auth_manager import AuthManager
from arvel.auth.contracts import GuardContract


def build_auth_manager(guards: dict[str, GuardContract]) -> AuthManager:
    return AuthManager(guards=guards, default="jwt")
```

The manager freezes the mapping—**no late registration**—so behavior stays predictable across workers.

## JWT guard

**`JwtGuard`** validates **`Authorization: Bearer`** tokens, typically against your signing keys and issuer/audience rules from settings. Claims feed into user resolution and downstream authorization.

## API keys

**`ApiKeyGuard`** suits service-to-service calls: stable secrets rotated out of band, scopes carried alongside keys in your persistence layer. Treat keys like passwords: hash at rest, rate-limit validation endpoints, and never log raw values.

## OAuth2 and OIDC

**`arvel.auth.oauth`** defines **`OAuthProviderContract`**, token/user DTOs, provider configs (Google, GitHub, Microsoft, Apple helpers), **`OIDCDiscoveryDocument`**, and **`fetch_oidc_discovery`** for **`.well-known/openid-configuration`**. You register providers on **`OAuthProviderRegistry`** and wire routes that redirect, exchange codes with PKCE, and establish a session or issue your own tokens.

```python
# Illustrative — see your app’s routes and settings for wiring
from arvel.auth.oauth import OAuthProviderRegistry


registry = OAuthProviderRegistry()
# registry.register(...)
```

## Practical guidance

- Prefer **short-lived access tokens** and refresh or re-auth on expiry
- Validate **iss**, **aud**, **exp** on JWTs
- Use **HTTPS everywhere** tokens travel
- Combine authentication with **policies** and **`Gate`** (see the Authorization page) so “logged in” is not confused with “allowed”

Arvel gives you the hooks; your threat model decides how strict the pipeline must be.

## CSRF protection

**`CsrfMiddleware`** protects **state-changing** methods (`POST`, `PUT`, `PATCH`, `DELETE`) with a **double-submit cookie** pattern and **`Origin`** checks. Clients send **`X-CSRF-Token`** (or a form field) with a token generated via **`generate_csrf_token`**, verified by **`verify_csrf_token`**. Exclude JSON APIs that use **Bearer** tokens through **`exclude_paths`** so machine clients are not blocked.

## Rate limiting

**`RateLimitMiddleware`** applies **sliding-window** limits per IP or per user, with rules like **`5/minute`** parsed by **`RateLimitRule`**. Use it on login, password reset, and any expensive endpoint bots love. Pair limits with **account lockouts** and **CAPTCHA** only when your abuse model demands it—middleware alone is not a full fraud strategy.
