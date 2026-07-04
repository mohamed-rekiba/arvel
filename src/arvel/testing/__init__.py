"""arvel.testing — test helpers: facade fakes + a TestClient factory.

``fake(Mail)`` swaps a recording double behind a facade so assertions like
``mail.assert_sent(WelcomeMail)`` work without real I/O; ``reset_fakes()`` clears them
(call in teardown). ``client(asgi)`` wraps Litestar's TestClient. Grounded in the
testing-strategy in knowledge/port/ (golden-path).
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any, cast


class FakeMailer:
    """Records sent mailables instead of delivering them. ``sent[i]`` is the mailable and
    ``recipients[i]`` the recipient list of the same send (Laravel assertSent-with-callback
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


class FakeFilesystem:
    """A temp-dir local disk swapped in for a real one (Laravel ``Storage::fake``), plus
    assertion helpers. Wraps a :class:`arvel.filesystem.Filesystem` rather than subclassing it —
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
    """Swap ``disk`` for a fresh temp-dir local disk (Laravel ``Storage::fake``); returns a
    :class:`FakeFilesystem` with ``assert_exists``/``assert_missing``/``assert_count``. Restore
    the real driver with :func:`restore_storage` (or let ``reset_fakes`` handle every swap,
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


def reset_fakes() -> None:
    """Clear all swapped facade roots and restore any faked storage disks (call in test teardown)."""
    from arvel.support.facades import Facade

    Facade.clear_swapped()
    restore_storage()


def client(asgi: Any) -> Any:
    """A Litestar ``TestClient`` over an ASGI app (``app.as_asgi()`` / ``kernel.build()``)."""
    from litestar.testing import TestClient

    return TestClient(asgi)


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
    """``async with database_transaction(db): ...`` — run a test in a transaction that's
    always rolled back, so its DB writes don't leak into the next test."""
    return connection.begin_test_transaction(name)


def travel_to(moment: Any) -> None:
    """Freeze the clock at ``moment`` (a ``Date``) for the rest of the test — Laravel
    ``travelTo``. Pair with :func:`travel_back`. Isolated per async task (ContextVar)."""
    from arvel.dates import Date

    Date.set_test_now(moment)


def travel_back() -> None:
    """Unfreeze the clock (Laravel ``travelBack``)."""
    from arvel.dates import Date

    Date.set_test_now(None)


@contextlib.contextmanager
def freeze_time(moment: Any = None) -> Generator[Any]:
    """``with freeze_time(): ...`` — freeze the clock at ``moment`` (or the current now) inside
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


__all__ = [
    "FakeEvents",
    "FakeFilesystem",
    "FakeMailer",
    "FakeQueue",
    "assert_database_has",
    "assert_database_missing",
    "assert_soft_deleted",
    "client",
    "database_transaction",
    "fake",
    "fake_storage",
    "freeze_time",
    "reset_fakes",
    "restore_storage",
    "travel_back",
    "travel_to",
]
