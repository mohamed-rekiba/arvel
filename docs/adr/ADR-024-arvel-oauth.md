# ADR-024 — `arvel-oauth`

**Status**: Accepted
**Date**: 2026-06-07 (first written down here; the package itself shipped earlier as pre-alpha)
**Scope**: All architectural decisions for the `arvel-oauth` package — package shape, the OAuth2 / OIDC flow, the provider abstraction and the registry, identity linking to the host `User`, at-rest token encryption, and the deliberately unmounted HTTP surface.

## Why this is one ADR

`arvel-oauth` adds social login to Arvel. Six tightly-coupled decisions shape what it does and what it pointedly *doesn't* do (no auto-mounted routes, no parallel auth path, no token refresh service). Splitting them across files would obscure how each one falls out of the previous one, so they live here in `§` sections.

---

## § 1 — Authorization-code flow with PKCE S256 + signed state cookie. No password grant. No implicit.

### Context

OAuth2 has multiple flows. For server-side web apps, the choice in 2026 is essentially:

- **Authorization code + PKCE**: the modern recommendation. PKCE prevents code interception; works for confidential and public clients.
- **Authorization code without PKCE**: still common for server-rendered apps with a strong client secret. Vulnerable to code-interception attacks if the redirect URI is ever compromised.
- **Implicit**: deprecated by OAuth 2.1. We won't support it.
- **Resource owner password**: also deprecated. Out of scope.

PKCE for confidential clients is overkill in theory but cheap in practice — a single code-verifier round-trip — and it shuts down a class of attacks where a malicious browser extension or a misconfigured redirector reaches the auth code before the legit client. OAuth 2.1 mandates PKCE for *all* clients.

### Decision

The package speaks **authorization code with PKCE (`S256`) only**. PKCE is enabled by default (`OAUTH_USE_PKCE=true`), with an opt-out for hand-rolled SDK providers that haven't caught up yet. The `state` parameter is mandatory: `pkce.generate_state()` is set as a signed, HttpOnly cookie before redirect; the callback compares cookie-state to query-state and rejects mismatches.

Verifier entropy: `secrets.token_urlsafe(96)` — RFC 7636 specifies ≥43 chars; we use 128 chars (>128 bits). Challenge: `base64url(sha256(verifier))` with no padding. No `plain` challenge method.

### Consequences

- The package conforms to OAuth 2.1 and the IETF BCP for native and server apps without any per-app code.
- `state` mismatch raises `InvalidOAuthState` and the caller returns the user to `OAUTH_ERROR_REDIRECT_URL`. No silent fall-through.
- GitHub historically didn't enforce PKCE; we still send it (per `OAUTH_USE_PKCE`), and the GitHub provider was tested against the live endpoints.
- Apple's flow uses `id_token` from the verified response — we don't hit a userinfo endpoint for Apple.
- We don't ship token refresh or revocation flows. Apps that need them implement them on top of `OAuthAccount.tokens`. Documented intentional gap; revisit if a real use-case appears.

### Alternatives considered

- **Skip PKCE for confidential clients**: smaller code path, marginally less round-trip work. Rejected — PKCE is now baseline for OAuth, and the cost is invisible.
- **Support multiple grants** (password, client-credentials): out of scope. `arvel-oauth` is for end-user social login. Service-to-service auth lives in framework `auth` (ADR-010).

---

## § 2 — Provider abstraction is a Pydantic-friendly base class, not a registry of strings

### Context

Five named providers ship: Google, GitHub, Microsoft, Apple, generic OIDC. Two ways to model that:

1. **Strategy / registry**: `register_provider("google", GoogleProvider)` — providers identified by string names, lookup at runtime.
2. **Concrete classes** as the public API: `GoogleProvider(...)`, with the manager only acting as a "give me the configured one for this name".

### Decision

`OAuthProvider` is a base class. `GoogleProvider`, `GitHubProvider`, `MicrosoftProvider`, `AppleProvider`, `OIDCProvider` are concrete subclasses. `OAuthManager` builds them on demand from `OAuthConfig`:

```python
manager.provider("google")   # GoogleProvider
manager.configured_providers()  # ["google", "microsoft"]  (those with creds set)
```

`OIDCProvider` is special — it builds via `await OIDCProvider.discover(issuer=...)` because it must fetch `.well-known/openid-configuration` first. The manager exposes that as `await manager.oidc()` rather than the synchronous `manager.provider(...)` to make the discovery cost obvious.

Adding a new provider is a class, not a hash-map insert.

### Consequences

- Strong typing. `manager.provider("google")` returns `OAuthProvider`, but a user who knows the concrete need can call the constructor directly with full type hints on `client_id` etc.
- A provider without credentials configured is invisible — `configured_providers()` doesn't list it, and `manager.provider("google")` raises `ProviderNotFound`. There's no "configured but broken" middle state.
- Five providers is a lot to maintain by hand, but each one is ~80 lines of HTTP-client + token-exchange + userinfo-mapping. The cost is bounded.
- No third-party plugin model. A consumer who needs Twitter / Discord / etc. subclasses `OAuthProvider` in their app, instantiates it, and registers it on `OAuthManager` themselves. Documented as the "advanced" path.

### Alternatives considered

- **String-keyed registry**: easier to extend at runtime, weaker static typing, and most apps need ≤2 providers anyway.
- **Pure async factory functions**: looked clean until we needed inheritance for things like Apple's JWT-client-secret signer. Subclasses won.

---

## § 3 — Link OAuth identities to the existing `User` via a separate `oauth_accounts` table — never replace the auth system

### Context

Two ways to link a provider identity (`provider`, `provider_id`) to the host:

1. **Embed in `users` table**: add `provider`, `provider_id`, `oauth_tokens` columns. Simple, but couples auth to OAuth and prevents one user from having multiple linked providers.
2. **Separate join table** (`oauth_accounts`): `(provider, provider_id)` UNIQUE, `user_id` FK to `users`. Many-to-one: a user can have Google *and* GitHub.

### Decision

A separate `oauth_accounts` table, owned by the package's installable migration:

```
oauth_accounts:
    id           PK
    user_id      FK → users.id (CASCADE)
    provider     varchar(40)
    provider_id  text             -- stored verbatim, never normalised
    tokens       text             -- AES-GCM-encrypted JSON, see § 5
    created_at, updated_at        -- Timestamps mixin
    UNIQUE (provider, provider_id)
```

`OAuthAccountLinker.link(oauth_user, token)` is a pure async method on `AsyncSession`. It does find-or-create:

1. If an `OAuthAccount` already exists for `(provider, provider_id)` → refresh its tokens, return it.
2. Otherwise, look up an existing `User` by **verified** email; reuse if present.
3. Otherwise, create a new `User` with the provider's name + a placeholder password (`secrets.token_urlsafe(32)`).

After linking, the package issues a **standard JWT session via `AuthService`** — it does *not* create a parallel auth system.

### Consequences

- One user can link multiple providers without schema changes.
- A user without an OAuth account stays a normal user. Authentication has one concept (the `User`), not "OAuth user vs password user".
- The same `AuthService` powers both flows, so guards, refresh tokens, and `Auth::user()` work identically — no special-casing in app code.
- Email-based account adoption is gated on `email_verified`. An unverified Google email cannot be used to claim an existing user with the same address. Tested in `test_install_and_model.py`.
- New users created from OAuth get an unusable password placeholder (random 32-byte token). They can't log in via password without a reset.
- `provider_id` is stored verbatim — providers are inconsistent about case-folding (GitHub IDs are numeric strings, Google's are giant integers as strings, Apple uses opaque user IDs). Normalising would risk collisions; we don't.
- `(provider, provider_id)` race in `link()`: two concurrent first-time logins for the same identity. The migration's UNIQUE constraint catches it; we re-raise as `DuplicateOAuthAccount` and let the caller decide what to do.

### Alternatives considered

- **Columns on `users`**: rejected. One-provider-per-user is too restrictive, and it bakes OAuth-specific columns into a table that should stay generic.
- **Replacing `AuthService`**: rejected. We'd be re-implementing JWT issuance, refresh, password-reset, etc., for a feature that should be additive.
- **Creating a separate `oauth_users` model**: rejected. App code would need to query both tables; `Auth::user()` would have to choose one.

---

## § 4 — Routes are not auto-mounted. Apps wire their own controller.

### Context

Most "social login for framework X" packages ship a route module that auto-registers `/auth/{provider}/redirect` and `/auth/{provider}/callback`. It's convenient on day one and a maintenance trap forever. Question of taste vs reach:

- **Auto-mount** with config knobs to disable / rename: easy install, leaks routing decisions into the package.
- **Build-your-own controller** with helpers: extra ceremony at install, full control of cookie names, redirect URLs, error rendering, intermediate consent screens, etc.

### Decision

Don't auto-mount. The package exposes `OAuthController` and `register_oauth_routes(router, controller)` helpers, and the docs walk through wiring them in the app's HTTP setup:

```python
controller = OAuthController(manager=manager, config=config, auth=auth_service)
register_oauth_routes(router, controller)
```

### Consequences

- The app decides the URL prefix, the redirect targets after success/failure, the controller's authentication context, and the cookie names. The package never quietly defines `/auth/{provider}` for you.
- Slightly higher install friction (one extra file). The friction is the *point* — wiring auth is exactly the call you want to make explicitly.
- Tests run against an `OAuthController` instance directly, with no router. The HTTP-level tests use FastAPI's `TestClient` against a hand-wired router fixture.
- Easy to add features the package doesn't ship: an intermediate "are you sure?" page, account-merge confirmation, an audit hook on every linked account.

### Alternatives considered

- **Auto-mount with a "disable" config flag**: rejected. The flag would be set in 100% of apps that care about their routing.
- **Auto-mount under a fixed prefix and trust the app to override**: rejected. Routing collisions / duplicate routes are quiet errors.

---

## § 5 — Tokens stored encrypted at rest with `EncryptedJson` (AES-256-GCM, keyed from `APP_KEY`)

### Context

Provider tokens (access + refresh + id_token) are sensitive. They give access to the user's third-party account, often with broader scopes than needed. The DB row is far more attractive than the user's password column (which is hashed and useless in cleartext).

### Decision

The `OAuthAccount.tokens` column is a `EncryptedJson` `TypeDecorator`. On bind: `Crypt.encrypt_string(json.dumps(value))`. On read: the inverse. The encryption key resolves lazily at bind/result time, so importing the model doesn't require `APP_KEY` to be present (necessary for migration tooling and tests).

### Consequences

- A DB dump alone doesn't expose tokens. An attacker also needs `APP_KEY`.
- The package's crypto is a thin wrapper over the framework's `Crypt` facade — same cipher, same MAC, same key rotation story (ADR-007 § 6).
- Reads decrypt transparently; the public API of `OAuthAccount` exposes a plain dict.
- `tokens` is `None`-tolerant: passing `None` short-circuits both bind and result. Useful for tokens that haven't been issued yet (some flows update them later).
- A bad `APP_KEY` (rotated without re-encrypting) yields a decryption error at read time. Documented; the rotation playbook (ADR-007 § 6) covers `Crypt::reEncryptDatabase()`.

### Alternatives considered

- **Plaintext column with file-system encryption only**: rejected. DB backups bypass file-system encryption. Tokens are exactly the kind of thing you don't want in a backup blob.
- **One-way hash**: useless — we need the actual token to call the provider's API.

---

## § 6 — Generic OIDC discovers via `.well-known`. No per-issuer hardcoding.

### Context

Five named providers cover the common cases. Beyond that, OIDC issuers are a long tail: Auth0, Okta, Keycloak, internal SSO, on-prem Azure ADFS, etc. Each has its own URLs but they all ship the same `.well-known/openid-configuration` document.

### Decision

`OIDCProvider.discover(issuer=...)` is an async classmethod that fetches the well-known document, validates it, and instantiates a provider with the right endpoints. `OAuthManager.oidc()` exposes it.

The provider counts as "configured" once `OIDC_ISSUER_URL` and `OIDC_CLIENT_ID` are set; the rest of the URLs come from discovery. `OAUTH_OIDC_ALLOW_HTTP_ISSUER` is an opt-in for local dev (`http://localhost:8080/realms/test`), defaulting to `false` (HTTPS-only).

### Consequences

- Adding support for a new OIDC issuer is *configuration*, not code.
- Discovery costs one HTTP round-trip per process per issuer. We don't cache between processes (no shared cache requirement) but it would be a small perf win to add later.
- Misconfigured issuers (typos, wrong URL, no `.well-known`) raise `OIDCDiscoveryError` at first use, not at boot. Acceptable: discovery is on the request path of the first user who clicks "log in", and we'd rather fail loudly there than at server start.
- The named providers don't go through `discover()` — their endpoints are stable enough to hardcode and we'd rather not add a network round-trip to the Google / GitHub / Microsoft path.

### Alternatives considered

- **No generic OIDC; only ship named providers**: rejected. The long tail is too long to enumerate.
- **Lazy-load even the named providers via discovery**: rejected. Google's well-known never changes; the round-trip is dead weight.

---

## Cross-references

- ADR-001 § 4 (single-`arvel` package + extras): `arvel[oauth]` follows the framework's package strategy.
- ADR-007 § 6 (EncryptedType: AES-GCM) and § 7 (Crypt facade): § 5 above reuses both.
- ADR-010 (Auth subsystem): § 3 issues sessions through the same `AuthService`; § 4 mounts on top of the same routing primitives.
- ADR-010 § 5 (email validation at boundary) — provider emails are validated as input, not assumed.
- User-facing docs: `docs/site/docs/packages/oauth.md`.
