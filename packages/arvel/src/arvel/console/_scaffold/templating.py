"""Literal string-replacement templating for skeleton files.

No template engine — token substitution only. Three tokens,
three ``str.replace`` calls, plus a post-condition that asserts no stray
``{{ }}`` tokens remain (catches template typos at install time, not at
user runtime). Contract surface only — bodies raise ``NotImplementedError``
until the scaffold implementation lands.
"""

from __future__ import annotations

import re
from typing import Final

TOKEN_KEYS: Final[tuple[str, ...]] = (
    "project_name",
    "project_name_pascal",
    "python_version",
)
"""Names accepted in the ``tokens`` dict passed to ``substitute``.

The dict's keys must be exactly these strings (the function builds
``{{ <key> }}`` patterns internally — callers don't write the braces).
"""

_UNSUBSTITUTED_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{\{\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\}\}"
)


class UnknownTemplateToken(ValueError):  # noqa: N818 — public API name pre-dates linter rule
    """Raised when ``substitute`` finds a ``{{ token }}`` it cannot resolve.

    Indicates a typo in a template file or a missing entry in the tokens
    dict. Carries the offending token name for diagnostics.
    """


def substitute(content: str, tokens: dict[str, str]) -> str:
    """Replace every ``{{ key }}`` occurrence in ``content`` with the matching value.

    Validates that:
    1. Every key in ``tokens`` is in ``TOKEN_KEYS`` (unknown keys → ValueError).
    2. After substitution, no ``{{ <name> }}`` pattern remains in the output
       (unsubstituted tokens → ``UnknownTemplateToken``).

    Returns the substituted content.
    """
    unknown_keys = set(tokens) - set(TOKEN_KEYS)
    if unknown_keys:
        msg = (
            f"tokens dict contains key(s) outside TOKEN_KEYS: "
            f"{sorted(unknown_keys)}; allowed: {list(TOKEN_KEYS)}"
        )
        raise ValueError(msg)

    # Replace every `{{ key }}` form (tolerant of surrounding whitespace inside the braces).
    # We use a single regex pass so repeats and varied spacing are handled uniformly.
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in tokens:
            msg = f"unknown template token: {{{{ {key} }}}}"
            raise UnknownTemplateToken(msg)
        return tokens[key]

    pattern = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
    result = pattern.sub(_replace, content)

    # Post-condition: no stray `{{ ... }}` patterns remain. This catches token
    # forms that slipped past the regex above (unlikely, but cheap insurance).
    stragglers = find_unsubstituted_tokens(result)
    if stragglers:
        msg = f"unsubstituted tokens remain after substitution: {stragglers}"
        raise UnknownTemplateToken(msg)
    return result


def find_unsubstituted_tokens(content: str) -> list[str]:
    """Return every ``{{ name }}`` pattern still present in ``content``.

    Returned strings include the braces (``"{{ project_name }}"``) so they
    can be quoted verbatim in error messages.
    """
    return _UNSUBSTITUTED_TOKEN_PATTERN.findall(content)
