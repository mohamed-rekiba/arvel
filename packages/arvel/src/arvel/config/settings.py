"""Base `pydantic-settings` class every Arvel config inherits from."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Self

from pydantic import AliasChoices, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from arvel.config._config_file_source import ConfigFileSettingsSource
from arvel.config.errors import ConfigError
from arvel.config.no_prefix import NoPrefix

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SUFFIXES = ("Settings", "Config")


def _derive_prefix(class_name: str) -> str:
    name = class_name
    for suffix in _SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            name = name[: -len(suffix)]
            break
    snake = _CAMEL_BOUNDARY.sub("_", name).upper()
    return f"{snake}_" if snake else ""


class ArvelSettings(BaseSettings):
    """Base class for typed configuration sections.

    Behavior:
    - ``env_prefix`` is auto-derived from the class name (``DbConfig`` → ``DB_``).
      Override by setting ``model_config["env_prefix"]`` in the subclass.
    - ``env_nested_delimiter="_"`` — nested fields use a single underscore.
    - ``env_file=".env"`` — loaded if present.
    - ``extra="ignore"`` — unknown env vars don't blow up.
    - ``case_sensitive=False``.

    Subclasses that need strict ``.env`` parsing (``extra="forbid"``) should
    opt into ``dotenv_filtering="match_prefix"`` *themselves* — applying it on
    the base would silently drop legitimate aliased fields (e.g. ``DB_URL``
    reaching ``DbConfig.url``).
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_nested_delimiter="_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=None,
    )

    # Dotted path into the config-module registry. Set on subclasses that should
    # resolve from config/*.py. A "{default}" token selects a named entry.
    __config_path__: ClassVar[str | None] = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: explicit kwargs > config/*.py > env > .env > secrets > defaults.
        return (
            init_settings,
            ConfigFileSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Override env_prefix only when the subclass didn't explicitly set a non-empty one.
        # Pydantic-settings fills `env_prefix=""` by default; treat empty string as unset.
        own_raw_obj: dict[str, Any] | Any = cls.__dict__.get("model_config", {})
        explicit_prefix: str | None = None
        if isinstance(own_raw_obj, dict):
            raw_prefix = own_raw_obj.get("env_prefix")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(raw_prefix, str) and raw_prefix:
                explicit_prefix = raw_prefix
        if not explicit_prefix:
            prefix = _derive_prefix(cls.__name__)
            if prefix:
                cls.model_config["env_prefix"] = prefix

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Pydantic hook — runs AFTER ``model_fields`` is fully populated.

        Promotes fields annotated ``Annotated[T, NoPrefix]`` to read from the bare
        uppercase env var, bypassing the auto-derived ``env_prefix``.
        """
        super().__pydantic_init_subclass__(**kwargs)
        no_prefix_fields: list[str] = []
        for field_name, field_info in cls.model_fields.items():
            if any(_is_no_prefix(m) for m in field_info.metadata):
                no_prefix_fields.append(field_name)

        if not no_prefix_fields:
            return

        for field_name in no_prefix_fields:
            field_info = cls.model_fields[field_name]
            upper = field_name.upper()
            field_info.validation_alias = AliasChoices(upper, field_name)
        cls.model_rebuild(force=True)

    @classmethod
    def from_environment(cls) -> Self:
        """Load + validate the settings, wrapping ValidationError into ConfigError."""
        try:
            return cls()
        except ValidationError as exc:
            keys = ", ".join(".".join(str(p) for p in err["loc"]) for err in exc.errors())
            msg = f"Failed to load {cls.__qualname__}: invalid fields [{keys}]."
            raise ConfigError(msg) from exc


def _is_no_prefix(marker: object) -> bool:
    return marker is NoPrefix or (isinstance(marker, type) and marker is NoPrefix)
