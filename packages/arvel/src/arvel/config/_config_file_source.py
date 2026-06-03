"""pydantic-settings source that overlays values from loaded ``config/*.py`` modules.

A typed settings class opts in by declaring ``__config_path__`` — a dotted path
into the module registry populated by ``ApplicationBuilder.with_config_dir``. The
path may contain a ``{default}`` token, resolved against ``<stem>.default`` so a
config file's ``default`` selects a named entry (Laravel ``connections``/``stores``/
``disks`` semantics).

Placed above the env source in ``settings_customise_sources`` so config-file
values win over env, which still wins over field defaults. The source returns
only keys that match the model's fields; everything else falls through to env.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING, cast

from pydantic_settings import PydanticBaseSettingsSource

from arvel.config._lookup_registry import config as read_config

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings


def _as_mapping(raw: object) -> dict[str, object]:
    """Coerce a registry value (dict, module, or namespace) to a flat dict."""
    if isinstance(raw, dict):
        return {str(k): v for k, v in cast("dict[object, object]", raw).items()}
    if isinstance(raw, (types.ModuleType, types.SimpleNamespace)):
        attrs: dict[str, object] = vars(raw)
        return {
            k: v
            for k, v in attrs.items()
            if not k.startswith("_") and not callable(v) and not isinstance(v, types.ModuleType)
        }
    return {}


def _field_names(settings_cls: type[BaseSettings]) -> frozenset[str]:
    return frozenset(settings_cls.model_fields.keys())


class ConfigFileSettingsSource(PydanticBaseSettingsSource):
    """Reads a class's ``__config_path__`` node from the config-module registry."""

    def get_field_value(self, field: object, field_name: str) -> tuple[None, str, bool]:
        # __call__ returns the whole mapping at once; per-field lookup is unused.
        del field
        return None, field_name, False

    def __call__(self) -> dict[str, object]:
        path_template = getattr(self.settings_cls, "__config_path__", None)
        if not isinstance(path_template, str) or not path_template:
            return {}

        stem = path_template.split(".", 1)[0]
        selector: str | None = None
        if "{default}" in path_template:
            chosen = read_config(f"{stem}.default")
            if not isinstance(chosen, str) or not chosen:
                return {}
            selector = chosen
            path = path_template.replace("{default}", chosen)
        else:
            path = path_template

        data = _as_mapping(read_config(path))
        fields = _field_names(self.settings_cls)
        result: dict[str, object] = {k: v for k, v in data.items() if k in fields}

        # Faithful named-entry: surface the active name on the selector field so
        # drivers resolve from `default` even when the entry dict doesn't repeat it.
        if "connection" in fields and "connection" not in result:
            chosen = selector if selector is not None else read_config(f"{stem}.default")
            if isinstance(chosen, str) and chosen:
                result["connection"] = chosen

        return result


__all__ = ["ConfigFileSettingsSource"]
