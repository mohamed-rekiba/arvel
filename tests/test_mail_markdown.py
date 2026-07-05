"""Mail (doc 16) — Markdown mailable bodies render to HTML (markdown-it-py)."""

from __future__ import annotations

from arvel.mail import Mailable


class Welcome(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").markdown("# Welcome\n\nThanks for **joining**.")


def _html_part(message: object) -> str:
    body = message.get_body(preferencelist=("html",))  # type: ignore[attr-defined]
    assert body is not None
    return str(body.get_content())


def test_markdown_renders_to_html() -> None:
    message = Welcome().render()
    body = _html_part(message)
    assert "<h1>Welcome</h1>" in body
    assert "<strong>joining</strong>" in body
    assert message["Subject"] == "Hi"


def test_markdown_returns_self_for_chaining() -> None:
    m = Mailable()
    assert m.markdown("text") is m


def test_markdown_lists_and_links() -> None:
    m = Mailable().markdown("- one\n- two\n\n[site](https://arvel.dev)")
    html = _html_part(m.render())
    assert "<li>one</li>" in html
    assert '<a href="https://arvel.dev">site</a>' in html


def test_markdown_renders_a_styled_button() -> None:
    m = Mailable().markdown("Thanks!\n\n[button: View Order](https://arvel.test/o/1)")
    html = _html_part(m.render())
    assert '<a href="https://arvel.test/o/1"' in html
    assert "border-radius" in html  # the theme's button styling, not a bare markdown link
    assert "View Order" in html


def test_markdown_styles_panels_and_tables() -> None:
    body = "> a heads-up\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = _html_part(Mailable().markdown(body).render())
    assert '<blockquote style="background' in html
    assert '<table style="border-collapse' in html


def test_markdown_mail_has_a_readable_text_alternative() -> None:
    message = (
        Mailable()
        .markdown("# Hi\n\nThanks for **joining**.\n\n[button: Go](https://arvel.test)")
        .render()
    )
    text_part = message.get_body(preferencelist=("plain",))
    assert text_part is not None
    text = text_part.get_content()
    assert "Hi" in text and "Thanks for joining." in text and "Go" in text
    assert "<" not in text  # no leaked HTML tags
