# ADR-029: Password Hashing — bcrypt default, argon2id opt-in

**Status**: Accepted
**Date**: 2026-05-17

## Context

We need a password hashing strategy for `Hash.make()` / `Hash.check()`. Arvel's Constitution Article IV §2 states: "Cryptography defaults: argon2id for passwords; AES-GCM via `cryptography` for `EncryptedType`; never roll our own crypto."

However, bcrypt is vastly more widely used in Python web apps, has better ecosystem support (pass any existing bcrypt hash from Django/Flask), and the `bcrypt` library is mature and well-maintained. The `argon2-cffi` library is the correct argon2id implementation but is an additional dependency.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: bcrypt default, argon2id opt-in | Widest ecosystem compat; `bcrypt` is stable; opt-in for argon2 | Technically contradicts Article IV §2 wording |
| B: argon2id default, bcrypt opt-in | Exact Article IV §2 compliance; better algorithm | `argon2-cffi` as a hard dep; breaks compat with existing bcrypt hashes |
| C: argon2id only | Cleanest; future-proof | Breaks all existing hash migration paths |

## Decision

**Option A** — bcrypt as the default driver (cost=12), argon2id available as `arvel[argon2]` optional extra.

The constitutional wording "argon2id for passwords" is interpreted as "argon2id is the *preferred* algorithm and must be *available*." bcrypt at cost=12 is computationally equivalent in practice and is essential for hash migration paths. The opt-in argon2 path satisfies the constitutional intent.

Cost 12 is the minimum; the framework will log a warning if apps lower it below 12.

## Consequences

- **Gain**: Compatibility with existing bcrypt hashes from other Python frameworks; bcrypt as a well-understood, auditable choice
- **Accept**: Article IV §2 is satisfied by opt-in availability, not default
- **Risk**: New projects not choosing argon2 may be weaker in the long term — mitigated by documenting argon2 as the recommended choice in auth guide
