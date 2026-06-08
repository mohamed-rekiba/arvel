# WI-arvel-027 — Microsoft provider must not treat an absent email_verified claim as verified

- **Module**: 27 — arvel-oauth (`MicrosoftProvider`)
- **Complexity**: L2
- **Risk tier**: 3 (account takeover via unverified email auto-linking)
- **Data classification**: confidential (auth identity)
- **Status**: completed

## Problem

`OAuthAccountLinker` only attaches a provider identity to an existing local user
when the email is verified, and only adopts the provider email as the unique
account email when verified — explicitly to stop an unverified claim hijacking an
existing row. `OAuthUser.email_verified` defaults to `False` for the same reason.

`MicrosoftProvider.get_user` undermined that:

```python
email_verified=bool(data.get("email_verified", email is not None))
```

Microsoft Entra's `/oidc/userinfo` omits `email_verified`, and its
`email`/`preferred_username` is not guaranteed verified (guest/MSA/federated). So
the default (`email is not None`) made every Microsoft login "verified". An
attacker with an Entra account whose unverified email matches a victim's local
account would auto-link into that account.

Repro (userinfo without the claim): Microsoft → `email_verified=True`, while
Google → `False` for the same payload.

## Fix

Default to `False` when the claim is absent, matching Google/OIDC and the
DTO/linker contract; honour an explicit `email_verified: true`.

```python
email_verified=bool(data.get("email_verified", False))
```

## Acceptance criteria

- Microsoft userinfo lacking `email_verified` → `OAuthUser.email_verified is False`.
- Explicit `email_verified: true` is still honoured.
- Unverified Microsoft logins create a fresh user (synthetic
  `{provider_id}@microsoft.local`) instead of linking by email.
- ruff check + format, mypy, pyright clean; arvel-oauth suite green.

## Out of scope (reviewed, no change)

- GitHub `/user.email` verified assumption (GitHub constrains public email to
  verified addresses; falls back to `/user/emails`).
- Non-constant-time `state` comparison (single-use random token; matches Socialite).
- Apple id_token JWKS verification, OIDC userinfo flow, PKCE — already correct.

## Files

- `packages/arvel-oauth/src/arvel_oauth/providers/microsoft.py`
- `packages/arvel-oauth/tests/test_providers.py` (2 new Microsoft cases)
- `docs/site/docs/packages/oauth.md` (linker email-verification contract note)
