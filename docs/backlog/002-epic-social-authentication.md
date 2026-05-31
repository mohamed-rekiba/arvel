# Epic 002: Social Authentication (`arvel-auth-social`)

## Summary

A new companion package (`arvel-auth-social`) that adds OAuth2/OIDC social login to arvel apps.
Ships built-in providers for Google, GitHub, Microsoft, and Apple, plus a generic OIDC provider
for any issuer that exposes a `.well-known/openid-configuration` document. PKCE is enforced by
default. Social accounts are linked to the app's existing user model via an installable migration.

---

## Stories

### Story 1: Built-in OAuth2 provider configuration

**As a** framework user,
**I want** to configure Google, GitHub, Microsoft, and Apple as social login providers via environment variables,
**so that** I can add social login without writing OAuth redirect and token exchange logic myself.

**Acceptance Criteria**:
- [ ] Given `SOCIAL_GOOGLE_CLIENT_ID` and `SOCIAL_GOOGLE_CLIENT_SECRET` are set, when `SocialAuthManager.provider("google")` is called, then a fully configured `GoogleProvider` is returned
- [ ] Given `SocialAuthManager` is resolved from the container, when `provider.get_authorization_url(state, code_challenge)` is called, then a valid Google authorization URL with PKCE challenge is returned
- [ ] Given a valid authorization code is exchanged, when `provider.exchange_code(code, code_verifier)` is called, then an `OAuthToken` is returned with `access_token` and optionally `id_token`
- [ ] Given a valid access token, when `provider.get_user(token)` is called, then an `OAuthUser` is returned with `provider`, `provider_id`, `email`, and `name` populated
- [ ] Given GitHub is configured (no `id_token`), when `provider.get_user(token)` is called, then `OAuthUser` is returned using the GitHub userinfo API (not OIDC claims)
- [ ] Given Apple is configured, when `provider.get_user(token)` is called, then user data is extracted from the `id_token` JWT (Apple does not provide a userinfo endpoint)
- [ ] Given an unknown provider name is requested, when `SocialAuthManager.provider("unknown")` is called, then a descriptive `SocialProviderNotFound` exception is raised

**Security Requirements**:
- [ ] Client secrets must be loaded from environment variables only — no hardcoded values
- [ ] Authorization state parameter must be a cryptographically random 32-byte hex value; mismatches on callback must raise `InvalidOAuthState`
- [ ] PKCE code verifier must be ≥ 43 characters (RFC 7636 §4.1)

**Documentation Requirements**:
- [ ] Add `docs/site/docs/social-auth.md` with provider configuration table and env var reference

**Requirement Refs**: Brainstorm design § Phase 2A
**Priority**: Must
**Complexity**: Large
**Status**: Done

---

### Story 2: OAuth2 redirect and callback HTTP flow

**As an** end user,
**I want** to click "Sign in with Google" and be redirected to Google's consent screen, then returned to the app after approval,
**so that** I can authenticate without creating a separate password.

**Acceptance Criteria**:
- [ ] Given `GET /auth/google/redirect` is called, when the controller runs, then the user is redirected to Google's authorization URL with a `state` cookie set
- [ ] Given `GET /auth/google/callback?code=...&state=...` is called with a valid state, when the controller runs, then the code is exchanged, the user profile is fetched, and a session/JWT is issued
- [ ] Given the callback state does not match the cookie, when the controller runs, then HTTP 422 is returned and no session is created
- [ ] Given the provider returns an error (e.g., `error=access_denied`), when the callback controller runs, then the user is redirected to a configurable `SOCIAL_ERROR_REDIRECT_URL`
- [ ] Given a first-time user authenticates via social login, when no matching `SocialAccount` exists, then a new `SocialAccount` is created and linked to either a new `User` or an existing `User` with the same verified email
- [ ] Given an existing user authenticates again via the same provider, when the callback runs, then the existing `SocialAccount` is updated (`updated_at`, `raw` tokens) and no duplicate is created

**Security Requirements**:
- [ ] The `state` parameter must be stored in an `HttpOnly`, `SameSite=Lax` cookie and compared server-side — never trusted from the query string alone
- [ ] `SocialAccount` must not store raw access tokens in plaintext; use the encrypted column type (`EncryptedType`) if token storage is required
- [ ] Email claim from the provider must be treated as unverified unless the provider explicitly marks it as verified (Google `email_verified`, GitHub primary+verified email)

**Documentation Requirements**:
- [ ] Add redirect/callback route examples to `docs/site/docs/social-auth.md`

**Requirement Refs**: Brainstorm design § Phase 2A
**Priority**: Must
**Complexity**: Medium
**Status**: Done

---

### Story 3: PKCE enforcement by default

**As a** framework user,
**I want** PKCE to be used automatically for all providers that support it,
**so that** authorization code interception attacks are mitigated without me having to opt in.

**Acceptance Criteria**:
- [ ] Given any provider with `use_pkce=True` (the default), when `get_authorization_url(state)` is called, then a `code_challenge` (S256 method) is included in the URL and the `code_verifier` is stored in session/cookie
- [ ] Given the authorization code is exchanged, when `exchange_code(code)` is called, then the stored `code_verifier` is included in the token request
- [ ] Given Apple (which requires client-secret JWT), when PKCE is used, then the client secret is the signed JWT — not the raw secret string
- [ ] Given a provider config with `use_pkce=False`, when `get_authorization_url` is called, then no `code_challenge` is included (explicit opt-out respected)

**Security Requirements**:
- [ ] PKCE verifier must use `secrets.token_urlsafe(96)` (≥ 128 bits of entropy, URL-safe)
- [ ] S256 challenge = `base64url(sha256(verifier))` per RFC 7636 — no plain method support

**Documentation Requirements**:
- [ ] Document PKCE default behavior and opt-out in `docs/site/docs/social-auth.md`

**Requirement Refs**: Brainstorm design § Phase 2A
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

### Story 4: Generic OIDC provider via auto-discovery

**As a** framework user,
**I want** to configure any OIDC-compliant provider (Keycloak, Auth0, Okta) by supplying only the issuer URL,
**so that** I can integrate enterprise IdPs without manually looking up authorization, token, and userinfo endpoints.

**Acceptance Criteria**:
- [ ] Given `SOCIAL_OIDC_ISSUER_URL=https://my-keycloak.example.com/realms/myrealm` is set, when `SocialAuthManager.provider("oidc")` is called, then `discover_oidc_config(issuer_url)` fetches `{issuer}/.well-known/openid-configuration` and populates endpoint URLs
- [ ] Given the discovery document is fetched, when it contains `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint`, then the provider uses them without further configuration
- [ ] Given a discovery document with a trailing slash on the issuer URL, when `discover_oidc_config` is called, then it handles the trailing slash without a double-slash in the constructed URL
- [ ] Given the discovery endpoint is unreachable, when `discover_oidc_config` is called, then `OIDCDiscoveryError` is raised with the issuer URL and HTTP status in the message
- [ ] Given the discovery document is fetched, when the provider authenticates a user, then OIDC claims are extracted from the `id_token` if present, with `userinfo` as fallback

**Security Requirements**:
- [ ] Discovery must only be performed over HTTPS; HTTP issuer URLs must be rejected unless `SOCIAL_ALLOW_HTTP_ISSUER=true` (dev only)
- [ ] `id_token` JWT must be validated (signature, `iss`, `aud`, `exp`) using the provider's JWKS endpoint before trusting claims

**Documentation Requirements**:
- [ ] Add generic OIDC section to `docs/site/docs/social-auth.md`

**Requirement Refs**: Brainstorm design § Phase 2A
**Priority**: Should
**Complexity**: Medium
**Status**: Done

---

### Story 5: Social account linking and `auth:social:install` command

**As a** framework user,
**I want** an `arvel auth:social:install` command that publishes the `social_accounts` migration and stubs,
**so that** I can add social login to an existing app without manually writing the linking table.

**Acceptance Criteria**:
- [ ] Given `arvel auth:social:install` is run, when the command completes, then a migration file for `social_accounts` is published to `db/migrations/`
- [ ] Given the migration runs, when the table is created, then it has columns: `id`, `user_id` (FK → users), `provider`, `provider_id`, `tokens` (encrypted), `created_at`, `updated_at`; and a unique constraint on `(provider, provider_id)`
- [ ] Given two users attempt to link the same provider account, when `SocialAccount` insert runs, then the unique constraint prevents the duplicate and a `DuplicateSocialAccount` exception is raised
- [ ] Given a user has multiple social accounts (Google + GitHub), when queried, then all are returned and each can be used to authenticate independently
- [ ] Given a social account is deleted, when the user attempts to log in via that provider, then a new `SocialAccount` is created (no orphaned linking)

**Security Requirements**:
- [ ] `tokens` column must use `EncryptedType` (AES-GCM cast) — never plaintext
- [ ] `provider_id` must be stored as-is from the provider — never modified or normalised (prevents ID collision attacks)

**Documentation Requirements**:
- [ ] Add `arvel auth:social:install` to `docs/site/docs/social-auth.md`

**Requirement Refs**: Brainstorm design § Phase 2A
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

## Dependencies

- Depends on Epic 001 Story 1 (`context/` module) — callback controller writes `user_id` to context after social login
- Depends on Epic 001 Story 2 (session-scoped logging) — auth events carry `user_id` in logs
- Requires `arvel` core `auth/` module (JWT issuance, `AuthBroker`) for post-social-login session creation
- `SocialAccount` model requires `EncryptedType` from `arvel.database` casts

## Notes

- `SocialAuthServiceProvider` is a companion provider — not in core baseline
- Old `arvel_old/auth/oauth.py` contracts and DTOs are direct ports; HTTP flow and concrete providers are new
- Apple sign-in requires client-secret JWT generation (ES256, `team_id`, `key_id`) — documented separately
