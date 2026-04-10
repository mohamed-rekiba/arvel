"""Tests for claims mapper — extracting roles/groups from JWT/OIDC claims."""

from __future__ import annotations

from arvel.auth.claims import ClaimsMapper, ClaimsMapperConfig, ExtractedClaims


class TestClaimsMapper:
    def test_extract_keycloak_claims(self) -> None:
        claims = {
            "sub": "user-123",
            "realm_access": {"roles": ["admin", "editor"]},
            "groups": ["/org/team-a", "/org/team-b"],
        }
        mapper = ClaimsMapper()
        result = mapper.extract(claims)

        assert result.sub == "user-123"
        assert result.roles == ["admin", "editor"]
        assert result.groups == ["/org/team-a", "/org/team-b"]

    def test_extract_azure_ad_claims(self) -> None:
        claims = {
            "sub": "azure-user-456",
            "roles": ["User.Read", "Admin"],
            "groups": ["group-id-1", "group-id-2"],
        }
        mapper = ClaimsMapper(
            ClaimsMapperConfig(
                role_claim_paths=["roles"],
                group_claim_paths=["groups"],
            )
        )
        result = mapper.extract(claims)

        assert result.sub == "azure-user-456"
        assert result.roles == ["User.Read", "Admin"]
        assert result.groups == ["group-id-1", "group-id-2"]

    def test_extract_nested_path(self) -> None:
        claims = {
            "sub": "user-789",
            "resource_access": {"my-app": {"roles": ["viewer"]}},
        }
        mapper = ClaimsMapper(
            ClaimsMapperConfig(
                role_claim_paths=["resource_access.my-app.roles"],
            )
        )
        result = mapper.extract(claims)
        assert result.roles == ["viewer"]

    def test_missing_claims_return_empty(self) -> None:
        claims = {"sub": "user-000"}
        mapper = ClaimsMapper()
        result = mapper.extract(claims)

        assert result.sub == "user-000"
        assert result.roles == []
        assert result.groups == []

    def test_deduplicates_roles(self) -> None:
        claims = {
            "sub": "user-dup",
            "realm_access": {"roles": ["admin", "editor"]},
            "roles": ["admin", "viewer"],
        }
        mapper = ClaimsMapper()
        result = mapper.extract(claims)
        assert result.roles == ["admin", "editor", "viewer"]

    def test_deduplicates_groups(self) -> None:
        claims = {
            "sub": "user-dup",
            "groups": ["/a", "/b", "/a"],
        }
        mapper = ClaimsMapper()
        result = mapper.extract(claims)
        assert result.groups == ["/a", "/b"]

    def test_string_role_value(self) -> None:
        claims = {
            "sub": "user-str",
            "roles": "single-role",
        }
        mapper = ClaimsMapper(ClaimsMapperConfig(role_claim_paths=["roles"]))
        result = mapper.extract(claims)
        assert result.roles == ["single-role"]

    def test_raw_claims_preserved(self) -> None:
        claims = {"sub": "user-raw", "custom_field": "value"}
        mapper = ClaimsMapper()
        result = mapper.extract(claims)
        assert result.raw == claims

    def test_missing_sub_returns_empty_string(self) -> None:
        mapper = ClaimsMapper()
        result = mapper.extract({})
        assert result.sub == ""


class TestExtractedClaims:
    def test_default_factory(self) -> None:
        ec = ExtractedClaims(sub="test")
        assert ec.roles == []
        assert ec.groups == []
        assert ec.raw == {}
