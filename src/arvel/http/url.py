"""URL generation and signed routes.

Provides reverse URL generation from named routes and HMAC-SHA256 signed
URLs with expiry for tamper-proof links (email verification, webhooks).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse

from arvel.http.exceptions import InvalidSignatureError

if TYPE_CHECKING:
    from arvel.http.router import Router


class UrlGenerator:
    """Generates URLs from named routes, with optional signing.

    Attributes:
        router: The Router instance containing named routes.
        app_key: Secret key used for HMAC-SHA256 signatures.
        base_url: Base URL prepended to generated paths (e.g. ``https://app.example.com``).
    """

    def __init__(
        self,
        router: Router,
        *,
        app_key: str = "",
        base_url: str = "",
    ) -> None:
        self._router = router
        self._app_key = app_key
        self._base_url = base_url.rstrip("/")

    def url_for(self, name: str, **params: str | int) -> str:
        """Generate a URL path from a named route."""
        path = self._router.url_for(name, **params)
        if self._base_url:
            return f"{self._base_url}{path}"
        return path

    def signed_url(
        self,
        name: str,
        *,
        expires: int | None = None,
        **params: str | int,
    ) -> str:
        """Generate a signed URL with optional expiry.

        Args:
            name: Named route to generate the URL for.
            expires: Seconds until the signature expires. ``None`` for no expiry.
            **params: Route path parameters.

        Returns:
            Full URL with ``signature`` and optionally ``expires`` query params.

        Raises:
            ValueError: If ``app_key`` is empty.
        """
        if not self._app_key:
            msg = "app_key is required for signed URLs"
            raise ValueError(msg)

        path = self._router.url_for(name, **params)

        query_params: dict[str, str] = {}
        if expires is not None:
            query_params["expires"] = str(int(time.time()) + expires)

        signature = self._compute_signature(path, query_params)
        query_params["signature"] = signature

        url = path
        if self._base_url:
            url = f"{self._base_url}{path}"

        return f"{url}?{urlencode(query_params)}"

    def validate_signature(self, url: str) -> bool:
        """Validate a signed URL's signature and expiry.

        Raises:
            InvalidSignatureError: If the signature is missing, invalid, or expired.
        """
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        signature = query.get("signature", [None])[0]
        if signature is None:
            raise InvalidSignatureError("Missing signature")

        expires_str = query.get("expires", [None])[0]
        if expires_str is not None:
            try:
                expires_ts = int(expires_str)
            except ValueError:
                raise InvalidSignatureError("Invalid expires value")  # noqa: B904
            if time.time() > expires_ts:
                raise InvalidSignatureError("Signature has expired")

        params_without_sig: dict[str, str] = {}
        if expires_str is not None:
            params_without_sig["expires"] = expires_str

        expected = self._compute_signature(parsed.path, params_without_sig)
        if not hmac.compare_digest(signature, expected):
            raise InvalidSignatureError("Invalid signature")

        return True

    def _compute_signature(self, path: str, params: dict[str, str]) -> str:
        payload = path
        if params:
            sorted_params = urlencode(sorted(params.items()))
            payload = f"{path}?{sorted_params}"
        return hmac.new(
            self._app_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
