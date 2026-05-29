"""Tests for the HTML-to-plain-text fallback used by the mailer."""

from __future__ import annotations

import pytest
from arvel.support.html_to_text import html_to_text


class TestHtmlToText:
    def test_empty_input_returns_empty_string(self) -> None:
        assert html_to_text("") == ""

    def test_whitespace_only_input_returns_empty_string(self) -> None:
        assert html_to_text("   \n\t  ") == ""

    def test_strips_simple_tags(self) -> None:
        assert html_to_text("<p>Hello world</p>") == "Hello world"

    def test_decodes_html_entities(self) -> None:
        assert html_to_text("<p>caf&eacute; &amp; tea</p>") == "café & tea"

    def test_decodes_numeric_entities(self) -> None:
        assert html_to_text("<p>&#x2603;</p>") == "\u2603"

    def test_block_elements_become_paragraph_breaks(self) -> None:
        out = html_to_text("<p>First.</p><p>Second.</p>")
        assert out == "First.\n\nSecond."

    def test_br_becomes_single_newline(self) -> None:
        out = html_to_text("Line 1<br>Line 2<br/>Line 3")
        assert out == "Line 1\nLine 2\nLine 3"

    def test_self_closing_hr_becomes_newline(self) -> None:
        out = html_to_text("Above<hr/>Below")
        assert out == "Above\nBelow"

    def test_collapses_excess_whitespace(self) -> None:
        out = html_to_text("<p>multiple    spaces</p>")
        assert out == "multiple spaces"

    def test_collapses_multiple_blank_lines(self) -> None:
        out = html_to_text("<p>A</p><p></p><p></p><p>B</p>")
        # No more than one blank line between paragraphs
        assert "\n\n\n" not in out

    def test_preserves_text_outside_tags(self) -> None:
        out = html_to_text("Plain text with <b>bold</b> word.")
        assert out == "Plain text with bold word."

    def test_handles_unclosed_tags_gracefully(self) -> None:
        # Naive stripper — no DOM correctness guarantees, but should not crash
        assert "broken" in html_to_text("<p>broken")

    @pytest.mark.parametrize(
        ("html", "expected_substr"),
        [
            ("<h1>Title</h1>", "Title"),
            ("<div>Block content</div>", "Block content"),
            ("<li>Item</li>", "Item"),
        ],
    )
    def test_block_level_tags_are_stripped(self, html: str, expected_substr: str) -> None:
        assert expected_substr in html_to_text(html)
