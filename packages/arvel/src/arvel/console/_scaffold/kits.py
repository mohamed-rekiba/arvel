"""Typed registry of starter kits available to ``arvel new --kit <name>``."""

from __future__ import annotations

import importlib.resources
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEFAULT_KIT",
    "KITS",
    "KitDownloadError",
    "KitSpec",
    "KitUnavailableError",
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


class KitUnavailableError(Exception):
    """A registered kit can't be provided right now.

    ``hint`` carries kit-specific, accurate guidance — never a blanket
    ``pip install``, since the e-commerce kit ships as a GitHub Release
    tarball, not a PyPI package.
    """

    def __init__(self, name: str, hint: str, original: BaseException | None = None) -> None:
        super().__init__(f"kit {name!r} is unavailable: {hint}")
        self.name = name
        self.hint = hint
        self.original = original


class KitDownloadError(KitUnavailableError):
    """Fetching the kit's release tarball failed — network, 404, or bad checksum."""


@dataclass(frozen=True)
class KitSpec:
    """One starter kit's metadata + lazy source-tree resolver."""

    name: str
    description: str
    resolve: Callable[[], Path]
    # Printed after ``cd <project>`` in ``arvel new`` success output (no leading spaces).
    next_step_commands: tuple[str, ...] = ("uv run arvel serve",)

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
    """Resolve the e-commerce kit tree — local checkout first, else download.

    The kit isn't a package: not on PyPI, not bundled in the wheel. In an Arvel
    checkout the source sits at ``kits/arvel-ecommerce-kit``, so contributors
    scaffold straight from it. Everyone else (``uv tool install arvel``) gets
    the newest ``arvel-ecommerce-kit-v*`` release tarball, fetched on first use.
    """
    local = _local_kit_source()
    if local is not None:
        return local
    # Imported lazily: keeps httpx off the CLI startup path and avoids a
    # kits ↔ remote_kit import cycle.
    from arvel.console._scaffold.remote_kit import fetch_ecommerce_kit

    return fetch_ecommerce_kit()


def _local_kit_source() -> Path | None:
    """Return ``kits/arvel-ecommerce-kit`` from an Arvel checkout, if present."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "kits" / "arvel-ecommerce-kit"
        if (candidate / "backend").is_dir():
            return candidate
    return None


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
            "(downloaded from GitHub releases on first use)"
        ),
        resolve=_ecommerce_kit_root,
        next_step_commands=(
            "source .venv/bin/activate",
            "make env",
            "make up",
            "make migrate",
            "make seed",
        ),
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
