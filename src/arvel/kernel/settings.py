"""Typed settings on **msgspec** — a typed, validated *view* over a ``config()`` section that
**auto-loads on instantiation** (no pydantic; DR-0005, DR-0016).

``config()`` is the single source of truth (populated from ``config/*.py``, ``with_config``, and the
environment via ``env()`` calls inside config files). A ``Settings`` subclass is a typed lens over one
section of it: set ``__config_key__`` and just instantiate — it reads + validates that section. It
does **not** read the environment itself, so there is exactly one config pipeline and a typed setting
can never disagree with ``config()``:

    class MailSettings(Settings):
        __config_key__ = "mail"
        host: str = "localhost"
        port: int = 25
        use_tls: bool = False

    mail = MailSettings()        # reads + validates config("mail")
    mail.port                    # int, coerced ("587" → 587) — and == config("mail.port")
    MailSettings(port=2525)      # explicit kwargs override the config section

Values are coerced + validated through ``msgspec.convert`` (``"587"``→int, ``"true"``→bool, …),
raising ``msgspec.ValidationError`` on a missing required field or a bad value. With no application
running (e.g. a pure unit test), instantiation skips the config read and uses defaults + any explicit
kwargs. ``.env`` files feed ``os.environ`` via ``load_dotenv`` (read by config files). msgspec is core
— typed settings need no extra. Grounded in knowledge/port/03 + DR-0005/DR-0016.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, ClassVar, Self

import msgspec

# Sentinel: distinguishes "no _config_source given" (read the global config) from an explicit source
# of ``None``/``{}`` (a specific app whose section is unset → use defaults, not the global config).
_NO_CONFIG_SOURCE = object()


class _SettingsMeta(msgspec.StructMeta):
    """Make instantiating a ``Settings`` auto-load + validate its ``config()`` section.

    ``cls(**overrides)`` reads ``config(__config_key__)`` (when an app is running), applies explicit
    keyword overrides on top, then validates via ``msgspec.convert``. Positional construction
    (``cls(a, b)``) bypasses the config read and builds the struct directly.

    ``__call__`` is runtime-only: to type-checkers a ``Settings`` constructs like any msgspec struct
    (via ``dataclass_transform``), so ``MailSettings()`` keeps its precise type and field-aware call
    checking — the config-loading is the runtime augmentation layered on top.
    """

    if not TYPE_CHECKING:

        def __call__(cls, *args, **overrides):
            if args:  # explicit positional construction → pure struct, no config read
                return super().__call__(*args, **overrides)
            from collections.abc import Mapping

            from arvel.kernel.globals import has_application

            data: dict[str, object] = {}
            # `_config_source` (when supplied) overrides the global config — a specific app's section,
            # passed by Manager._settings so Manager(app) honors *that* app's config, not the global.
            source = overrides.pop("_config_source", _NO_CONFIG_SOURCE)
            if source is not _NO_CONFIG_SOURCE:
                if isinstance(source, Mapping):
                    data = dict(source)
            else:
                key = getattr(cls, "__config_key__", None)
                if key is not None and has_application():
                    from arvel.kernel.config import config

                    section = config(key)
                    if isinstance(section, Mapping):
                        data = dict(section)
            data.update(overrides)  # explicit kwargs win over the config section
            return msgspec.convert(data, cls, strict=False)


class Settings(msgspec.Struct, metaclass=_SettingsMeta):
    """Base for a typed settings group — a typed, validated view over a ``config()`` section.

    Set ``__config_key__`` to the dotted config key for the section; instantiating reads + validates
    it (see the module docstring)."""

    __config_key__: ClassVar[str | None] = None

    @classmethod
    def from_source(cls, source: Any) -> Self:
        """Build the settings from an explicit config ``source`` (a section mapping) instead of the
        global ``config()`` — used by ``Manager(app)`` so it reads *that* app's section. ``None`` ⇒
        an empty section (defaults apply)."""
        # the metaclass consumes ``_config_source``; pass it via **dict so it isn't type-checked
        # against the (synthesized) struct __init__ signature.
        return cls(**{"_config_source": source if source is not None else {}})


def load_dotenv(path: str | os.PathLike[str]) -> None:
    """Load ``KEY=VALUE`` pairs from a ``.env`` file into ``os.environ`` — **existing env wins**.

    Parsing is delegated to `python-dotenv <https://pypi.org/project/python-dotenv/>`_, which handles
    quoting, ``export KEY=…`` prefixes, inline ``#`` comments, multiline values, and ``${VAR}``
    expansion correctly (the previous hand-rolled parser silently dropped malformed lines). A real
    environment variable always takes precedence (``override=False``), and a missing file is a no-op.
    Lazy-imports python-dotenv so ``import arvel`` stays light.
    """
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(dotenv_path=os.fspath(path), override=False)
