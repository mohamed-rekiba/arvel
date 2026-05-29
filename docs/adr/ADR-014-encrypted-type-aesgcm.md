# ADR-014 — EncryptedType: AES-GCM with random + deterministic modes

**Status**: Accepted
**Date**: 2026-05-17

## Context

`EncryptedType` lets developers store sensitive data (SSNs, API keys,
private notes) encrypted at rest. Two patterns are needed:

1. **Random mode** (default): each write uses a fresh random IV. Resulting
   ciphertexts are different for the same plaintext. Maximally secure but
   not searchable by exact equality.
2. **Deterministic mode** (opt-in): each write uses an IV derived from the
   row's PK + a per-column salt. Same plaintext on the same row → same
   ciphertext, so a `WHERE col = ?` against the encrypted column works for
   exact-match queries. Leaks equality but enables search.

Options for the AEAD primitive:

| Option | Pros | Cons |
|---|---|---|
| A. `cryptography.fernet` (AES-128-CBC + HMAC) | Easiest API | 128-bit key only; padded ciphertext leaks length; deterministic mode unnatural |
| B. **`cryptography.hazmat.primitives.ciphers.aead.AESGCM`** | 256-bit; AEAD (integrity for free); efficient; standard | Lower-level — we own the IV / AAD logic |
| C. `nacl.secret.SecretBox` (XSalsa20-Poly1305) | Simple | Different cipher family than the rest of the ecosystem; deterministic mode harder |

## Decision

Option B — **AES-GCM via `cryptography`**, 256-bit key.

**Wire format (shipped in WI-003 with Stage 4b hardening)**:

```
b64( VERSION(1) || KEY_ID_LEN(1) || KEY_ID(N) || IV(12) || CT_WITH_TAG )
```

- `VERSION = 0x01` — single byte, lets future formats coexist on disk during a rolling
  migration.
- `KEY_ID` — ASCII string identifying which key was active when the row was
  written. Defaults to `"v1"`. Mismatched key-ids raise
  `DecryptionError` (never silent corruption).
- `IV` — 12-byte AES-GCM nonce (see modes below).
- `CT_WITH_TAG` — ciphertext concatenated with the 16-byte GCM tag.
- Optional `associated_data` is passed to GCM as AAD; recommended pattern
  is `EncryptedType(key, associated_data=f"{table}.{column}".encode())` so
  ciphertext copied from a different column fails to decrypt.

**Random mode (default)**:
- Generate 12-byte IV via `os.urandom(12)`.
- Encrypt: `aesgcm.encrypt(iv, plaintext, associated_data=aad)`.

**Deterministic mode (`deterministic=True`)**:
- IV: `SHA256(key || plaintext)[:12]`. Same plaintext → same IV → same
  ciphertext. Exact-match searchable but leaks equality.
- Same AAD discipline applies — copied ciphertext from another column
  still fails to decrypt.

**Key sourcing**:
- Master key: `settings.app.secret_key` (`SecretStr`, 32 bytes from URL-safe
  Base64; if shorter, HKDF-expand to 32).
- Per-column derived key:
  `HKDF(SHA256, length=32, salt=column_salt, info=f"col:{table}.{column}").derive(master)`.
- `column_salt` is a static 16-byte value compiled into the model class
  (auto-derived from a stable hash of `f"{table}.{column}"`).

**Key rotation**:
- Document the procedure in `docs/concepts/arvent.md`. Outline:
  1. Add `secondary_key` config field.
  2. On read, try primary key first; fall back to secondary.
  3. Run `arvel db:rotate-encryption <model>.<col>` (WI-004) to re-encrypt
     all rows with the primary key.
  4. Remove `secondary_key` once rotation completes.
- Until WI-004 ships the CLI helper, rotation is manual via a one-off script.
  The DSL primitives (`for row in await Model.all(): row.col = row.col; await row.save()`) make this trivial.

## Consequences

**Positive**:
- Standard, well-vetted AEAD cipher.
- Random mode is genuinely random (different ciphertexts per write).
- Deterministic mode is searchable for the narrow use case (e.g. encrypted
  emails for lookup).
- Decryption with the wrong key raises `cryptography.exceptions.InvalidTag` →
  we wrap as `DecryptionError`. Never silent corruption.

**Negative**:
- Deterministic mode leaks equality. Users opt in; docs are explicit.
- Master key rotation is non-trivial — it's an O(N rows) operation; that's
  inherent, not a flaw of our design.
- `settings.app.secret_key` becomes critical: losing it means losing the
  encrypted data. Documented as such; users are expected to back it up like
  a database master credential.

**Enforcement**:
- `tests/security/test_encrypted_wire_format.py` covers the versioned wire
  format, key-id binding, AAD binding, and the random/deterministic mode
  invariants (random ≠ deterministic, deterministic stable).
- Wrong-key/tampered-ciphertext failures raise `DecryptionError`, never
  return garbage.
- The rotation CLI (`arvel encryption:rotate`) ships in the
  wire format above is rotation-ready (key-id on disk identifies which
  key wrote each row).
