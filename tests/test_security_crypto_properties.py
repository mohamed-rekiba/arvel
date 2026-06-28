"""Security — property-based / fuzz coverage for the crypto boundary.

The example-based happy paths live in ``test_security.py``. This file proves the
*security invariants* hold across the input space, not just for hand-picked values —
the core of adversarial testing: prove the framework *refuses* the unintended.

Invariants asserted here:
- ``Encrypter`` is authenticated encryption: round-trips any text, and any mutation
  or truncation of a token is either rejected (``InvalidToken``) or decodes to the
  *same* plaintext — never a *different* one. (base64 has redundant encodings of
  identical bytes, so a single-char flip can be a no-op; what must never happen is a
  tamper forging *different* content past the MAC.)
- ``Hasher`` (argon2): verifies the right password for any input, rejects wrong ones,
  and is salted (two hashes of the same password differ).
- ``Signer`` (itsdangerous): round-trips, and any tamper is rejected or yields the
  same value — never a different accepted value (a forgery).
"""

from __future__ import annotations

from cryptography.fernet import InvalidToken
from hypothesis import given, settings
from hypothesis import strategies as st
from itsdangerous import BadData

from arvel.security import Encrypter, Hasher, Signer

# urlsafe-base64 alphabet Fernet/itsdangerous tokens are drawn from.
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="


def _flip_char(s: str, index: int) -> str:
    """Return ``s`` with the char at ``index`` replaced by a *different* b64 char."""
    i = index % len(s)
    original = s[i]
    replacement = next(c for c in _B64 if c != original)
    return s[:i] + replacement + s[i + 1 :]


# --- Encrypter: round-trip ------------------------------------------------------


@given(plaintext=st.text())
@settings(max_examples=200)
def test_encrypter_roundtrips_any_text(plaintext: str) -> None:
    enc = Encrypter(Encrypter.generate_key())
    assert enc.decrypt(enc.encrypt(plaintext)) == plaintext


# --- Encrypter: tamper-evidence (the load-bearing invariant) --------------------


@given(plaintext=st.text(min_size=1), index=st.integers(min_value=0))
@settings(max_examples=300)
def test_encrypter_mutation_never_yields_different_plaintext(plaintext: str, index: int) -> None:
    """The authenticated-encryption invariant: a single-char mutation is either
    rejected (``InvalidToken``) OR decodes to the *same* plaintext (base64 has
    redundant encodings of identical bytes). It must NEVER yield a *different*
    plaintext — that would mean the MAC could be bypassed to forge content."""
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt(plaintext)
    tampered = _flip_char(token, index)
    try:
        result = enc.decrypt(tampered)
    except InvalidToken:
        return
    assert result == plaintext, f"mutation forged a different plaintext: {result!r}"


@given(plaintext=st.text(min_size=1), cut=st.integers(min_value=1, max_value=40))
@settings(max_examples=100)
def test_encrypter_rejects_truncated_token(plaintext: str, cut: int) -> None:
    enc = Encrypter(Encrypter.generate_key())
    token = enc.encrypt(plaintext)
    truncated = token[:-cut] if cut < len(token) else ""
    try:
        enc.decrypt(truncated)
    except InvalidToken:
        return
    raise AssertionError("truncated token was accepted")


@given(blob=st.binary(max_size=200))
@settings(max_examples=200)
def test_encrypter_rejects_arbitrary_bytes(blob: bytes) -> None:
    """Arbitrary attacker-supplied input is rejected, never mis-decrypted or crashing
    with an unexpected error type."""
    enc = Encrypter(Encrypter.generate_key())
    candidate = blob.decode("latin-1")
    try:
        enc.decrypt(candidate)
    except InvalidToken:
        return
    raise AssertionError("arbitrary bytes accepted as a valid token")


# --- Encrypter: a key cannot decrypt another key's ciphertext -------------------


@given(plaintext=st.text())
@settings(max_examples=100)
def test_encrypter_wrong_key_is_rejected(plaintext: str) -> None:
    token = Encrypter(Encrypter.generate_key()).encrypt(plaintext)
    other = Encrypter(Encrypter.generate_key())
    try:
        other.decrypt(token)
    except InvalidToken:
        return
    raise AssertionError("ciphertext decrypted under an unrelated key")


# --- Hasher (argon2): slow on purpose, so cap example counts --------------------


@given(password=st.text(min_size=1, max_size=72))
@settings(max_examples=15, deadline=None)
def test_hasher_verifies_correct_and_is_salted(password: str) -> None:
    h = Hasher()
    a = h.make(password)
    b = h.make(password)
    assert a != b  # unique salts → different digests for the same password
    assert h.check(password, a) is True
    assert h.check(password, b) is True


@given(
    password=st.text(min_size=1, max_size=72),
    other=st.text(min_size=1, max_size=72),
)
@settings(max_examples=15, deadline=None)
def test_hasher_rejects_wrong_password(password: str, other: str) -> None:
    h = Hasher()
    hashed = h.make(password)
    if other != password:
        assert h.check(other, hashed) is False


# --- Signer (itsdangerous): round-trip + tamper rejection -----------------------


@given(value=st.text())
@settings(max_examples=200)
def test_signer_roundtrips(value: str) -> None:
    s = Signer("secret-key")
    assert s.unsign(s.sign(value)) == value


@given(value=st.text(min_size=1), index=st.integers(min_value=0))
@settings(max_examples=300)
def test_signer_tamper_never_yields_different_value(value: str, index: int) -> None:
    """A tamper is either rejected (``BadData``) or, where base64 has a redundant
    encoding, round-trips to the *same* value. It must NEVER produce a *different*
    accepted value — that would be a signature forgery."""
    s = Signer("secret-key")
    signed = s.sign(value)
    tampered = _flip_char(signed, index)
    if tampered == signed:
        return
    try:
        result = s.unsign(tampered)
    except BadData:
        return
    assert result == value, f"tamper forged a different value: {result!r}"
