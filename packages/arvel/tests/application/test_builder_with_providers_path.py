"""FR-004-008: ``ApplicationBuilder.with_providers(Path)`` overload.

The existing ``with_providers(list[type[ServiceProvider]])`` continues to
work unchanged (NFR-004-007). The new overload accepts a ``Path`` (or
``str``) pointing to a ``bootstrap/providers.py`` file whose module-level
``providers`` attribute is read by the builder.

QA-Pre Red state: the path overload currently raises ``NotImplementedError``
at ``.create()`` time. Stage 3b will replace that with the loader-driven
implementation that satisfies the acceptance tests below.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel import Application, ServiceProvider


class _SampleProvider(ServiceProvider):
    """Test fixture used as a sentinel provider class."""


def test_existing_list_overload_still_works(tmp_path: Path) -> None:
    """NFR-004-007: existing call sites that pass a list of provider classes pass unchanged."""
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([_SampleProvider])
        .create()
    )
    assert isinstance(app, Application)


def test_with_providers_accepts_pathlib_path(tmp_path: Path) -> None:
    """Builder accepts ``Path`` without raising at the call (failure deferred to .create())."""
    providers_file = tmp_path / "bootstrap" / "providers.py"
    providers_file.parent.mkdir()
    providers_file.write_text(
        "from arvel import ServiceProvider\n"
        "class _StubProvider(ServiceProvider):\n"
        "    pass\n"
        "providers: list[type[ServiceProvider]] = [_StubProvider]\n",
    )

    # The fluent call itself must not raise.
    builder = (
        Application.configure(tmp_path).with_environment("testing").with_providers(providers_file)
    )
    assert builder is not None


def test_with_providers_accepts_str_path(tmp_path: Path) -> None:
    """Builder accepts a string path (converted internally to Path)."""
    providers_file = tmp_path / "bootstrap" / "providers.py"
    providers_file.parent.mkdir()
    providers_file.write_text("providers: list[type] = []\n")

    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers(str(providers_file))
    )
    assert builder is not None


def test_with_providers_path_loads_providers_at_create(tmp_path: Path) -> None:
    """End-to-end: a Path to providers.py resolves to a real provider class.

    We define the provider class inside an adjacent file (so the loaded
    providers.py imports from a single, unambiguous module path) and check
    by qualname rather than class identity — pytest's import mechanics can
    yield the same module under two different sys.modules keys, so identity
    checks across a freshly-loaded module are fragile.
    """
    pkg = tmp_path / "fixture_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "my_provider.py").write_text(
        "from arvel import ServiceProvider\nclass MyProvider(ServiceProvider):\n    pass\n",
    )
    providers_file = tmp_path / "bootstrap" / "providers.py"
    providers_file.parent.mkdir()
    providers_file.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "from fixture_pkg.my_provider import MyProvider\n"
        # Pop the sys.path entry after import so our load_module_from_path
        # invariant assertion still holds.
        "sys.path.pop(0)\n"
        "providers = [MyProvider]\n",
    )

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers(providers_file)
        .create()
    )

    # The framework auto-registers a baseline of providers (Config, Log, Lang,
    # Database, Http, Scheduler) before user providers and the Console provider
    # last. The user's `MyProvider` must end up in the chain.
    classes = app._provider_classes  # pyright: ignore[reportPrivateUsage]
    loaded = next((c for c in classes if c.__name__ == "MyProvider"), None)
    assert loaded is not None, f"MyProvider not in {[c.__name__ for c in classes]}"
    assert issubclass(loaded, ServiceProvider)


def test_with_providers_path_missing_attribute_raises_at_create(tmp_path: Path) -> None:
    """A providers.py without a top-level ``providers`` attribute raises at .create()."""
    providers_file = tmp_path / "bootstrap" / "providers.py"
    providers_file.parent.mkdir()
    providers_file.write_text("OTHER = 42\n")

    builder = (
        Application.configure(tmp_path).with_environment("testing").with_providers(providers_file)
    )

    with pytest.raises((RuntimeError, AttributeError, TypeError)) as excinfo:
        builder.create()

    # The error must mention the path so users know where to fix it.
    assert str(providers_file) in str(excinfo.value) or "providers" in str(excinfo.value).lower()


def test_with_providers_path_wrong_type_raises_at_create(tmp_path: Path) -> None:
    """A ``providers`` attribute that isn't a list of provider classes raises."""
    providers_file = tmp_path / "bootstrap" / "providers.py"
    providers_file.parent.mkdir()
    providers_file.write_text('providers = "not a list"\n')

    builder = (
        Application.configure(tmp_path).with_environment("testing").with_providers(providers_file)
    )

    with pytest.raises((TypeError, ValueError, RuntimeError)):
        builder.create()
