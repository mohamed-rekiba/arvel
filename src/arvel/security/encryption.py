"""AES-256-CBC encryption with HMAC-SHA256 authentication.

Uses only the Python stdlib (no cryptography dependency required).
Payload format: base64(iv + ciphertext + hmac)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from arvel.security.contracts import EncrypterContract
from arvel.security.exceptions import DecryptionError

_IV_SIZE = 16
_KEY_SIZE = 32
_MAC_SIZE = 32
_BLOCK_SIZE = 16


def _pad(data: bytes) -> bytes:
    pad_len = _BLOCK_SIZE - (len(data) % _BLOCK_SIZE)
    return data + bytes([pad_len]) * pad_len


def _unpad(data: bytes) -> bytes:
    if not data:
        raise DecryptionError("Empty plaintext after decryption")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > _BLOCK_SIZE:
        raise DecryptionError("Invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise DecryptionError("Corrupted PKCS7 padding")
    return data[:-pad_len]


def _aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """AES-256-CBC encryption using PEP 272 style — stdlib only via _aes_block."""
    padded = _pad(plaintext)
    blocks = [padded[i : i + _BLOCK_SIZE] for i in range(0, len(padded), _BLOCK_SIZE)]
    ciphertext = b""
    prev = iv
    for block in blocks:
        xored = bytes(a ^ b for a, b in zip(block, prev, strict=False))
        encrypted = _aes_ecb_encrypt_block(key, xored)
        ciphertext += encrypted
        prev = encrypted
    return ciphertext


def _aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """AES-256-CBC decryption — stdlib only."""
    if len(ciphertext) % _BLOCK_SIZE != 0:
        raise DecryptionError("Ciphertext length is not a multiple of block size")
    blocks = [ciphertext[i : i + _BLOCK_SIZE] for i in range(0, len(ciphertext), _BLOCK_SIZE)]
    plaintext = b""
    prev = iv
    for block in blocks:
        decrypted = _aes_ecb_decrypt_block(key, block)
        plaintext += bytes(a ^ b for a, b in zip(decrypted, prev, strict=False))
        prev = block
    return _unpad(plaintext)


def _aes_ecb_encrypt_block(key: bytes, block: bytes) -> bytes:
    """Encrypt a single 16-byte block with AES-256 in ECB mode.

    Tries the stdlib hashlib-based approach first, falls back to
    the `cryptography` package if available.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
        enc = cipher.encryptor()
        return enc.update(block) + enc.finalize()
    except ImportError:
        pass

    return _aes_pure_block(key, block, encrypt=True)


def _aes_ecb_decrypt_block(key: bytes, block: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
        dec = cipher.decryptor()
        return dec.update(block) + dec.finalize()
    except ImportError:
        pass

    return _aes_pure_block(key, block, encrypt=False)


# --- Pure-Python AES-256 fallback (no external deps) ---

_SBOX = (
    0x63,
    0x7C,
    0x77,
    0x7B,
    0xF2,
    0x6B,
    0x6F,
    0xC5,
    0x30,
    0x01,
    0x67,
    0x2B,
    0xFE,
    0xD7,
    0xAB,
    0x76,
    0xCA,
    0x82,
    0xC9,
    0x7D,
    0xFA,
    0x59,
    0x47,
    0xF0,
    0xAD,
    0xD4,
    0xA2,
    0xAF,
    0x9C,
    0xA4,
    0x72,
    0xC0,
    0xB7,
    0xFD,
    0x93,
    0x26,
    0x36,
    0x3F,
    0xF7,
    0xCC,
    0x34,
    0xA5,
    0xE5,
    0xF1,
    0x71,
    0xD8,
    0x31,
    0x15,
    0x04,
    0xC7,
    0x23,
    0xC3,
    0x18,
    0x96,
    0x05,
    0x9A,
    0x07,
    0x12,
    0x80,
    0xE2,
    0xEB,
    0x27,
    0xB2,
    0x75,
    0x09,
    0x83,
    0x2C,
    0x1A,
    0x1B,
    0x6E,
    0x5A,
    0xA0,
    0x52,
    0x3B,
    0xD6,
    0xB3,
    0x29,
    0xE3,
    0x2F,
    0x84,
    0x53,
    0xD1,
    0x00,
    0xED,
    0x20,
    0xFC,
    0xB1,
    0x5B,
    0x6A,
    0xCB,
    0xBE,
    0x39,
    0x4A,
    0x4C,
    0x58,
    0xCF,
    0xD0,
    0xEF,
    0xAA,
    0xFB,
    0x43,
    0x4D,
    0x33,
    0x85,
    0x45,
    0xF9,
    0x02,
    0x7F,
    0x50,
    0x3C,
    0x9F,
    0xA8,
    0x51,
    0xA3,
    0x40,
    0x8F,
    0x92,
    0x9D,
    0x38,
    0xF5,
    0xBC,
    0xB6,
    0xDA,
    0x21,
    0x10,
    0xFF,
    0xF3,
    0xD2,
    0xCD,
    0x0C,
    0x13,
    0xEC,
    0x5F,
    0x97,
    0x44,
    0x17,
    0xC4,
    0xA7,
    0x7E,
    0x3D,
    0x64,
    0x5D,
    0x19,
    0x73,
    0x60,
    0x81,
    0x4F,
    0xDC,
    0x22,
    0x2A,
    0x90,
    0x88,
    0x46,
    0xEE,
    0xB8,
    0x14,
    0xDE,
    0x5E,
    0x0B,
    0xDB,
    0xE0,
    0x32,
    0x3A,
    0x0A,
    0x49,
    0x06,
    0x24,
    0x5C,
    0xC2,
    0xD3,
    0xAC,
    0x62,
    0x91,
    0x95,
    0xE4,
    0x79,
    0xE7,
    0xC8,
    0x37,
    0x6D,
    0x8D,
    0xD5,
    0x4E,
    0xA9,
    0x6C,
    0x56,
    0xF4,
    0xEA,
    0x65,
    0x7A,
    0xAE,
    0x08,
    0xBA,
    0x78,
    0x25,
    0x2E,
    0x1C,
    0xA6,
    0xB4,
    0xC6,
    0xE8,
    0xDD,
    0x74,
    0x1F,
    0x4B,
    0xBD,
    0x8B,
    0x8A,
    0x70,
    0x3E,
    0xB5,
    0x66,
    0x48,
    0x03,
    0xF6,
    0x0E,
    0x61,
    0x35,
    0x57,
    0xB9,
    0x86,
    0xC1,
    0x1D,
    0x9E,
    0xE1,
    0xF8,
    0x98,
    0x11,
    0x69,
    0xD9,
    0x8E,
    0x94,
    0x9B,
    0x1E,
    0x87,
    0xE9,
    0xCE,
    0x55,
    0x28,
    0xDF,
    0x8C,
    0xA1,
    0x89,
    0x0D,
    0xBF,
    0xE6,
    0x42,
    0x68,
    0x41,
    0x99,
    0x2D,
    0x0F,
    0xB0,
    0x54,
    0xBB,
    0x16,
)

_INV_SBOX = tuple(_SBOX.index(i) for i in range(256))

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x11B) & 0xFF if a & 0x80 else (a << 1) & 0xFF


def _mix_single(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _key_expansion_256(key: bytes) -> list[list[int]]:
    nk = 8
    nr = 14
    w: list[list[int]] = []
    for i in range(nk):
        w.append(list(key[4 * i : 4 * i + 4]))
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([a ^ b for a, b in zip(w[i - nk], temp, strict=False)])
    return w


def _add_round_key(state: list[list[int]], rk: list[list[int]]) -> None:
    for c in range(4):
        for r in range(4):
            state[r][c] ^= rk[c][r]


def _sub_bytes(state: list[list[int]], sbox: tuple[int, ...] = _SBOX) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] = sbox[state[r][c]]


def _shift_rows(state: list[list[int]]) -> None:
    state[1] = state[1][1:] + state[1][:1]
    state[2] = state[2][2:] + state[2][:2]
    state[3] = state[3][3:] + state[3][:3]


def _inv_shift_rows(state: list[list[int]]) -> None:
    state[1] = state[1][-1:] + state[1][:-1]
    state[2] = state[2][-2:] + state[2][:-2]
    state[3] = state[3][-3:] + state[3][:-3]


def _mix_columns(state: list[list[int]]) -> None:
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _xtime(a[0]) ^ _xtime(a[1]) ^ a[1] ^ a[2] ^ a[3]
        state[1][c] = a[0] ^ _xtime(a[1]) ^ _xtime(a[2]) ^ a[2] ^ a[3]
        state[2][c] = a[0] ^ a[1] ^ _xtime(a[2]) ^ _xtime(a[3]) ^ a[3]
        state[3][c] = _xtime(a[0]) ^ a[0] ^ a[1] ^ a[2] ^ _xtime(a[3])


def _inv_mix_columns(state: list[list[int]]) -> None:
    m = _mix_single
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = m(a[0], 14) ^ m(a[1], 11) ^ m(a[2], 13) ^ m(a[3], 9)
        state[1][c] = m(a[0], 9) ^ m(a[1], 14) ^ m(a[2], 11) ^ m(a[3], 13)
        state[2][c] = m(a[0], 13) ^ m(a[1], 9) ^ m(a[2], 14) ^ m(a[3], 11)
        state[3][c] = m(a[0], 11) ^ m(a[1], 13) ^ m(a[2], 9) ^ m(a[3], 14)


def _bytes_to_state(block: bytes) -> list[list[int]]:
    return [[block[r + 4 * c] for c in range(4)] for r in range(4)]


def _state_to_bytes(state: list[list[int]]) -> bytes:
    return bytes(state[r][c] for c in range(4) for r in range(4))


def _aes_pure_block(key: bytes, block: bytes, *, encrypt: bool) -> bytes:
    """Pure-Python AES-256 single-block encrypt/decrypt. Slow but dependency-free."""
    nr = 14
    w = _key_expansion_256(key)
    state = _bytes_to_state(block)

    if encrypt:
        _add_round_key(state, [w[c] for c in range(4)])
        for rnd in range(1, nr):
            _sub_bytes(state)
            _shift_rows(state)
            _mix_columns(state)
            _add_round_key(state, [w[rnd * 4 + c] for c in range(4)])
        _sub_bytes(state)
        _shift_rows(state)
        _add_round_key(state, [w[nr * 4 + c] for c in range(4)])
    else:
        _add_round_key(state, [w[nr * 4 + c] for c in range(4)])
        for rnd in range(nr - 1, 0, -1):
            _inv_shift_rows(state)
            _sub_bytes(state, _INV_SBOX)
            _add_round_key(state, [w[rnd * 4 + c] for c in range(4)])
            _inv_mix_columns(state)
        _inv_shift_rows(state)
        _sub_bytes(state, _INV_SBOX)
        _add_round_key(state, [w[c] for c in range(4)])

    return _state_to_bytes(state)


class AesEncrypter(EncrypterContract):
    """AES-256-CBC encrypter with HMAC-SHA256 message authentication."""

    def __init__(self, key: bytes) -> None:
        if len(key) < _KEY_SIZE:
            raise ValueError(f"Encryption key must be at least {_KEY_SIZE} bytes, got {len(key)}")
        self._enc_key = key[:_KEY_SIZE]
        self._mac_key = hashlib.sha256(key + b"mac").digest()

    def encrypt(self, value: str) -> str:
        iv = os.urandom(_IV_SIZE)
        ciphertext = _aes_cbc_encrypt(self._enc_key, iv, value.encode("utf-8"))
        mac = hmac.new(self._mac_key, iv + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(iv + ciphertext + mac).decode("ascii")

    def decrypt(self, payload: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(payload)
        except Exception as e:
            raise DecryptionError("Invalid base64 payload") from e

        if len(raw) < _IV_SIZE + _BLOCK_SIZE + _MAC_SIZE:
            raise DecryptionError("Payload too short")

        iv = raw[:_IV_SIZE]
        mac_received = raw[-_MAC_SIZE:]
        ciphertext = raw[_IV_SIZE:-_MAC_SIZE]

        mac_computed = hmac.new(self._mac_key, iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac_received, mac_computed):
            raise DecryptionError("MAC verification failed — payload tampered or wrong key")

        plaintext_bytes = _aes_cbc_decrypt(self._enc_key, iv, ciphertext)
        return plaintext_bytes.decode("utf-8")
