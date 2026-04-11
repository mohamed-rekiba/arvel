"""Tests for project name validation and conversion utilities."""

from __future__ import annotations

from arvel.cli.plugins.new import validate_project_name
from arvel.cli.plugins.new.scaffold import to_package_name, to_pascal_case


class TestValidateProjectName:
    def test_valid_snake_case(self) -> None:
        assert validate_project_name("myapp") is True

    def test_valid_with_underscores(self) -> None:
        assert validate_project_name("my_app") is True

    def test_valid_kebab_case(self) -> None:
        assert validate_project_name("my-cool-app") is True

    def test_invalid_starts_with_digit(self) -> None:
        assert validate_project_name("1app") is False

    def test_invalid_special_chars(self) -> None:
        assert validate_project_name("my app!") is False

    def test_invalid_empty(self) -> None:
        assert validate_project_name("") is False


class TestToPackageName:
    def test_kebab_to_snake(self) -> None:
        assert to_package_name("my-cool-app") == "my_cool_app"

    def test_already_snake(self) -> None:
        assert to_package_name("my_app") == "my_app"

    def test_simple(self) -> None:
        assert to_package_name("myapp") == "myapp"


class TestToPascalCase:
    def test_snake_to_pascal(self) -> None:
        assert to_pascal_case("my_cool_app") == "MyCoolApp"

    def test_kebab_to_pascal(self) -> None:
        assert to_pascal_case("my-cool-app") == "MyCoolApp"

    def test_simple(self) -> None:
        assert to_pascal_case("myapp") == "Myapp"
