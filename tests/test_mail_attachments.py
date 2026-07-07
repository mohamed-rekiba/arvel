"""Mail (doc 16) — Mailable.attach / attach_data add MIME parts to the rendered message."""

from __future__ import annotations

from pathlib import Path

from arvel.mail import Mailable


class Doc(Mailable):
    def build(self) -> Mailable:
        return self.subject("Invoice").html("<p>see attached</p>")


def _attachments(message: object) -> list:
    return list(message.iter_attachments())  # type: ignore[attr-defined]


def test_attach_file_from_disk(tmp_path: Path) -> None:
    f = tmp_path / "invoice.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    message = Doc().attach(str(f)).render()
    parts = _attachments(message)
    assert len(parts) == 1
    assert parts[0].get_filename() == "invoice.pdf"
    assert parts[0].get_content_type() == "application/pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF-1.4 fake"


def test_attach_data_in_memory() -> None:
    message = Doc().attach_data(b"col1,col2\n1,2", "report.csv", mime="text/csv").render()
    parts = _attachments(message)
    assert len(parts) == 1
    assert parts[0].get_filename() == "report.csv"
    assert parts[0].get_content_type() == "text/csv"


def test_custom_name_and_multiple(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01")
    message = (
        Doc().attach(str(f), name="renamed.bin").attach_data(b"hi", "note.txt", mime="text/plain")
    ).render()
    names = {p.get_filename() for p in _attachments(message)}
    assert names == {"renamed.bin", "note.txt"}


def test_no_attachments_still_renders() -> None:
    message = Doc().render()
    assert _attachments(message) == []
    assert message["Subject"] == "Invoice"


async def test_attach_from_storage_reads_a_real_disk(tmp_path: Path) -> None:
    import fsspec

    from arvel.filesystem import Filesystem

    disk = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    await disk.put("invoices/1.pdf", b"%PDF from storage")

    mailable = Doc().attach_from_storage(disk, "invoices/1.pdf", mime="application/pdf")
    await mailable.resolve_attachments()  # the disk read happens here, off the render path
    parts = _attachments(mailable.render())
    assert len(parts) == 1
    assert parts[0].get_filename() == "1.pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF from storage"


def test_embed_data_renders_an_inline_image_with_matching_cid() -> None:
    class Card(Mailable):
        cid: str = ""

        def build(self) -> Mailable:
            self.cid = self.embed_data(b"\x89PNG-fake", mime="image/png")
            return self.subject("Hi").html(f'<p><img src="{self.cid}"></p>')

    card = Card()
    message = card.render()
    ref = card.cid.removeprefix("cid:")

    images = [p for p in message.walk() if p.get_content_type() == "image/png"]
    assert len(images) == 1
    assert images[0]["Content-ID"] == f"<{ref}>"
    assert images[0].get_payload(decode=True) == b"\x89PNG-fake"

    html = message.get_body(preferencelist=("html",))
    assert html is not None and f"cid:{ref}" in html.get_content()
