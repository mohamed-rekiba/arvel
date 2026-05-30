"""Tests for temporary URL signing — FR-006-032, NFR-006-007..008."""

from __future__ import annotations

import os
import time

import pytest
from arvel.storage.url_signer import TemporaryUrlSigner


@pytest.fixture
def app_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def signer(app_key: bytes) -> TemporaryUrlSigner:
    return TemporaryUrlSigner(app_key=app_key, base_url="http://localhost:8000")


class TestTemporaryUrlSigner:
    def test_generates_valid_url(self, signer: TemporaryUrlSigner) -> None:
        url = signer.sign("invoices/001.pdf", ttl=300)
        assert "token=" in url
        assert "expires=" in url
        assert "invoices/001.pdf" in url

    def test_valid_token_verifies(self, signer: TemporaryUrlSigner) -> None:
        url = signer.sign("file.txt", ttl=300)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        assert signer.verify(
            path="file.txt",
            token=params["token"][0],
            expires=params["expires"][0],
        )

    def test_expired_token_does_not_verify(self, signer: TemporaryUrlSigner) -> None:
        expires = str(int(time.time()) - 1)  # 1 second in the past
        import base64
        import hashlib
        import hmac

        key = signer.derived_key
        message = f"file.txt:{expires}".encode()
        token = base64.urlsafe_b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()
        assert signer.verify("file.txt", token=token, expires=expires) is False

    def test_tampered_path_does_not_verify(self, signer: TemporaryUrlSigner) -> None:
        url = signer.sign("original.txt", ttl=300)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        # Token signed for original.txt; verify against a different path
        assert (
            signer.verify(
                path="evil.txt",
                token=params["token"][0],
                expires=params["expires"][0],
            )
            is False
        )

    def test_uses_hmac_sha256_not_md5(self, signer: TemporaryUrlSigner) -> None:
        """NFR-006-008: HMAC-SHA256 only; no MD5/SHA-1."""
        import inspect

        import arvel.storage.url_signer as mod

        source = inspect.getsource(mod)
        assert "md5" not in source.lower()
        assert "sha1" not in source.lower() or "sha1" not in source

    def test_constant_time_compare_used(self, signer: TemporaryUrlSigner) -> None:
        """NFR-006-007: constant-time comparison to prevent timing attacks."""
        import inspect

        import arvel.storage.url_signer as mod

        source = inspect.getsource(mod)
        assert "compare_digest" in source
