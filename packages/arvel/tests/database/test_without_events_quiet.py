"""Eloquent-parity: without_events + quiet persistence."""

from __future__ import annotations

from arvel.database import Model, Observer, SoftDeletes, Timestamps, id_, string
from arvel.database.events import clear_observers
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Memo(Model, Timestamps, SoftDeletes):
    __tablename__ = "memos_q"
    id: int = id_()
    body: str = string(200)


class Tally(Observer[Memo]):
    def __init__(self) -> None:
        self.events: list[str] = []

    def creating(self, instance: Memo) -> None:
        self.events.append("creating")

    def created(self, instance: Memo) -> None:
        self.events.append("created")

    def saving(self, instance: Memo) -> None:
        self.events.append("saving")

    def saved(self, instance: Memo) -> None:
        self.events.append("saved")

    def updating(self, instance: Memo) -> None:
        self.events.append("updating")

    def updated(self, instance: Memo) -> None:
        self.events.append("updated")

    def deleting(self, instance: Memo) -> None:
        self.events.append("deleting")

    def deleted(self, instance: Memo) -> None:
        self.events.append("deleted")

    def restoring(self, instance: Memo) -> None:
        self.events.append("restoring")

    def restored(self, instance: Memo) -> None:
        self.events.append("restored")


async def _setup(engine: AsyncEngine) -> Tally:
    clear_observers(Memo)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    obs = Tally()
    Memo.observe(obs)
    return obs


async def test_without_events_suppresses_all_observers(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    obs = await _setup(engine)
    async with Memo.without_events():
        memo = await Memo.create(body="quiet")
        memo.body = "still quiet"
        await memo.save()
        await memo.delete()
    assert obs.events == []


async def test_events_resume_after_block(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    async with Memo.without_events():
        await Memo.create(body="silent")
    # Firing must resume once the block exits.
    await Memo.create(body="loud")
    assert "created" in obs.events


async def test_without_events_is_reentrant(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    async with Memo.without_events():
        async with Memo.without_events():
            await Memo.create(body="inner")
        # Still suppressed after the inner block exits.
        await Memo.create(body="outer")
    assert obs.events == []
    # Fully restored after the outermost block.
    await Memo.create(body="after")
    assert obs.events == ["saving", "creating", "created", "saved"]


async def test_save_quietly(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    memo = Memo(body="q")
    await memo.save_quietly()
    assert obs.events == []
    assert await Memo.where(body="q").exists() is True


async def test_delete_quietly(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    memo = await Memo.create(body="d")
    obs.events.clear()
    await memo.delete_quietly()
    assert obs.events == []


async def test_force_delete_quietly(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    memo = await Memo.create(body="f")
    obs.events.clear()
    await memo.force_delete_quietly()
    assert obs.events == []
    assert await Memo.with_trashed().where(body="f").exists() is False


async def test_restore_quietly(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    memo = await Memo.create(body="r")
    await memo.delete()
    obs.events.clear()
    await memo.restore_quietly()
    assert obs.events == []


async def test_update_quietly(engine: AsyncEngine, session: AsyncSession) -> None:
    obs = await _setup(engine)
    memo = await Memo.create(body="u1")
    obs.events.clear()
    await memo.update_quietly(body="u2")
    assert obs.events == []
    fresh = await Memo.where(body="u2").first()
    assert fresh is not None


async def test_cancellable_hook_does_not_abort_inside_block(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    clear_observers(Memo)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    class Veto(Observer[Memo]):
        def creating(self, instance: Memo) -> bool:
            return False

    Memo.observe(Veto())
    # Outside the block the veto would raise OperationCancelledError; inside it's muted.
    async with Memo.without_events():
        memo = await Memo.create(body="forced")
    assert memo.id is not None
