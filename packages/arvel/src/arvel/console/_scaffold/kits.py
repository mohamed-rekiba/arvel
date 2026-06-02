"""Typed registry of starter kits available to ``arvel new --kit <name>``."""

from __future__ import annotations

import importlib
import importlib.resources
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEFAULT_KIT",
    "KITS",
    "KitNotInstalledError",
    "KitSpec",
    "UnknownKitError",
    "available_kits",
    "format_kit_listing",
    "resolve_kit",
]

DEFAULT_KIT = "api"


class UnknownKitError(Exception):
    """Raised when ``--kit`` names a kit not in :data:`KITS`."""

    def __init__(self, name: str, available: list[str]) -> None:
        listing = ", ".join(sorted(available)) if available else "(none)"
        super().__init__(f"unknown kit {name!r}; available: {listing}")
        self.name = name
        self.available = available


class KitNotInstalledError(Exception):
    """Raised when a registered kit's companion package isn't importable.

    The kit is known to the registry but its source tree can't be located
    at runtime — typically because the companion package isn't installed.
    """

    def __init__(self, name: str, package: str, original: BaseException) -> None:
        super().__init__(
            f"kit {name!r} is registered but its companion package "
            f"{package!r} is not installed: {original}"
        )
        self.name = name
        self.package = package
        self.original = original


@dataclass(frozen=True)
class KitSpec:
    """One starter kit's metadata + lazy source-tree resolver."""

    name: str
    description: str
    resolve: Callable[[], Path]

    def root(self) -> Path:
        """Return the kit's source tree, raising if it can't be located."""
        path = self.resolve()
        if not path.is_dir():
            msg = f"kit {self.name!r} source tree not found at {path}"
            raise FileNotFoundError(msg)
        return path


def _api_kit_root() -> Path:
    """Resolve the bundled framework skeleton tree."""
    return Path(str(importlib.resources.files("arvel").joinpath("_skeleton")))


def _ecommerce_kit_root() -> Path:
    """Resolve via the ``arvel_ecommerce_kit`` companion package.

    Wrapping the import keeps the framework usable even when the kit
    package isn't installed — the failure surfaces as
    :class:`KitNotInstalledError` only when the user requests
    ``--kit ecommerce``.
    """
    try:
        module = importlib.import_module("arvel_ecommerce_kit")
    except ImportError as exc:
        raise KitNotInstalledError(
            name="ecommerce",
            package="arvel-ecommerce-kit",
            original=exc,
        ) from exc
    kit_root_fn: Callable[[], Path] = module.kit_root
    return kit_root_fn()


KITS: dict[str, KitSpec] = {
    "api": KitSpec(
        name="api",
        description="API-only Arvel project from the framework's bundled skeleton (default)",
        resolve=_api_kit_root,
    ),
    "ecommerce": KitSpec(
        name="ecommerce",
        description=(
            "Full-stack e-commerce kit: FastAPI backend + Vue 3 frontend + "
            "PostgreSQL / Redis / RabbitMQ / MinIO / Mailpit "
            "(requires arvel-ecommerce-kit package)"
        ),
        resolve=_ecommerce_kit_root,
    ),
}


def available_kits() -> list[str]:
    """Return registered kit names in registration order."""
    return list(KITS.keys())


def resolve_kit(name: str) -> KitSpec:
    """Return the :class:`KitSpec` for ``name`` or raise :class:`UnknownKitError`."""
    if name not in KITS:
        raise UnknownKitError(name, available_kits())
    return KITS[name]


def format_kit_listing() -> str:
    """Render the available-kits block shown alongside friendly errors."""
    longest = max(len(spec.name) for spec in KITS.values())
    lines = ["Available kits:"]
    lines.extend(f"  {spec.name.ljust(longest)}  {spec.description}" for spec in KITS.values())
    return "\n".join(lines)
