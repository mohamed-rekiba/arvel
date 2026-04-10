"""Security contracts — ABCs for hashing and encryption drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class HasherContract(ABC):
    """Password hashing abstraction. Drivers: bcrypt, argon2."""

    @abstractmethod
    def make(self, password: str) -> str:
        """Hash a plaintext password. Returns an encoded hash string."""

    @abstractmethod
    def check(self, password: str, hashed: str) -> bool:
        """Verify a plaintext password against a hash. Uses constant-time comparison."""

    @abstractmethod
    def needs_rehash(self, hashed: str) -> bool:
        """Check if a hash was made with outdated parameters and should be re-hashed."""


class EncrypterContract(ABC):
    """Symmetric encryption abstraction. Default driver: AES-256-CBC with HMAC."""

    @abstractmethod
    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext string. Returns a Base64-encoded, MAC-signed payload."""

    @abstractmethod
    def decrypt(self, payload: str) -> str:
        """Decrypt a payload. Raises DecryptionError if MAC verification fails."""
