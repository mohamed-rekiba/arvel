# ADR-085: Personal Access Token Storage — SHA-256 + Sanctum Pattern

**Status**: Accepted
**Date**: 2026-05-17

## Context

`HasApiTokens.create_token()` must generate a token and store it securely. Options are: store plain text, store encrypted, or store a hash. The token is effectively a credential — it must be treated like a password.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Store plain text | Trivial token revocation check | DB breach exposes all tokens |
| B: Store encrypted (AES-GCM) | Recoverable; revocation easy | Encryption key becomes single point of failure; key rotation is expensive |
| C: Store SHA-256 hash (Sanctum pattern) | DB breach useless (hashes aren't reversible); no key management | Plain text shown once only — lost token requires new token |

## Decision

**Option C** — SHA-256 hash stored, plain text shown once (Sanctum pattern).

`secrets.token_urlsafe(40)` generates 320 bits of entropy — brute-forcing SHA-256(token) from the hash is computationally infeasible. Timing-safe comparison via `hmac.compare_digest` prevents timing oracles. This is the same design used by Laravel Sanctum and GitHub personal access tokens.

Token generation:
```python
plain_text = secrets.token_urlsafe(40)
token_hash = hashlib.sha256(plain_text.encode()).hexdigest()
```

Verification:
```python
candidate_hash = hashlib.sha256(bearer.encode()).hexdigest()
stored_hash = record.token
if not hmac.compare_digest(candidate_hash, stored_hash):
    return None
```

## Consequences

- **Gain**: DB breach does not expose tokens; no encryption key to manage
- **Accept**: Lost tokens cannot be recovered — users must generate a new one
- **Risk**: None significant at this entropy level
