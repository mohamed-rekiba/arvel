"""Naive HTML-to-plain-text fallback used by the mailer.

Used when a mailable supplies an HTML body but no plain-text alternative.
The output is a low-fidelity fallback — it strips tags, decodes entities,
and inserts paragraph breaks after block-level closes — meant for email
clients that can't render HTML and for spam scoring. It is **not** a
content-faithful rendering: links lose their hrefs, lists lose their
markers, headings lose their emphasis.

For richer conversions (preserving link URLs, list markers, table layout)
supply your own ``text_view`` template alongside ``html_view`` instead of
relying on this fallback. Mailables that ship to real users should always
provide both bodies explicitly.
"""

from __future__ import annotations

import re
from html import unescape

# Block-level closing tags trigger a blank-line break in the plain-text
# output so the result reads as paragraphs, not as one wrapped line.
_BLOCK_CLOSE_RE = re.compile(
    r"(?i)</(?:p|div|li|h[1-6]|tr|table|article|section|header|footer|main|aside|nav)\s*/?>",
)
# Self-closing or open <br>/<hr> also get treated as a single newline so
# inline breaks don't disappear into surrounding whitespace.
_BR_RE = re.compile(r"(?i)<\s*(?:br|hr)\s*/?\s*>")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    """Strip HTML tags and decode entities to produce a plain-text body.

    Returns an empty string for empty or whitespace-only input. The output
    is not guaranteed to be reversible to the original HTML.
    """
    if not html or html.isspace():
        return ""

    text = _BR_RE.sub("\n", html)
    text = _BLOCK_CLOSE_RE.sub("\n\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


__all__ = ["html_to_text"]
