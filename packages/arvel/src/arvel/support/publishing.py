"""Publishing registry — Laravel ``vendor:publish`` parity.

A package's :class:`~arvel.providers.ServiceProvider` can call
:meth:`~arvel.providers.ServiceProvider.publishes` to register source-to-
destination file mappings under a named tag. The ``arvel vendor:publish``
console command consumes the registry and copies the registered files into
the consumer app, optionally rewriting migration filenames with a current
UTC timestamp so they slot into ``database/migrations/`` in order.

Migrations are flagged with ``is_migration=True`` because they are the
common case and need filename rewriting to land at the right spot in the
migration order. Plain config files / asset publishes flow through the
same registry without rewriting.
"""

from __future__ import annotations

import datetime
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "PublishRegistry",
    "Publishable",
    "rewrite_migration_filename",
]


@dataclass(frozen=True)
class Publishable:
    """A single file the consumer can publish via ``arvel vendor:publish``.

    Attributes:
        source: Absolute path to the file shipped inside the package.
        destination: Absolute path where the consumer wants the file. For
            migrations this is the *directory* + the *seed filename* — the
            actual basename is rewritten with a UTC timestamp at publish
            time so the file lands in chronological order inside
            ``database/migrations/``.
        tag: Group label. ``"default"`` when none is supplied. The CLI's
            ``--tag`` flag filters on this.
        provider: Fully-qualified class name of the registering
            ``ServiceProvider``. The CLI's ``--provider`` flag filters on
            this.
        is_migration: When True, ``destination`` is treated as a directory
            target and the filename is rewritten with a UTC timestamp at
            publish time.
    """

    source: Path
    destination: Path
    tag: str
    provider: str
    is_migration: bool


class PublishRegistry:
    """Process-singleton record of every publishable a provider registered.

    Bound on the :class:`~arvel.application.Application` so multiple apps
    in the same Python process (notably tests) get distinct registries.
    """

    def __init__(self) -> None:
        self._items: list[Publishable] = []

    def add(self, items: list[Publishable]) -> None:
        """Append publishables to the registry. Order is preserved."""
        self._items.extend(items)

    def all(self) -> list[Publishable]:
        """Return every registered publishable (defensive copy)."""
        return list(self._items)

    def by_tag(self, tag: str) -> list[Publishable]:
        """Return publishables whose tag matches ``tag``."""
        return [item for item in self._items if item.tag == tag]

    def by_provider(self, provider: str) -> list[Publishable]:
        """Return publishables registered by ``provider``.

        Matches when ``provider`` equals either the fully-qualified class
        name or the bare class name — Laravel allows either form in the
        ``--provider`` flag.
        """
        bare = provider.rsplit(".", 1)[-1]
        return [
            item
            for item in self._items
            if item.provider == provider or item.provider.rsplit(".", 1)[-1] == bare
        ]

    def tags(self) -> list[str]:
        """Return all distinct tags in registration order."""
        seen: set[str] = set()
        out: list[str] = []
        for item in self._items:
            if item.tag not in seen:
                seen.add(item.tag)
                out.append(item.tag)
        return out

    def providers(self) -> list[str]:
        """Return all distinct providers in registration order."""
        seen: set[str] = set()
        out: list[str] = []
        for item in self._items:
            if item.provider not in seen:
                seen.add(item.provider)
                out.append(item.provider)
        return out


def rewrite_migration_filename(
    source: Path,
    destination_dir: Path,
    *,
    now: datetime.datetime | None = None,
    used: set[Path] | None = None,
) -> Path:
    """Return the timestamped destination path for a migration.

    The source basename is taken verbatim minus any leading timestamp
    prefix. Stubs may be shipped as either ``create_xxx.py`` (no prefix) or
    ``YYYY_MM_DD_HHMMSS_create_xxx.py`` (with one); both are accepted.

    If ``used`` is supplied, the function disambiguates against names
    already chosen this run by appending microseconds when needed —
    publishing two stubs in the same second still yields distinct
    filenames.
    """
    base = _strip_timestamp_prefix(source.name)
    moment = now if now is not None else datetime.datetime.now(datetime.UTC)

    candidate = destination_dir / f"{moment.strftime('%Y_%m_%d_%H%M%S')}_{base}"
    if used is None or candidate not in used:
        if used is not None:
            used.add(candidate)
        return candidate

    # Same-second collision — disambiguate with microseconds.
    time.sleep(0.001)
    moment_us = datetime.datetime.now(datetime.UTC)
    candidate = destination_dir / f"{moment_us.strftime('%Y_%m_%d_%H%M%S_%f')}_{base}"
    used.add(candidate)
    return candidate


_TIMESTAMP_PREFIX_LEN = 17  # YYYY_MM_DD_HHMMSS_ before the descriptive name


def _strip_timestamp_prefix(name: str) -> str:
    """Remove a leading ``YYYY_MM_DD_HHMMSS_`` prefix if present."""
    if len(name) <= _TIMESTAMP_PREFIX_LEN:
        return name
    head = name[:_TIMESTAMP_PREFIX_LEN]
    if (
        head[4] == "_"
        and head[7] == "_"
        and head[10] == "_"
        and head[16] == "_"
        and head[:4].isdigit()
        and head[5:7].isdigit()
        and head[8:10].isdigit()
        and head[11:16].isdigit()
    ):
        return name[_TIMESTAMP_PREFIX_LEN:]
    return name


def normalize_publish_paths(
    paths: Mapping[str | Path, str | Path],
    *,
    base_path: Path,
    tag: str,
    provider: str,
    is_migrations: bool,
) -> list[Publishable]:
    """Translate a ``ServiceProvider.publishes()`` mapping into ``Publishable``s.

    Resolves both source and destination to absolute paths; relative
    destinations are anchored at ``base_path`` (the framework
    ``Application.base_path``).
    """
    out: list[Publishable] = []
    for src, dest in paths.items():
        src_path = Path(src).resolve()
        dest_path = Path(dest)
        if not dest_path.is_absolute():
            dest_path = (base_path / dest_path).resolve()
        out.append(
            Publishable(
                source=src_path,
                destination=dest_path,
                tag=tag,
                provider=provider,
                is_migration=is_migrations,
            ),
        )
    return out
