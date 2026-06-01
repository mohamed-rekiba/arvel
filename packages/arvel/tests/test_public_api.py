"""Public API surface stability.

Imports MUST succeed for every name we promise in foundations-api.md.
Stage 3b makes these tests pass.
"""

from __future__ import annotations

import pytest


def test_top_level_exports_complete() -> None:
    import arvel

    expected = {
        "Container",
        "Scope",
        "BindingResolutionError",
        "CircularDependencyError",
        "AsyncBindingError",
        "Application",
        "ApplicationBuilder",
        "BootError",
        "ShutdownError",
        "ServiceProvider",
        "ConfigError",
        "ConfigNotRegisteredError",
        "env",
        "dep",
    }
    missing = expected - set(arvel.__all__)
    assert not missing, f"Missing top-level exports: {sorted(missing)}"


def test_facades_config_import() -> None:
    from arvel.facades import Config

    assert Config is not None


def test_support_imports() -> None:
    from arvel.support import Collection, Pipeline
    from arvel.support.env import EnvCoercionError, env

    assert Pipeline is not None
    assert Collection is not None
    assert env is not None
    assert issubclass(EnvCoercionError, ValueError)


def test_container_module_imports() -> None:
    from arvel.container import (
        AsyncBindingError,
        BindingResolutionError,
        CircularDependencyError,
        Container,
        Scope,
    )

    assert Container is not None
    assert Scope.SINGLETON.value == "singleton"
    assert issubclass(CircularDependencyError, BindingResolutionError)
    assert issubclass(AsyncBindingError, BindingResolutionError)


def test_application_module_imports() -> None:
    from arvel.application import (
        Application,
        ApplicationBuilder,
        BootError,
        ShutdownError,
    )

    assert Application is not None
    assert ApplicationBuilder is not None
    assert issubclass(BootError, RuntimeError)
    assert issubclass(ShutdownError, RuntimeError)


def test_providers_module_imports() -> None:
    from arvel.providers import ConfigServiceProvider, ServiceProvider

    assert ServiceProvider is not None
    assert issubclass(ConfigServiceProvider, ServiceProvider)


def test_config_module_imports() -> None:
    from arvel.config import (
        ArvelSettings,
        Config,
        ConfigError,
        ConfigNotRegisteredError,
        register,
    )

    assert ArvelSettings is not None
    assert Config is not None
    assert issubclass(ConfigNotRegisteredError, ConfigError)
    assert callable(register)


def test_dep_helper_importable() -> None:
    from arvel import dep

    assert callable(dep)


def test_py_typed_marker_present() -> None:
    from pathlib import Path

    import arvel

    pkg_path = Path(arvel.__file__).parent
    assert (pkg_path / "py.typed").exists(), "py.typed marker missing"


@pytest.mark.parametrize(
    "name",
    [
        "Container",
        "Scope",
        "BindingResolutionError",
        "CircularDependencyError",
        "AsyncBindingError",
        "Application",
        "ApplicationBuilder",
        "BootError",
        "ShutdownError",
        "ServiceProvider",
        "ConfigError",
        "ConfigNotRegisteredError",
        "env",
        "dep",
    ],
)
def test_each_top_level_symbol_resolves(name: str) -> None:
    import arvel

    assert hasattr(arvel, name), f"arvel.{name} not exported"
