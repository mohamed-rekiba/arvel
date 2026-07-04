"""03 SEC-CRYPTO — Hasher driver manager: both drivers, cross-driver verification, plaintext-free
``needs_rehash``, ``is_hashed``/``info``. See projects/arvel/product/stories/03-sec-crypto.md."""

from __future__ import annotations

from arvel.security import Hasher, HashManager
from arvel.security.hashing import Argon2Driver, BcryptDriver, HashInfo

# --- AC 1: make/check per driver; wrong password -> False -----------------------


def test_argon2_make_and_check() -> None:
    h = HashManager("argon2id")
    hashed = h.make("s3cret")
    assert hashed.startswith("$argon2id$")
    assert h.check("s3cret", hashed) is True
    assert h.check("wrong", hashed) is False


def test_bcrypt_make_and_check() -> None:
    h = HashManager("bcrypt")
    hashed = h.make("s3cret")
    assert hashed.startswith("$2b$")
    assert h.check("s3cret", hashed) is True
    assert h.check("wrong", hashed) is False


def test_default_driver_is_argon2id() -> None:
    assert Hasher().make("x").startswith("$argon2id$")


# --- AC 2: needs_rehash is plaintext-free — params changed, both directions ----


def test_argon2_needs_rehash_when_params_change() -> None:
    stale = Argon2Driver(memory_cost=8, time_cost=1, parallelism=1).make("secret")
    current = HashManager("argon2id")  # default (stronger) params
    assert current.needs_rehash(stale) is True
    assert current.needs_rehash(current.make("secret")) is False


def test_bcrypt_needs_rehash_when_rounds_change() -> None:
    stale = BcryptDriver(rounds=4).make("secret")
    current = HashManager("bcrypt", rounds=12)
    assert current.needs_rehash(stale) is True
    assert current.needs_rehash(current.make("secret")) is False


# --- AC 3: is_hashed / info ------------------------------------------------------


def test_is_hashed_true_for_a_produced_hash_false_for_plaintext() -> None:
    h = HashManager("argon2id")
    assert h.is_hashed(h.make("secret")) is True
    assert h.is_hashed("secret") is False


def test_info_returns_algorithm_and_params() -> None:
    h = HashManager("argon2id")
    info = h.info(h.make("secret"))
    assert isinstance(info, HashInfo)
    assert info.algorithm == "argon2id"
    assert info.options == {"memory_cost": 65536, "time_cost": 3, "parallelism": 4}

    bcrypt_hash = HashManager("bcrypt", rounds=10).make("secret")
    bcrypt_info = HashManager("bcrypt").info(bcrypt_hash)
    assert bcrypt_info == HashInfo(algorithm="bcrypt", options={"rounds": 10})


def test_info_is_none_for_unrecognized_value() -> None:
    assert HashManager().info("not-a-hash") is None


# --- AC 4: cross-driver migration (bcrypt hash verifies under argon2id config) --


def test_bcrypt_hash_verifies_under_argon2id_configured_manager() -> None:
    bcrypt_hash = BcryptDriver().make("secret")
    manager = HashManager("argon2id")  # configured driver is argon2id, not bcrypt
    assert manager.check("secret", bcrypt_hash) is True
    assert manager.check("wrong", bcrypt_hash) is False


def test_bcrypt_hash_needs_rehash_true_under_argon2id_configured_manager() -> None:
    bcrypt_hash = BcryptDriver().make("secret")
    manager = HashManager("argon2id")
    assert manager.needs_rehash(bcrypt_hash) is True


def test_argon2_hash_verifies_under_bcrypt_configured_manager() -> None:
    argon2_hash = Argon2Driver().make("secret")
    manager = HashManager("bcrypt")
    assert manager.check("secret", argon2_hash) is True
    assert manager.needs_rehash(argon2_hash) is True
