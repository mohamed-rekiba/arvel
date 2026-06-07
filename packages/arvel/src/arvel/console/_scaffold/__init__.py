"""Internal helpers for ``arvel new`` — skeleton templating + project-name validation.

Not a public API. Re-exported here only so call-sites inside
``arvel.console.commands.new`` can write short imports.
"""

from __future__ import annotations

from arvel.console._scaffold.context import ScaffoldContext
from arvel.console._scaffold.kits import (
    DEFAULT_KIT,
    KITS,
    KitDownloadError,
    KitSpec,
    KitUnavailableError,
    UnknownKitError,
    available_kits,
    format_kit_listing,
    resolve_kit,
)
from arvel.console._scaffold.templating import (
    TOKEN_KEYS,
    UnknownTemplateToken,
    find_unsubstituted_tokens,
    substitute,
)
from arvel.console._scaffold.validation import (
    MAX_PROJECT_NAME_LENGTH,
    PROJECT_NAME_REGEX,
    InvalidProjectName,
    resolve_target_directory,
    validate_project_name,
)

__all__ = [
    "DEFAULT_KIT",
    "KITS",
    "MAX_PROJECT_NAME_LENGTH",
    "PROJECT_NAME_REGEX",
    "TOKEN_KEYS",
    "InvalidProjectName",
    "KitDownloadError",
    "KitSpec",
    "KitUnavailableError",
    "ScaffoldContext",
    "UnknownKitError",
    "UnknownTemplateToken",
    "available_kits",
    "find_unsubstituted_tokens",
    "format_kit_listing",
    "resolve_kit",
    "resolve_target_directory",
    "substitute",
    "validate_project_name",
]
