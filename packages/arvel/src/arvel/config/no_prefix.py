"""``NoPrefix`` marker for ``Annotated[T, NoPrefix]`` on ``ArvelSettings`` fields.

Fields annotated with ``NoPrefix`` bypass the auto-derived ``env_prefix`` and read from
the bare uppercase field name.
"""

from __future__ import annotations


class NoPrefix:
    """Marker: read this field from the bare uppercase env var, no prefix."""
