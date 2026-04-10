"""Tests for Epic 12: Docker & CI Environment.

Covers:
- Story 1: Docker Compose file exists with all services and health checks
- Story 2: Test environment configuration (markers, service detection)
- Story 3: CI pipeline configuration (service containers, type check, coverage)
- Story 4: Makefile targets
- Story 5: MariaDB/MySQL driver support (migration URL mapping)
- Story 6: Keycloak OIDC provider for auth testing (realm, client, users)

All tests should FAIL until implementation exists (QA-Pre / Red phase).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ──── Project root for file-existence checks ────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestDockerCompose:
    """Story 1: Docker Compose for Local Development."""

    def test_compose_file_exists(self) -> None:
        assert (PROJECT_ROOT / "docker-compose.yml").is_file(), (
            "docker-compose.yml must exist at project root"
        )

    def test_compose_has_postgres_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "postgres:" in content

    def test_compose_has_mariadb_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "mariadb:" in content

    def test_compose_has_valkey_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "valkey:" in content

    def test_compose_has_mailpit_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "mailpit:" in content

    def test_compose_has_minio_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "minio:" in content

    def test_compose_has_keycloak_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "keycloak:" in content

    def test_compose_has_rabbitmq_service(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "rabbitmq:" in content

    def test_compose_has_health_checks(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "healthcheck:" in content

    def test_compose_has_no_latest_tags(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert ":latest" not in content, "All images must use pinned versions, not :latest"

    def test_compose_uses_named_volumes(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "volumes:" in content


class TestEnvDocker:
    """Story 1: .env.docker template with dev-only credentials."""

    def test_env_docker_exists(self) -> None:
        assert (PROJECT_ROOT / ".env.docker").is_file(), (
            ".env.docker template must exist at project root"
        )

    def test_env_docker_has_postgres_credentials(self) -> None:
        content = (PROJECT_ROOT / ".env.docker").read_text()
        assert "POSTGRES_" in content

    def test_env_docker_has_mariadb_credentials(self) -> None:
        content = (PROJECT_ROOT / ".env.docker").read_text()
        assert "MARIADB_" in content

    def test_env_docker_has_valkey_config(self) -> None:
        content = (PROJECT_ROOT / ".env.docker").read_text()
        assert "VALKEY_" in content

    def test_env_docker_has_keycloak_credentials(self) -> None:
        content = (PROJECT_ROOT / ".env.docker").read_text()
        assert "KC_ADMIN" in content

    def test_env_docker_has_minio_credentials(self) -> None:
        content = (PROJECT_ROOT / ".env.docker").read_text()
        assert "MINIO_" in content


class TestEnvTesting:
    """Story 2: .env.testing template."""

    def test_env_testing_exists(self) -> None:
        assert (PROJECT_ROOT / ".env.testing").is_file(), (
            ".env.testing template must exist at project root"
        )

    def test_env_testing_has_db_url(self) -> None:
        content = (PROJECT_ROOT / ".env.testing").read_text()
        assert "DB_URL" in content

    def test_env_testing_has_cache_redis_url(self) -> None:
        content = (PROJECT_ROOT / ".env.testing").read_text()
        assert "CACHE_REDIS_URL" in content

    def test_env_testing_has_mail_config(self) -> None:
        content = (PROJECT_ROOT / ".env.testing").read_text()
        assert "MAIL_" in content

    def test_env_testing_has_oidc_config(self) -> None:
        content = (PROJECT_ROOT / ".env.testing").read_text()
        assert "OIDC_" in content

    def test_env_testing_has_storage_config(self) -> None:
        content = (PROJECT_ROOT / ".env.testing").read_text()
        assert "STORAGE_" in content


class TestPytestMarkers:
    """Story 2: Pytest markers registered in pyproject.toml."""

    def test_mysql_only_marker_registered(self) -> None:
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "mysql_only" in content, "mysql_only marker must be registered"

    def test_rabbitmq_marker_registered(self) -> None:
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "rabbitmq" in content, "rabbitmq marker must be registered"

    def test_oidc_marker_registered(self) -> None:
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "oidc" in content, "oidc marker must be registered"


class TestMakefile:
    """Story 4: Makefile targets."""

    def test_makefile_exists(self) -> None:
        assert (PROJECT_ROOT / "Makefile").is_file()

    @pytest.mark.parametrize(
        "target",
        [
            "up",
            "down",
            "clean",
            "test",
            "test-unit",
            "test-integration",
            "lint",
            "typecheck",
            "verify",
            "coverage",
        ],
    )
    def test_makefile_has_target(self, target: str) -> None:
        content = (PROJECT_ROOT / "Makefile").read_text()
        assert f"{target}:" in content, f"Makefile must have a '{target}' target"


class TestMariaDBEnvTemplate:
    """Story 5: Alembic env.py template delegates to run_alembic_env."""

    def test_env_template_delegates_to_framework_entrypoint(self) -> None:
        from arvel.data.migrations import MigrationRunner

        template = MigrationRunner.get_env_template()
        assert "run_alembic_env" in template

    def test_run_alembic_env_handles_sqlite_and_async(self) -> None:
        import inspect

        import arvel.data.migrations as migrations_mod
        from arvel.data.migrations import run_alembic_env

        module_source = inspect.getsource(migrations_mod)
        env_source = inspect.getsource(run_alembic_env)
        assert "aiosqlite" in module_source
        assert "run_async_migrations" in env_source or "async_engine_from_config" in env_source
        assert "inject_revisions" in env_source


class TestMariaDBOptionalExtra:
    """Story 5: pyproject.toml has mysql optional extra (dialect name covers MariaDB)."""

    def test_mysql_extra_in_pyproject(self) -> None:
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "mysql = [" in content or "mysql = [" in content, (
            "pyproject.toml must define a 'mysql' optional extra"
        )


class TestKeycloakRealm:
    """Story 6: Keycloak realm JSON pre-configures OIDC for testing."""

    REALM_PATH = PROJECT_ROOT / ".docker" / "keycloak" / "arvel-test-realm.json"

    def test_realm_file_exists(self) -> None:
        assert self.REALM_PATH.is_file(), "Keycloak realm JSON must exist at .docker/keycloak/"

    def test_realm_is_valid_json(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        assert isinstance(data, dict)

    def test_realm_name(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        assert data["realm"] == "arvel-test"

    def test_realm_has_confidential_client(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        clients = {c["clientId"]: c for c in data.get("clients", [])}
        assert "arvel-test-client" in clients
        client = clients["arvel-test-client"]
        assert client["publicClient"] is False
        assert client.get("secret") == "arvel-test-secret"

    def test_client_supports_authorization_code_and_direct_grant(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        client = next(c for c in data["clients"] if c["clientId"] == "arvel-test-client")
        assert client["standardFlowEnabled"] is True
        assert client["directAccessGrantsEnabled"] is True

    def test_client_supports_pkce(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        client = next(c for c in data["clients"] if c["clientId"] == "arvel-test-client")
        assert client["attributes"].get("pkce.code.challenge.method") == "S256"

    def test_client_has_required_scopes(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        client = next(c for c in data["clients"] if c["clientId"] == "arvel-test-client")
        scopes = set(client.get("defaultClientScopes", []))
        assert {"openid", "email", "profile"} <= scopes

    def test_realm_has_roles(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        role_names = [r["name"] for r in data.get("roles", {}).get("realm", [])]
        assert "admin" in role_names
        assert "user" in role_names

    def test_realm_has_groups(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        group_names = [g["name"] for g in data.get("groups", [])]
        assert len(group_names) >= 1

    def test_realm_has_test_users(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        users = {u["username"]: u for u in data.get("users", [])}
        assert "testuser" in users
        assert users["testuser"]["email"] == "testuser@arvel.dev"
        assert users["testuser"]["emailVerified"] is True

    def test_test_user_has_roles_and_groups(self) -> None:
        data = json.loads(self.REALM_PATH.read_text())
        user = next(u for u in data["users"] if u["username"] == "testuser")
        assert "admin" in user.get("realmRoles", [])
        assert len(user.get("groups", [])) >= 1

    def test_setup_script_creates_groups_scope(self) -> None:
        """ClaimsMapper expects a 'groups' claim — setup script creates scope."""
        setup_script = self.REALM_PATH.parent / "setup-realm.sh"
        assert setup_script.is_file(), "setup-realm.sh must exist alongside realm JSON"
        content = setup_script.read_text()
        assert "groups" in content

    def test_compose_mounts_realm_into_keycloak(self) -> None:
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "/opt/keycloak/data/import" in content

    def test_ci_mounts_realm_into_keycloak(self) -> None:
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "/opt/keycloak/data/import" in content
