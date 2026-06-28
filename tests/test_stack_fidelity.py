"""G4 — stack fidelity harness.

Each capability module, as it lands, registers a check here asserting that its
**mandated DR-0002 engine actually backs it** — e.g. a real ``litestar.Litestar``
app + Litestar-generated OpenAPI; SQLAlchemy Core constructs compiled by the
builder; a ``whenever`` type under ``Date``; Typer under the CLI. A stdlib
reimplementation of a mandated library must make its check FAIL.

*Lazy-import ≠ reimplement* (knowledge/port/00-porting-strategy.md §5b). Empty at
T0.1 (no capability modules yet); the registry grows with every engine story.
"""

from __future__ import annotations

import sys
from collections.abc import Callable


def _dates_use_whenever() -> None:
    """arvel.dates.Date must be backed by a whenever type — not stdlib datetime."""
    import whenever

    from arvel.dates import Date

    value = Date.now("UTC").raw
    assert isinstance(value, whenever.ZonedDateTime), (
        f"Date backed by {type(value)!r}, not whenever"
    )
    # DST-correct: adding a calendar day across a spring-forward keeps wall-clock time
    # (something stdlib naive arithmetic gets wrong) — whenever handles it.
    before = Date.parse("2024-03-30T12:00:00+00:00[Europe/London]")
    after = before.add(days=1)
    assert after.to_iso().startswith("2024-03-31T12:00:00"), after.to_iso()


def _localization_uses_babel() -> None:
    """The [i18n] tier must use Babel CLDR plural rules, not a hand-rolled English rule."""
    from arvel.localization import plural_category

    # Polish: 2 → 'few' (CLDR). A naive `one|other` rule cannot produce this.
    assert plural_category("pl", 2) == "few"
    assert plural_category("ar", 3) == "few"
    assert plural_category("en", 2) == "other"
    assert "babel" in sys.modules, "Babel was not used for CLDR pluralization"


def _console_uses_typer() -> None:
    """The CLI must be a Typer app with a LazyGroup — not a stdlib argv dispatcher."""
    sys.modules.pop("arvel.console.builtins", None)
    import typer

    from arvel.console import build_cli
    from arvel.console.lazy import LazyGroup

    app = build_cli()
    assert isinstance(app, typer.Typer), "CLI root is not a typer.Typer"
    assert isinstance(typer.main.get_command(app), LazyGroup), "CLI group is not the LazyGroup"
    assert "about" in LazyGroup.commands_manifest
    # LazyGroup must not import a command's module until it is invoked.
    assert "arvel.console.builtins" not in sys.modules, "LazyGroup imported a command eagerly"


# (capability name, check) — check() raises AssertionError if the mandated engine
# is not the one actually in use. Capability stories append to this list.
def _security_uses_mandated_libs() -> None:
    """Hashing on pwdlib (argon2), encryption on cryptography (Fernet)."""
    from arvel.security import Encrypter, Hasher

    hashed = Hasher().make("secret")
    assert hashed.startswith("$argon2"), f"hash not argon2/pwdlib: {hashed[:12]}"
    enc = Encrypter(Encrypter.generate_key())
    assert enc.decrypt(enc.encrypt("payload")) == "payload"
    assert "pwdlib" in sys.modules and "cryptography" in sys.modules


def _http_uses_litestar() -> None:
    """The served app must be a real litestar.Litestar with Litestar-generated OpenAPI."""
    import litestar
    from litestar.testing import TestClient

    from arvel.http import HttpKernel

    kernel = HttpKernel()

    async def ping(request: object) -> dict[str, bool]:
        return {"ok": True}

    kernel.get("/ping", ping)
    app = kernel.build()
    assert isinstance(app, litestar.Litestar), "served app is not a litestar.Litestar"
    with TestClient(app=app) as client:
        schema = client.get("/schema/openapi.json")
        assert schema.status_code == 200
        assert "/ping" in schema.json().get("paths", {}), "OpenAPI not generated from routes"


def _validation_uses_msgspec() -> None:
    """Validation + schema generation must go through msgspec (→ OpenAPI)."""
    import msgspec

    from arvel.validation import ValidationException, json_schema, validate

    class S(msgspec.Struct):
        name: str
        age: int

    obj = validate({"name": "x", "age": 3}, S)
    assert isinstance(obj, msgspec.Struct)
    props = next(iter(json_schema(S)["$defs"].values()))["properties"]
    assert "name" in props and "age" in props  # msgspec-generated JSON schema
    try:
        validate({"name": "x"}, S)
    except ValidationException:
        pass
    else:
        raise AssertionError("expected ValidationException")
    assert "msgspec" in sys.modules


def _orm_uses_sqlalchemy_core() -> None:
    """The builder must emit SQLAlchemy Core constructs that compile multi-dialect."""
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql, sqlite

    from arvel.database import Builder

    md = sa.MetaData()
    users = sa.Table(
        "users", md, sa.Column("id", sa.Integer, primary_key=True), sa.Column("active", sa.Boolean)
    )
    stmt = Builder(users).where(active=True).to_select()
    assert isinstance(stmt, sa.Select), "builder did not emit a Core Select (raw SQL?)"
    pg = str(stmt.compile(dialect=postgresql.dialect()))
    lite = str(stmt.compile(dialect=sqlite.dialect()))
    assert "users" in pg and "users" in lite
    # Same builder call, two dialects → different bind-param styles proves Core compile.
    assert pg != lite


def _cache_uses_cashews() -> None:
    """The default cache driver must instantiate a real cashews backend, not a dict."""
    from cashews import Cache

    from arvel.cache import CacheManager

    repo = CacheManager().driver()  # no app → 'array' (mem://) cashews backend
    assert isinstance(repo.client, Cache), "cache driver is not backed by cashews"


def _storage_uses_fsspec() -> None:
    """The default storage disk must be a real fsspec filesystem, not os calls."""
    from fsspec import AbstractFileSystem

    from arvel.filesystem import FilesystemManager

    disk = FilesystemManager().disk()  # no app → 'local' fsspec LocalFileSystem
    assert isinstance(disk.fs, AbstractFileSystem), "storage disk is not backed by fsspec"


def _mail_uses_aiosmtplib() -> None:
    """The smtp transport must drive a real aiosmtplib.SMTP, not stdlib smtplib."""
    import aiosmtplib

    from arvel.mail import MailManager

    transport = MailManager().driver("smtp")
    assert isinstance(transport.client, aiosmtplib.SMTP), "mail smtp driver is not aiosmtplib"


def _notifications_use_apprise() -> None:
    """The notification fan-out must use a real apprise.Apprise client."""
    import apprise

    from arvel.notifications import NotificationManager

    assert isinstance(NotificationManager().apprise(), apprise.Apprise), (
        "notifications not on apprise"
    )


def _views_use_jinja2() -> None:
    """The view factory must wrap a real jinja2 Environment, not string formatting."""
    import jinja2

    from arvel.views import ViewFactory

    factory = ViewFactory()
    assert isinstance(factory.env, jinja2.Environment), "view factory is not Jinja2"
    assert factory.env.is_async, "Jinja2 env must be async (render_async)"


def _queue_uses_taskiq() -> None:
    """The queue must run on a real taskiq broker, not a list/threading stub."""
    import taskiq

    from arvel.queue import QueueManager

    broker = QueueManager().broker
    assert isinstance(broker, taskiq.AsyncBroker), "queue is not backed by a taskiq broker"


def _image_uses_pillow() -> None:
    """Image ops must run on a real PIL.Image.Image, not a hand-rolled buffer."""
    from PIL import Image as PILImage

    from arvel.media import ImageManager

    image = ImageManager().make(8, 8)
    assert isinstance(image.raw, PILImage.Image), "image is not backed by Pillow"
    assert image.resize(4, 4).width == 4


def _video_uses_av() -> None:
    """Video must open through a real av (PyAV) container, not stdlib parsing."""
    import tempfile
    from pathlib import Path

    import av

    from arvel.media import Video

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "clip.mp4"
        container = av.open(str(path), mode="w")
        stream = container.add_stream("mpeg4", rate=1)
        stream.width, stream.height, stream.pix_fmt = 16, 16, "yuv420p"
        frame = av.VideoFrame(16, 16, "yuv420p")
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()

        video = Video.open(str(path))
        try:
            assert isinstance(video.raw, av.container.Container), "video is not backed by av"
        finally:
            video.close()


FIDELITY_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("dates → whenever", _dates_use_whenever),
    ("localization → babel", _localization_uses_babel),
    ("console → typer", _console_uses_typer),
    ("security → pwdlib/cryptography", _security_uses_mandated_libs),
    ("http → litestar", _http_uses_litestar),
    ("validation → msgspec", _validation_uses_msgspec),
    ("orm → sqlalchemy core", _orm_uses_sqlalchemy_core),
    ("cache → cashews", _cache_uses_cashews),
    ("storage → fsspec", _storage_uses_fsspec),
    ("mail → aiosmtplib", _mail_uses_aiosmtplib),
    ("notifications → apprise", _notifications_use_apprise),
    ("views → jinja2", _views_use_jinja2),
    ("queue → taskiq", _queue_uses_taskiq),
    ("image → pillow", _image_uses_pillow),
    ("video → av", _video_uses_av),
]


def test_all_capabilities_use_their_mandated_engine() -> None:
    failures: list[str] = []
    for name, check in FIDELITY_CHECKS:
        try:
            check()
        except AssertionError as exc:  # pragma: no cover - exercised once modules land
            failures.append(f"{name}: {exc}")
    assert not failures, "stack-fidelity (G4) violations:\n" + "\n".join(failures)


def test_harness_is_wired() -> None:
    """The registry exists and is the single place capabilities assert fidelity."""
    assert isinstance(FIDELITY_CHECKS, list)
