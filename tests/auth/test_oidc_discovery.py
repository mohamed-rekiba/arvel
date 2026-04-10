"""Tests for OIDC auto-discovery."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from arvel.auth.oauth import OIDCDiscoveryDocument, discover_oidc_config

KEYCLOAK_DISCOVERY = {
    "issuer": "https://keycloak.example.com/realms/myrealm",
    "authorization_endpoint": "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/auth",
    "token_endpoint": "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/token",
    "userinfo_endpoint": "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/userinfo",
    "jwks_uri": "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs",
    "scopes_supported": ["openid", "email", "profile", "groups"],
    "response_types_supported": ["code", "id_token"],
    "claims_supported": ["sub", "name", "email", "groups", "realm_access"],
}


def _mock_urlopen(discovery_data: dict[str, Any]):
    """Create a mock for urllib.request.urlopen returning discovery JSON."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(discovery_data).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


class TestOIDCDiscovery:
    def test_discover_keycloak(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(KEYCLOAK_DISCOVERY)):
            doc, config = discover_oidc_config(
                "https://keycloak.example.com/realms/myrealm",
                client_id="my-app",
                client_secret="my-secret",
            )

        assert isinstance(doc, OIDCDiscoveryDocument)
        assert doc.issuer == "https://keycloak.example.com/realms/myrealm"
        assert "keycloak" in doc.authorization_endpoint
        assert doc.jwks_uri.endswith("/certs")
        assert "groups" in doc.scopes_supported
        assert "realm_access" in doc.claims_supported

        assert config.provider_name == "myrealm"
        assert config.client_id == "my-app"
        assert config.client_secret == "my-secret"
        assert config.authorize_url == doc.authorization_endpoint
        assert config.token_url == doc.token_endpoint

    def test_discover_strips_trailing_slash(self) -> None:
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(KEYCLOAK_DISCOVERY)):
            _doc, config = discover_oidc_config(
                "https://keycloak.example.com/realms/myrealm/",
                client_id="app",
                client_secret="secret",
            )
        assert config.provider_name == "myrealm"

    def test_discover_minimal_response(self) -> None:
        minimal = {
            "authorization_endpoint": "https://auth.test/authorize",
            "token_endpoint": "https://auth.test/token",
        }
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(minimal)):
            doc, _config = discover_oidc_config(
                "https://auth.test",
                client_id="id",
                client_secret="secret",
            )

        assert doc.userinfo_endpoint == ""
        assert doc.jwks_uri == ""
        assert doc.scopes_supported == []
