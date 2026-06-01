"""TranslationLoader Protocol + PythonFileLoader / JsonFileLoader.

Two ready-to-use loaders ship out of the box:

- :class:`PythonFileLoader` — reads ``resources/lang/{locale}/{namespace}.py``,
 the original driver. Each file exports a module-level
 ``translations: dict[str, str | dict]``.
- :class:`JsonFileLoader` — reads ``resources/lang/{locale}/{namespace}.json``
 **or** ``resources/lang/{locale}.json`` (single-file mode). Same
 string-or-nested-dict shape as the Python driver but in JSON, so a
 single catalog can serve both backend (Python) and frontend
 (Vue I18n / i18next) consumers.

Both implement :class:`TranslationLoader` and are interchangeable —
applications wire whichever fits via :class:`arvel.providers.LangServiceProvider`
(see ``LangServiceProvider`` for the binding hook).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from arvel.i18n.exceptions import (
    TranslationFileMalformedError,
    TranslationFileMissingError,
)

TranslationValue = str | dict[str, "TranslationValue"]


@runtime_checkable
class TranslationLoader(Protocol):
    """Adapter protocol. Implement to add gettext / DB / JSON backends."""

    def load(self, locale: str, namespace: str) -> dict[str, TranslationValue]: ...


class PythonFileLoader:
    """Default loader. Reads ``resources/lang/{locale}/{namespace}.py``.

    The file MUST expose a module-level ``translations: dict[str, str | dict]``.
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def load(self, locale: str, namespace: str) -> dict[str, TranslationValue]:
        target = self._base / "resources" / "lang" / locale / f"{namespace}.py"
        if not target.exists():
            raise TranslationFileMissingError(locale, namespace)
        spec = importlib.util.spec_from_file_location(f"_arvel_lang_{locale}_{namespace}", target)
        if spec is None or spec.loader is None:
            raise TranslationFileMalformedError(f"could not load spec for {target}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "translations"):
            raise TranslationFileMalformedError(
                f"{target} missing required `translations: dict` export"
            )
        return _coerce_translations(module.translations, target)


class JsonFileLoader:
    """JSON-catalog loader. Reads ``resources/lang/{locale}/{namespace}.json``
    when a namespace is requested, **or** falls back to a single-file layout
    (``resources/lang/{locale}.json``) where every namespace lives as a
    top-level key in one shared catalog.

    The single-file layout is the recommended shape when the same catalog
    must be consumed by Vue I18n on the frontend and the backend
    Translator on the same code path — only one file to keep in sync per
    locale.

    File contents must decode to ``dict[str, str | dict]`` recursively;
    anything else raises :class:`TranslationFileMalformedError`.
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def load(self, locale: str, namespace: str) -> dict[str, TranslationValue]:
        nested = self._base / "resources" / "lang" / locale / f"{namespace}.json"
        single = self._base / "resources" / "lang" / f"{locale}.json"

        if nested.exists():
            data = self._read_json(nested)
            return _coerce_translations(data, nested)

        if single.exists():
            data = self._read_json(single)
            if not isinstance(data, dict):
                msg = (
                    f"{single} must be a JSON object whose keys are namespaces, "
                    f"got {type(data).__name__}"
                )
                raise TranslationFileMalformedError(msg)
            typed = cast("dict[object, object]", data)
            namespace_data = typed.get(namespace)
            if namespace_data is None:
                raise TranslationFileMissingError(locale, namespace)
            return _coerce_translations(namespace_data, single)

        raise TranslationFileMissingError(locale, namespace)

    @staticmethod
    def _read_json(target: Path) -> object:
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"{target} is not valid JSON: {exc.msg} (line {exc.lineno})"
            raise TranslationFileMalformedError(msg) from exc


def _coerce_translations(raw: object, target: Path) -> dict[str, TranslationValue]:
    """Validate ``raw`` matches ``dict[str, TranslationValue]``, recursively."""
    if not isinstance(raw, dict):
        raise TranslationFileMalformedError(
            f"{target} `translations` must be a dict, got {type(raw).__name__}"
        )
    typed_raw = cast("dict[object, object]", raw)
    result: dict[str, TranslationValue] = {}
    for key, value in typed_raw.items():
        if not isinstance(key, str):
            raise TranslationFileMalformedError(
                f"{target} translation key must be str, got {type(key).__name__}"
            )
        result[key] = _coerce_value(value, target)
    return result


def _coerce_value(value: object, target: Path) -> TranslationValue:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _coerce_translations(cast("dict[object, object]", value), target)
    raise TranslationFileMalformedError(
        f"{target} translation value must be str or nested dict, got {type(value).__name__}"
    )


__all__ = ["JsonFileLoader", "PythonFileLoader", "TranslationLoader", "TranslationValue"]
