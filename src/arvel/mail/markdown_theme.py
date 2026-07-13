"""arvel.mail.markdown_theme — a minimal Markdown "component theme" for markdown mailables:
inline-styled buttons/panels/tables + a container wrapper,
rendered through markdown-it-py alone — no template engine, no extra dependency.

``[button: Text](url)`` on its own line becomes a centered, styled call-to-action; blockquotes
become "panels" (a shaded box); GFM tables get borders/padding. The plain-text alternative is then
derived the same way as any other HTML body — stripping these (inline-styled, but still plain)
tags leaves the readable text (button/panel/heading content), so no separate text renderer is
needed (see ``Mailable.render``'s ``_strip_tags`` fallback).
"""

from __future__ import annotations

import re
from typing import Any

_BUTTON_RE = re.compile(r"^\[button:\s*(?P<text>[^\]]+)\]\((?P<url>[^)]+)\)\s*$", re.MULTILINE)

_BUTTON_HTML = (
    '<div style="text-align:center;margin:24px 0">'
    '<a href="{url}" style="background:#2d3748;color:#ffffff;padding:12px 24px;'
    'border-radius:4px;text-decoration:none;display:inline-block">{text}</a></div>'
)

_WRAPPER = (
    '<div style="font-family:sans-serif;max-width:600px;margin:0 auto;'
    'color:#1a202c;line-height:1.5">{body}</div>'
)


def _button(match: re.Match[str]) -> str:
    # escape url + text (defence in depth) — the button HTML bypasses markdown-it's own link
    # validation, so a mail body that ever interpolates untrusted data can't inject an attribute
    # break-out or a javascript: href through the [button:] convention
    import html as _html

    return _BUTTON_HTML.format(
        url=_html.escape(match["url"], quote=True), text=_html.escape(match["text"])
    )


def _style_tables(html: str) -> str:
    return (
        html.replace("<table>", '<table style="border-collapse:collapse;width:100%;margin:16px 0">')
        .replace("<th>", '<th style="border-bottom:2px solid #e2e8f0;padding:8px;text-align:left">')
        .replace("<td>", '<td style="border-bottom:1px solid #e2e8f0;padding:8px">')
    )


def _style_panels(html: str) -> str:
    return html.replace(
        "<blockquote>",
        '<blockquote style="background:#f7fafc;border-left:4px solid #4a5568;'
        'padding:12px 16px;margin:16px 0">',
    )


def render_themed(markdown_body: str, markdown_it_cls: type[Any]) -> str:
    """Render ``markdown_body`` through the component theme: the ``[button: text](url)``
    convention becomes a styled call-to-action, blockquotes become panels, GFM tables get inline
    borders — all wrapped in the theme's container. ``html=True`` so the button's raw HTML passes
    through (the source is the mailable author's own Markdown, not untrusted user input)."""
    engine = markdown_it_cls("commonmark", {"html": True}).enable("table")
    source = _BUTTON_RE.sub(_button, markdown_body)
    html = engine.render(source)
    html = _style_panels(_style_tables(html))
    return _WRAPPER.format(body=html)


__all__ = ["render_themed"]
