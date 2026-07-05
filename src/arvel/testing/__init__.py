"""arvel.testing — test helpers: facade fakes + a TestClient factory.

``fake(Mail)`` swaps a recording double behind a facade so assertions like
``mail.assert_sent(WelcomeMail)`` work without real I/O; ``reset_fakes()`` clears them
(call in teardown). ``client(asgi)`` wraps Litestar's TestClient. Grounded in the
testing-strategy in knowledge/port/ (golden-path).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator, Mapping, Sequence
from typing import Any, cast


class FakeMailer:
    """Records sent mailables instead of delivering them. ``sent[i]`` is the mailable and
    ``recipients[i]`` the recipient list of the same send (assertSent-with-callback
    parity: tests can assert WHO a mail went to, not just that it went)."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.recipients: list[list[str]] = []

    def to(self, *recipients: Any) -> _PendingFake:
        return _PendingFake(self, [str(r) for r in recipients])

    def assert_sent(self, mailable_cls: type) -> None:
        if not any(isinstance(m, mailable_cls) for m in self.sent):
            raise AssertionError(
                f"expected a {mailable_cls.__name__} to be sent; sent={self.sent!r}"
            )

    def assert_nothing_sent(self) -> None:
        if self.sent:
            raise AssertionError(f"expected no mail; sent={self.sent!r}")


class _PendingFake:
    def __init__(self, mailer: FakeMailer, recipients: list[str] | None = None) -> None:
        self._mailer = mailer
        self._recipients = recipients or []

    def cc(self, *recipients: Any) -> _PendingFake:
        return self

    def bcc(self, *recipients: Any) -> _PendingFake:
        return self

    async def send(self, mailable: Any) -> bool:
        self._mailer.sent.append(mailable)
        self._mailer.recipients.append(self._recipients)
        return True


class FakeQueue:
    """Records pushed jobs instead of enqueuing them."""

    def __init__(self) -> None:
        self.pushed: list[tuple[type, tuple[Any, ...], dict[str, Any]]] = []

    async def push(
        self,
        job_cls: type,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        self.pushed.append((job_cls, tuple(args), dict(kwargs or {})))

    def assert_pushed(self, job_cls: type) -> None:
        if not any(job is job_cls for job, _, _ in self.pushed):
            pushed = [job.__name__ for job, _, _ in self.pushed]
            raise AssertionError(f"expected {job_cls.__name__} to be pushed; pushed={pushed}")

    def assert_nothing_pushed(self) -> None:
        if self.pushed:
            raise AssertionError("expected no jobs pushed")

    def assert_dispatched(self, job_cls: type) -> None:
        """Alias of:meth:`assert_pushed` — ``Bus::assertDispatched`` naming. arvel models
        job dispatch as one fake regardless of facade (``Queue``/``Bus`` are the same push path);
        see:func:`fake_bus`."""
        self.assert_pushed(job_cls)

    def assert_not_dispatched(self, job_cls: type) -> None:
        """Alias of the inverse of:meth:`assert_pushed` — ``Bus::assertNotDispatched``."""
        if any(job is job_cls for job, _, _ in self.pushed):
            raise AssertionError(f"expected {job_cls.__name__} NOT to be pushed")


class FakeEvents:
    """Records dispatched events instead of invoking listeners."""

    def __init__(self) -> None:
        self.dispatched: list[Any] = []

    def listen(self, *args: Any, **kwargs: Any) -> None:
        """Accepted + ignored under the fake."""

    async def dispatch(self, event: Any, *payload: Any) -> list[Any]:
        self.dispatched.append(event)
        return []

    async def until(self, event: Any, *payload: Any) -> Any:
        self.dispatched.append(event)
        return None

    def assert_dispatched(self, event_type: type) -> None:
        if not any(isinstance(e, event_type) for e in self.dispatched):
            raise AssertionError(f"expected a {event_type.__name__} to be dispatched")


class FakeNotifications:
    """Records notifications instead of delivering them.
    ``sent[i]`` is ``(notifiable, notification, channels)``."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, Any, list[str]]] = []

    async def send(self, notifiable: Any, notification: Any) -> dict[str, Any]:
        channels = notification.via(notifiable)
        self.sent.append((notifiable, notification, channels))
        return dict.fromkeys(channels, "faked")

    async def send_now(
        self, notifiable: Any, notification: Any, channels: list[str] | None = None
    ) -> dict[str, Any]:
        return await self.send(notifiable, notification)

    def assert_sent_to(
        self,
        notifiable: Any,
        notification_cls: type,
        callback: Callable[[Any], bool] | None = None,
    ) -> None:
        matches = [
            note
            for who, note, _ in self.sent
            if who is notifiable and isinstance(note, notification_cls)
        ]
        if callback is not None:
            matches = [note for note in matches if callback(note)]
        if not matches:
            raise AssertionError(
                f"expected a {notification_cls.__name__} sent to {notifiable!r}; sent={self.sent!r}"
            )

    def assert_not_sent_to(self, notifiable: Any, notification_cls: type) -> None:
        matches = [
            note
            for who, note, _ in self.sent
            if who is notifiable and isinstance(note, notification_cls)
        ]
        if matches:
            raise AssertionError(
                f"expected no {notification_cls.__name__} sent to {notifiable!r}; found {matches!r}"
            )

    def assert_nothing_sent(self) -> None:
        if self.sent:
            raise AssertionError(f"expected no notifications sent; sent={self.sent!r}")

    def assert_count(self, n: int) -> None:
        if len(self.sent) != n:
            raise AssertionError(f"expected {n} notification(s) sent; found {len(self.sent)}")


_FAKE_FOR_ACCESSOR: dict[str, type] = {
    "mail": FakeMailer,
    "queue": FakeQueue,
    "events": FakeEvents,
}


def fake(facade: Any) -> Any:
    """Swap a recording fake behind ``facade`` (by its accessor); return it for assertions."""
    accessor = facade.accessor()
    fake_obj = _FAKE_FOR_ACCESSOR[accessor]()
    facade.swap(fake_obj)
    return fake_obj


def fake_bus() -> FakeQueue:
    """Fake job dispatch — an alias of ``fake(Queue)``: arvel already
        models ``Bus``/``Queue`` dispatch as the one push path, so this returns the same
    :class:`FakeQueue` rather than a second, duplicate double. Extend with
        ``assert_dispatched_chain``/``assert_batched`` once batching (story 18) lands."""
    from arvel.support.facades import Queue

    return cast("FakeQueue", fake(Queue))


_faked_notifications = False


def fake_notifications() -> FakeNotifications:
    """Swap the ``notifications`` container binding for a recording double (``Notification::fake``) so ``notifiable.notify(...)`` records instead of delivering.

    Reaches into the container directly (``app().instance(...)``) rather than a ``Facade`` — there's
    no ``Notification`` facade in arvel (notifications are sent via the ``Notifiable`` mixin, which
    resolves ``app().make("notifications")`` itself);:func:`restore_notifications` (or
    ``reset_fakes``) undoes it."""
    from arvel.kernel.globals import app

    global _faked_notifications
    fake_obj = FakeNotifications()
    app().instance("notifications", fake_obj)
    _faked_notifications = True
    return fake_obj


def restore_notifications() -> None:
    """Restore the real ``notifications`` binding after:func:`fake_notifications`. A no-op if
        nothing was faked (or the app that held the swap is already gone — best-effort, like
    :func:`restore_storage`)."""
    global _faked_notifications
    if not _faked_notifications:
        return
    from arvel.kernel.globals import app, has_application

    if has_application():
        app().forget("notifications")
    _faked_notifications = False


class FakeFilesystem:
    """A temp-dir local disk swapped in for a real one, plus
    assertion helpers. Wraps a:class:`arvel.filesystem.Filesystem` rather than subclassing it —
    ``Filesystem`` isn't designed for extension, and every disk method it needs is proxied
    through ``__getattr__``, so it's a drop-in stand-in wherever ``Storage.disk(name)`` hands
    one out."""

    def __init__(self, disk: Any) -> None:
        self._disk = disk

    def __getattr__(self, name: str) -> Any:
        return getattr(self._disk, name)

    async def assert_exists(self, path: str) -> None:
        if not await self._disk.exists(path):
            raise AssertionError(f"expected {path!r} to exist on the faked disk")

    async def assert_missing(self, path: str) -> None:
        if await self._disk.exists(path):
            raise AssertionError(f"expected {path!r} to be missing from the faked disk")

    async def assert_count(self, directory: str, count: int) -> None:
        found = await self._disk.all_files(directory)
        if len(found) != count:
            raise AssertionError(
                f"expected {count} files in {directory!r}; found {len(found)}: {found}"
            )


_faked_disks: set[str] = set()


def fake_storage(disk: str = "local") -> FakeFilesystem:
    """Swap ``disk`` for a fresh temp-dir local disk; returns a
    :class:`FakeFilesystem` with ``assert_exists``/``assert_missing``/``assert_count``. Restore
        the real driver with:func:`restore_storage` (or let ``reset_fakes`` handle every swap,
        including this one, in teardown).

        Implemented against ``FilesystemManager.swap_disk`` rather than the generic facade
        ``swap()``: ``Storage`` proxies its *default* disk, but a fake usually targets one named disk
        (often not the default) while leaving the others real — swapping the whole facade root can't
        express that, so this reaches into the manager's per-disk cache instead."""
    import tempfile

    import fsspec

    from arvel.filesystem import Filesystem, FilesystemManager
    from arvel.kernel.globals import app

    manager: FilesystemManager = app("filesystem")
    # fsspec ships no full stubs (see arvel.filesystem._fsspec) — funnel through Any at this
    # one boundary rather than let a partially-typed stub leak into a strict pyright error.
    fsspec_any: Any = fsspec
    fake_disk = Filesystem(
        fsspec_any.filesystem("file"), root=tempfile.mkdtemp(prefix="arvel-fake-")
    )
    manager.swap_disk(disk, fake_disk)
    _faked_disks.add(disk)
    return FakeFilesystem(fake_disk)


def restore_storage(disk: str | None = None) -> None:
    """Restore the real driver for ``disk`` (or every faked disk, if omitted) after
    :func:`fake_storage`. A no-op if nothing was faked."""
    names = list(_faked_disks) if disk is None else [disk]
    if not names:
        return
    from arvel.filesystem import FilesystemManager
    from arvel.kernel.globals import app

    manager: FilesystemManager = app("filesystem")
    for name in names:
        manager.forget(name)
        _faked_disks.discard(name)


_http_faked = False


def fake_http(mapping: Mapping[str, Any] | None = None) -> Any:
    """Fake the ``Http`` client for this test — routes through
    ``arvel.support.facades.Http.fake`` so ``arvel.testing`` is the one import surface; returns the
    underlying client (``assert_sent``/``assert_not_sent``/``assert_sent_count``/``recorded``, plus
    ``Http.response(...)`` for canned bodies).:func:`reset_fakes` restores the real transport."""
    from arvel.kernel.globals import app
    from arvel.support.facades import Http

    global _http_faked
    Http.fake(mapping)
    _http_faked = True
    return app("http")


def restore_http() -> None:
    """Restore the real ``Http`` transport after:func:`fake_http`. A no-op if nothing was faked
    (or the app that held the swap is already gone — best-effort, like:func:`restore_storage`)."""
    global _http_faked
    if not _http_faked:
        return
    from arvel.kernel.globals import app, has_application

    if has_application():
        app("http").restore()
    _http_faked = False


def reset_fakes() -> None:
    """Clear all swapped facade roots and restore any faked storage disks/HTTP transport/notification
    binding (call in test teardown)."""
    from arvel.support.facades import Facade

    Facade.clear_swapped()
    restore_storage()
    restore_http()
    restore_notifications()


def _dotted_get(data: Any, key: str, default: Any) -> Any:
    """dotted-key lookup into parsed JSON (``"user.name"``, ``"items.0.id"``)."""
    current: Any = data
    for part in key.split("."):
        if isinstance(current, Mapping) and part in current:
            mapping = cast("Mapping[str, Any]", current)
            current = mapping[part]
            continue
        if isinstance(current, list) and part.lstrip("-").isdigit():
            items = cast("list[Any]", current)
            index = int(part)
            if -len(items) <= index < len(items):
                current = items[index]
                continue
        return default
    return current


_MISSING = object()


class TestResponse:
    """Wraps an HTTP test response with expressive assertions.
    ``.raw`` is the escape hatch to the full underlying response (an ``httpx.Response`` — Litestar's
    ``TestClient`` is an ``httpx.Client``). Every assertion returns ``self`` (fluent)."""

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def assert_status(self, n: int) -> TestResponse:
        if self.raw.status_code != n:
            raise AssertionError(
                f"expected status {n}, got {self.raw.status_code}: {self.raw.text!r}"
            )
        return self

    def assert_ok(self) -> TestResponse:
        return self.assert_status(200)

    def assert_created(self) -> TestResponse:
        return self.assert_status(201)

    def assert_no_content(self) -> TestResponse:
        return self.assert_status(204)

    def assert_not_found(self) -> TestResponse:
        return self.assert_status(404)

    def assert_forbidden(self) -> TestResponse:
        return self.assert_status(403)

    def assert_unauthorized(self) -> TestResponse:
        return self.assert_status(401)

    def assert_unprocessable(self) -> TestResponse:
        return self.assert_status(422)

    def assert_redirect(self, to: str | None = None) -> TestResponse:
        if not (300 <= self.raw.status_code < 400):
            raise AssertionError(f"expected a redirect status, got {self.raw.status_code}")
        if to is not None:
            location = self.raw.headers.get("location")
            if location != to:
                raise AssertionError(f"expected a redirect to {to!r}, got {location!r}")
        return self

    def assert_json(self, fragment: Mapping[str, Any]) -> TestResponse:
        """Subset match (extra keys tolerated); ``fragment`` keys are dotted paths."""
        data = self.raw.json()
        for key, expected in fragment.items():
            actual = _dotted_get(data, key, _MISSING)
            if actual != expected:
                raise AssertionError(
                    f"expected json[{key!r}] == {expected!r}; got {actual!r} (body: {data!r})"
                )
        return self

    def assert_json_path(self, path: str, value: Any) -> TestResponse:
        actual = _dotted_get(self.raw.json(), path, _MISSING)
        if actual != value:
            raise AssertionError(f"expected json path {path!r} == {value!r}; got {actual!r}")
        return self

    def assert_json_count(self, n: int, path: str | None = None) -> TestResponse:
        data = self.raw.json() if path is None else _dotted_get(self.raw.json(), path, _MISSING)
        if data is _MISSING:
            raise AssertionError(f"expected a countable array at {path!r}; the path is absent")
        # assertJsonCount targets arrays — a dict/str at the path is not a countable
        # collection (counting its keys/chars would silently pass on the wrong shape)
        if not isinstance(data, (list, tuple)):
            raise AssertionError(
                f"expected an array at {path or '<root>'!r}; got {type(data).__name__}"
            )
        count = len(cast("Sequence[Any]", data))
        if count != n:
            raise AssertionError(f"expected {n} item(s) at {path or '<root>'!r}; got {count}")
        return self

    def assert_json_missing(self, fragment: Mapping[str, Any]) -> TestResponse:
        data = self.raw.json()
        for key in fragment:
            if _dotted_get(data, key, _MISSING) is not _MISSING:
                raise AssertionError(f"expected json to be missing {key!r}; found in {data!r}")
        return self

    def assert_see(self, text: str) -> TestResponse:
        if text not in self.raw.text:
            raise AssertionError(f"expected body to contain {text!r}; body was {self.raw.text!r}")
        return self

    def assert_header(self, name: str, value: str | None = None) -> TestResponse:
        actual = self.raw.headers.get(name)
        if actual is None:
            raise AssertionError(
                f"expected header {name!r} to be present; headers={self.raw.headers!r}"
            )
        if value is not None and actual != value:
            raise AssertionError(f"expected header {name!r} == {value!r}, got {actual!r}")
        return self

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)


_RESPONSE_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "request"})


class _WrappedTestClient:
    """Wraps Litestar's ``TestClient`` so every verb call returns a:class:`TestResponse` instead of
    the raw response; everything else (the context-manager protocol, cookies,...) proxies straight
    through to the real client."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._raw, name)
        if name not in _RESPONSE_VERBS:
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> TestResponse:
            return TestResponse(attr(*args, **kwargs))

        return _wrapped

    def __enter__(self) -> _WrappedTestClient:
        self._raw.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._raw.__exit__(*exc_info)


def client(asgi: Any) -> Any:
    """A Litestar ``TestClient`` over an ASGI app (``app.as_asgi()`` / ``kernel.build()``), wrapped
    so every verb call (``get``/``post``/...) returns a:class:`TestResponse` with expressive
    assertions."""
    from litestar.testing import TestClient

    return _WrappedTestClient(TestClient(asgi))


async def _matching_count(
    connection: Any, table: str, conditions: dict[str, Any], *, soft_deleted: bool = False
) -> int:
    import sqlalchemy as sa

    from arvel.database import Builder

    names = {*conditions} | ({"deleted_at"} if soft_deleted else set[str]())
    columns = [cast("Any", sa.Column(name)) for name in names] or [cast("Any", sa.Column("id"))]
    ad_hoc = sa.Table(table, sa.MetaData(), *columns)
    query = Builder(ad_hoc, connection)
    for column, expected in conditions.items():
        query = query.where(column, "=", expected)
    if soft_deleted:
        query = query.where_not_null("deleted_at")
    count: int = await query.count()
    return count


async def assert_database_has(connection: Any, table: str, **conditions: Any) -> None:
    """Assert at least one row in ``table`` matches ``conditions``."""
    if await _matching_count(connection, table, conditions) == 0:
        raise AssertionError(f"expected a row in {table!r} matching {conditions}")


async def assert_database_missing(connection: Any, table: str, **conditions: Any) -> None:
    """Assert no row in ``table`` matches ``conditions``."""
    if await _matching_count(connection, table, conditions) > 0:
        raise AssertionError(f"expected NO row in {table!r} matching {conditions}")


async def assert_soft_deleted(connection: Any, table: str, **conditions: Any) -> None:
    """Assert a matching row exists and is soft-deleted (``deleted_at`` set)."""
    if await _matching_count(connection, table, conditions, soft_deleted=True) == 0:
        raise AssertionError(f"expected a soft-deleted row in {table!r} matching {conditions}")


def database_transaction(connection: Any, name: str | None = None) -> Any:
    """``async with database_transaction(db):...`` — run a test in a transaction that's
    always rolled back, so its DB writes don't leak into the next test."""
    return connection.begin_test_transaction(name)


def travel_to(moment: Any) -> None:
    """Freeze the clock at ``moment`` (a ``Date``) for the rest of the test
    ``travelTo``. Pair with:func:`travel_back`. Isolated per async task (ContextVar)."""
    from arvel.dates import Date

    Date.set_test_now(moment)


def travel_back() -> None:
    """Unfreeze the clock."""
    from arvel.dates import Date

    Date.set_test_now(None)


@contextlib.contextmanager
def freeze_time(moment: Any = None) -> Generator[Any]:
    """``with freeze_time():...`` — freeze the clock at ``moment`` (or the current now) inside
    the block and restore the prior state on exit, even on error."""
    from arvel.dates import Date
    from arvel.dates import now as _now

    previous = Date.test_now()  # restore exactly what was there (None or a prior freeze)
    target = moment if moment is not None else _now()
    Date.set_test_now(target)
    try:
        yield target
    finally:
        Date.set_test_now(previous)


# --- console test helpers --------------------------------------------------------------
#
# ponytail: this section duck-types just enough of `arvel.console` (Command/Prompter/signature
# parsing/Artisan dispatch) to run an app-registered command or closure, rather than importing it —
# import-linter's G1 layers contract puts `arvel.console` *above* `arvel.testing` (console may
# import testing; testing may not import console), so `Artisan.call`/`Command`/`Prompter` aren't
# reachable from here even via a lazy import (import-linter's static analysis catches those too).
# Ceiling: only app-registered `Command` classes/`Console.command(...)` closures are reachable this
# way (mirrors `arvel.console.kernel._artisan_dispatch`'s own split) — a *built-in* framework
# command (`migrate`, `make:*`,...) isn't; drive those with Typer's own `CliRunner` directly
# (``from typer.testing import CliRunner``). Upgrade path: if a shared parser/dispatcher ever moves
# below the layer line, swap this out for the real thing.


class ConsoleResult:
    """The outcome of:func:`artisan` — exit code + captured stdout/stderr."""

    def __init__(self, exit_code: int, output: str) -> None:
        self.exit_code = exit_code
        self.output = output

    def assert_exit_code(self, n: int) -> ConsoleResult:
        if self.exit_code != n:
            raise AssertionError(
                f"expected exit code {n}, got {self.exit_code}; output:\n{self.output}"
            )
        return self

    def assert_output_contains(self, s: str) -> ConsoleResult:
        if s not in self.output:
            raise AssertionError(f"expected output to contain {s!r}; output was:\n{self.output}")
        return self


def _command_name(cls: type) -> str:
    """Mirrors ``arvel.console.kernel.command_name`` (can't import it — see the module note)."""
    signature = (getattr(cls, "signature", "") or "").strip()
    if signature:
        return signature.split()[0]
    from arvel.support import Str

    return Str.snake(cls.__name__)


def _parse_signature_tokens(signature: str) -> list[tuple[str, bool, str | None]]:
    """``(name, is_option, default)`` per ``{...}`` token — the common forms only (``{name}``/
    ``{name?}``/``{name=default}``/``{--flag}``/``{--opt=}``); no variadics (``{arg*}``) or shortcuts
    (``{--S|flag}``). ``default`` is the positional's ``=value`` when present, else ``None``. Mirrors
    ``arvel.console.closure.parse_signature`` (can't import it — console is above testing in the DAG)."""
    import re

    tokens: list[tuple[str, bool, str | None]] = []
    for raw in re.findall(r"\{([^{}]+)\}", signature):
        if raw.startswith("--"):
            body = raw[2:]
            tokens.append((body[:-1] if body.endswith("=") else body, True, None))
        elif "=" in raw:
            name, default = raw.split("=", 1)
            tokens.append((name, False, default))
        elif raw.endswith("?"):
            tokens.append((raw[:-1], False, None))
        else:
            tokens.append((raw, False, None))
    return tokens


def _bind_command_line(signature: str, rest: Sequence[str]) -> dict[str, Any]:
    """Raw CLI tokens (post command-name) -> ``{token_name: value}``, per ``signature``'s grammar —
    positionals assigned in order (an omitted ``{name=default}`` positional gets its default), value
    options as ``--name=value`` (a bare ``--flag`` becomes ``True``).

    ponytail: value options must use ``--opt=value``, not space-separated ``--opt value`` — matching
    that would mean reimplementing typer's parser here (which testing can't import). Ceiling, not a
    bug: use the ``=`` form in artisan() calls."""
    tokens = _parse_signature_tokens(signature)
    positionals = [(name, default) for name, is_option, default in tokens if not is_option]
    option_names = {name for name, is_option, _default in tokens if is_option}
    values: dict[str, Any] = {}
    pos_i = 0
    for tok in rest:
        if tok.startswith("--"):
            key, sep, val = tok[2:].partition("=")
            if key in option_names:
                values[key] = val if sep else True
            continue
        if pos_i < len(positionals):
            values[positionals[pos_i][0]] = tok
            pos_i += 1
    # fill omitted positionals that declared a default (parity with the real CLI's {name=default})
    for name, default in positionals[pos_i:]:
        if default is not None:
            values[name] = default
    return values


class _SeededPrompter:
    """Duck-typed stand-in for ``arvel.console.prompts.Prompter`` — the same seeded-answers
    semantics (an exhausted/empty seeded answer means "accept the default"), for the ``ask``/
    ``secret``/``confirm``/``choice``/``anticipate`` names ``Command`` delegates to."""

    def __init__(self, answers: Sequence[str] | None) -> None:
        self._answers = list(answers) if answers is not None else []
        self._i = 0

    def _next(self) -> str:
        value = self._answers[self._i] if self._i < len(self._answers) else ""
        self._i += 1
        return value

    def ask(self, label: str, default: str | None = None) -> str:
        return self._next() or (default or "")

    def secret(self, label: str) -> str:
        return self._next()

    def confirm(self, label: str, default: bool = False) -> bool:
        seeded = self._next()
        return seeded.strip().lower() in ("y", "yes", "true", "1") if seeded else default

    def choice(self, label: str, options: Sequence[str], default: str | None = None) -> str:
        return self._next() or (default or "")

    def anticipate(self, label: str, suggestions: Sequence[str], default: str | None = None) -> str:
        return self._next() or (default or "")


class _TestOutput:
    """Duck-typed stand-in for ``arvel.console.ConsoleOutput`` — everything a ``Command`` writes
    goes into one buffer (:attr:`ConsoleResult.output`); no color/table-width fidelity, just text
    a test can search with ``assert_output_contains``."""

    def __init__(self, buffer: list[str]) -> None:
        self._buffer = buffer

    def info(self, message: str) -> None:
        self._buffer.append(message)

    def line(self, message: str = "") -> None:
        self._buffer.append(message)

    def comment(self, message: str) -> None:
        self._buffer.append(message)

    def question(self, message: str) -> None:
        self._buffer.append(message)

    def error(self, message: str) -> None:
        self._buffer.append(message)

    def warn(self, message: str) -> None:
        self._buffer.append(message)

    def new_line(self, n: int = 1) -> None:
        self._buffer.extend([""] * n)

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self._buffer.append(" ".join(str(h) for h in headers))
        for row in rows:
            self._buffer.append(" ".join(str(cell) for cell in row))

    def with_progress_bar(self, iterable: Any, *, label: str = "") -> Any:
        yield from iterable


def _run_capturing_exit(run: Callable[[], None]) -> int:
    """Run ``run`` (an ``asyncio.run(...)`` call), turning a clean ``typer.Exit``/``SystemExit``
    into its exit code — mirrors ``arvel.console.kernel._run_and_capture_exit`` (can't import it)."""
    import typer

    try:
        run()
    except typer.Exit as exc:
        return exc.exit_code
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


def artisan(app: Any, command: str, input: Sequence[str] | None = None) -> ConsoleResult:
    """Run an app-registered console command (a ``Command`` class or a ``routes/console.pyConsole.command(...)`` closure) against a booted ``app`` and capture its exit code + output. ``input`` pre-seeds prompt answers in the order they're
    asked (``Command.ask``/``confirm``/``choice``/...). Only app-registered commands are reachable
    this way — see the module note above ``ConsoleResult`` for why, and the built-in-command
    workaround."""
    import asyncio
    import contextlib
    import inspect
    import io

    from arvel.kernel.globals import app as _active_app
    from arvel.kernel.globals import has_application, set_application

    name, *rest = command.split()
    buffer: list[str] = []
    prompter = _SeededPrompter(input)

    closure = getattr(app, "console_commands", {}).get(name)
    cls = None
    if closure is None:
        cls = next(
            (c for c in getattr(app, "command_classes", []) if _command_name(c) == name), None
        )
    if closure is None and cls is None:
        raise ValueError(f"artisan(): {name!r} is not registered on this app")

    previous = _active_app() if has_application() else None
    set_application(app)
    stray_output = io.StringIO()
    try:
        with contextlib.redirect_stdout(stray_output), contextlib.redirect_stderr(stray_output):
            if closure is not None:
                # ponytail: closures have no injectable prompter (unlike Command) — `input` only
                # pre-seeds prompts for the Command-class branch below.
                values = _bind_command_line(getattr(closure, "signature", "") or "", rest)

                async def _run_closure() -> None:
                    result = app.call(closure.handler, **values)
                    if inspect.isawaitable(result):
                        await result

                exit_code = _run_capturing_exit(lambda: asyncio.run(_run_closure()))
            else:
                if cls is None:  # invariant: the guard above raised when cls was None
                    raise RuntimeError("command class unexpectedly missing after resolution")
                values = _bind_command_line(getattr(cls, "signature", "") or "", rest)
                instance = cls(output=_TestOutput(buffer), prompter=prompter)
                instance.bind_parsed(values)

                async def _run_class() -> None:
                    result = app.call((instance, "handle"))
                    if inspect.isawaitable(result):
                        await result

                exit_code = _run_capturing_exit(lambda: asyncio.run(_run_class()))
    finally:
        set_application(previous)
    if stray := stray_output.getvalue():
        buffer.append(stray.rstrip("\n"))
    return ConsoleResult(exit_code, "\n".join(buffer))


__all__ = [
    "ConsoleResult",
    "FakeEvents",
    "FakeFilesystem",
    "FakeMailer",
    "FakeNotifications",
    "FakeQueue",
    "TestResponse",
    "artisan",
    "assert_database_has",
    "assert_database_missing",
    "assert_soft_deleted",
    "client",
    "database_transaction",
    "fake",
    "fake_bus",
    "fake_http",
    "fake_notifications",
    "fake_storage",
    "freeze_time",
    "reset_fakes",
    "restore_http",
    "restore_notifications",
    "restore_storage",
    "travel_back",
    "travel_to",
]
