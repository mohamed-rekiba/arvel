# Epic: Encrypter.decrypt_string must raise DecryptionError for any bad payload

## Summary
The app `Encrypter` documents `DecryptionError` as its failure type, but
`decrypt_string` ran `base64.b64decode(payload)` outside its try/except, so a
non-base64 payload leaked a raw `binascii.Error`. Its sibling column type
(`database.casts.EncryptedType`) already funnels every malformed input into
`DecryptionError`, and Laravel's `Encrypter::decrypt` raises `DecryptException` for any
invalid payload. A caller decrypting attacker-controlled input via the `Crypt` facade
and catching `DecryptionError` would have the `binascii.Error` escape as an uncaught
500. The base64 decode is now wrapped so every malformed payload raises
`DecryptionError`.

**Module:** encryption · **Spec:** `docs/pipeline/specs/WI-arvel-015-decrypt-error-contract.md`

## Stories

### Story 1: Decryption fails with one predictable error
**As a** developer decrypting untrusted input, **I want** every invalid payload to raise
`DecryptionError`, **so that** a single `except DecryptionError` handles malformed,
tampered, wrong-version, and wrong-key input without leaking `binascii.Error`.

**Acceptance Criteria**:
- [x] Given a non-base64 / wrong-length / empty payload, when decrypted, then `DecryptionError` is raised (not `binascii.Error`).
- [x] Given an unknown version byte, a wrong key, or a tampered tag, when decrypted, then `DecryptionError` is raised.
- [x] Given a valid payload, when decrypted, then it round-trips unchanged.

**Security Requirements**:
- [x] Untrusted ciphertext can't escalate a decode failure into an uncaught 500 (A10 mishandling exceptional conditions).
- [x] AEAD authentication unchanged — tampering still fails closed.

**Documentation Requirements**:
- [x] `docs/site/docs/features/encryption.md` states `DecryptionError` covers malformed base64, unknown version, wrong key, and tampering.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3, SPEC-4, SPEC-5
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..014.

## Notes
- Folded-in: added `tests/encryption/` — the `Encrypter` had no direct unit coverage.
- Deferred follow-ups (separate work items):
  - **`decrypt()` JSON parse failure** surfaces `json.JSONDecodeError` (API misuse on a
    valid-key payload, not attacker input).
  - **`from_app_key()` malformed `APP_KEY`** raises `binascii.Error` (operator config,
    not request input).
