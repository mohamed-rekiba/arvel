"""Mail (doc 16) — Markdown mailable bodies render to HTML (markdown-it-py)."""

from __future__ import annotations

from arvel.mail import Mailable


class Welcome(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").markdown("# Welcome\n\nThanks for **joining**.")


def test_markdown_renders_to_html() -> None:
    message = Welcome().render()
    body = message.get_content()
    assert "<h1>Welcome</h1>" in body
    assert "<strong>joining</strong>" in body
    assert message["Subject"] == "Hi"


def test_markdown_returns_self_for_chaining() -> None:
    m = Mailable()
    assert m.markdown("text") is m


def test_markdown_lists_and_links() -> None:
    m = Mailable().markdown("- one\n- two\n\n[site](https://arvel.dev)")
    html = m.render().get_content()
    assert "<li>one</li>" in html
    assert '<a href="https://arvel.dev">site</a>' in html
