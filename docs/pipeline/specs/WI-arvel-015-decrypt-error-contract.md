# WI-arvel-015 — Encrypter.decrypt_string must raise DecryptionError for any bad payload

| | |
|---|---|
| **Module** | encryption |
| **Complexity** | L2 | **Risk** | Tier 3 (crypto/untrusted input) | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/015-encryption.md` (C1 fixed; decrypt() JSON + from_app_key deferred) |
| **Review** | C1 confirmed via repro: `decrypt_string` leaks `binascii.Error` on malformed base64; sibling `EncryptedType` already funnels all bad input → `DecryptionError` |

## Problem

`Encrypter.decrypt_string` documents `DecryptionError` as its failure type, but the
base64 decode sat outside the try/except:

```python
def decrypt_string(self, payload: str) -> str:
    raw = base64.b64decode(payload)          # binascii.Error on bad base64 → leaks
    if raw[:1] != _VERSION:
        raise DecryptionError("Unrecognised encrypter wire-format version.")
    iv, ct = raw[1 : 1 + _IV_BYTES], raw[1 + _IV_BYTES :]
    try:
        return self._aes.decrypt(iv, ct, None).decode("utf-8")
    except Exception as exc:
        raise DecryptionError("Failed to decrypt value ...") from exc
```

A non-base64 payload raised a raw `binascii.Error`. The sibling column type
`database.casts.EncryptedType.process_result_value` already does `except Exception:
raise DecryptionError(...)`, and Laravel's `Encrypter::decrypt` raises `DecryptException`
for every invalid payload. A caller decrypting attacker-controlled input via the `Crypt`
facade and catching the documented `DecryptionError` would have the `binascii.Error`
escape — an uncaught 500 (A10: mishandling exceptional conditions).

Reproduced: `decrypt_string("!!!not-base64!!!")` and `decrypt_string("a")` raised
`binascii.Error`; `"@@@@"` correctly raised `DecryptionError`.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | A malformed (non-base64 / wrong length / empty) payload raises `DecryptionError`. | `tests/encryption/test_wi_015_decrypt_error_contract.py::test_malformed_payload_raises_decryption_error` (×4) | PASS |
| SPEC-2 | An unknown version byte raises `DecryptionError`. | `...::test_malformed_payload_raises_decryption_error[@@@@]` | PASS |
| SPEC-3 | A wrong-key ciphertext raises `DecryptionError`. | `...::test_wrong_key_raises_decryption_error` | PASS |
| SPEC-4 | A tampered tag raises `DecryptionError`. | `...::test_tampered_ciphertext_raises_decryption_error` | PASS |
| SPEC-5 | Round-trip (`encrypt_string`/`decrypt_string`, `encrypt`/`decrypt`) unchanged. | `...::test_round_trip_string`, `...::test_round_trip_value` | PASS |
| SPEC-6 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean; encryption + full suite green. | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`encrypter.py` — wrap `base64.b64decode(payload)` in `try/except ValueError`
(`binascii.Error` subclasses `ValueError`) and raise `DecryptionError`. `decrypt_string`
now raises the documented type for every malformed payload, matching `EncryptedType` and
Laravel.

## Deliberate design decisions

- **Catch `ValueError`, not `binascii.Error`.** `binascii.Error` is a `ValueError`
  subclass; catching the base class avoids an extra import and still narrowly targets
  decode failures (the slicing below can't raise — slices are bounds-safe).
- **Keep the version-mismatch message distinct.** A decodable-but-wrong-version payload
  still gets its specific `DecryptionError` message; only true decode failures get the
  "not valid base64" message.

## Out-of-scope cleanup (folded in)

- Added `tests/encryption/` (the `Encrypter` had no direct unit coverage — the existing
  `tests/security/test_crypt_facade.py` only exercised facade key management).

## Deferred (tracked)

- **`Encrypter.decrypt()` JSON parse failure** surfaces `json.JSONDecodeError`. Only
  reachable via API misuse on a valid-key payload (not attacker input). Parity-additive.
- **`from_app_key()` malformed `APP_KEY`** raises `binascii.Error`. Operator-controlled
  config, not request input; could wrap in a clearer config error later.
