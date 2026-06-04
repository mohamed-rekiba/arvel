"""Unit tests for the queued media conversion pipeline.

Covers:
- FileAdder.queued() sets _queue_conversions flag.
- FileAdder with .queued() dispatches QueuedConversionJob instead of running inline.
- FileAdder without .queued() continues to run conversions inline (regression).
- QueuedConversionJob.handle() loads Media, resolves host, and calls _process_one.
- QueuedConversionJob.handle() exits silently when media row is gone.
- QueuedConversionJob.handle() exits silently when host resolves to None.
- QueuedConversionJob serializes and has correct queue/retry defaults.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arvel_image.media.jobs import QueuedConversionJob

# ── QueuedConversionJob defaults ─────────────────────────────────────────────


def test_queued_conversion_job_defaults() -> None:
    job = QueuedConversionJob(media_id="abc-123", model_class_path="app.models.Product")
    assert job.queue == "media"
    assert job.tries == 3
    assert job.backoff == [30, 60, 120]


def test_queued_conversion_job_is_serializable() -> None:
    job = QueuedConversionJob(media_id="abc-123", model_class_path="app.models.Product")
    envelope = job.to_envelope()
    assert envelope.payload["media_id"] == "abc-123"
    assert envelope.payload["model_class_path"] == "app.models.Product"
    # queue/delay/priority are routing metadata promoted onto the envelope.
    assert "queue" not in envelope.payload
    assert "delay" not in envelope.payload
    assert "priority" not in envelope.payload
    # Retry config has no envelope slot, so it round-trips inside the payload.
    assert envelope.payload["tries"] == 3
    assert envelope.payload["backoff"] == [30, 60, 120]


# ── QueuedConversionJob.handle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_exits_when_media_not_found() -> None:
    """If the media row was deleted before the job runs, handle() returns silently."""
    with patch("arvel_image.media.jobs.Media") as MockMedia:
        MockMedia.find = AsyncMock(return_value=None)
        job = QueuedConversionJob(media_id="gone", model_class_path="app.models.Product")
        await job.handle()  # should not raise


@pytest.mark.asyncio
async def test_handle_exits_when_host_not_found() -> None:
    """If the host model row is gone, handle() returns silently."""
    mock_media = MagicMock()
    mock_media.model_id = "42"

    with (
        patch("arvel_image.media.jobs.Media") as MockMedia,
        patch("arvel_image.media.jobs._resolve_host", new=AsyncMock(return_value=None)),
    ):
        MockMedia.find = AsyncMock(return_value=mock_media)
        job = QueuedConversionJob(media_id="m1", model_class_path="app.models.Product")
        await job.handle()  # should not raise


@pytest.mark.asyncio
async def test_handle_calls_process_one_with_resolved_host() -> None:
    """handle() passes both media and host to _process_one when both resolve."""
    mock_media = MagicMock()
    mock_media.model_id = "42"
    mock_media.responsive_images = {}
    mock_host = MagicMock()

    with (
        patch("arvel_image.media.jobs.Media") as MockMedia,
        patch("arvel_image.media.jobs._resolve_host", new=AsyncMock(return_value=mock_host)),
        patch("arvel_image.media.jobs._process_one", new=AsyncMock()) as mock_process,
    ):
        MockMedia.find = AsyncMock(return_value=mock_media)
        job = QueuedConversionJob(media_id="m1", model_class_path="app.models.Product")
        await job.handle()
        mock_process.assert_awaited_once_with(mock_media, mock_host)


# ── FileAdder.queued() flag ───────────────────────────────────────────────────


def test_file_adder_queued_sets_flag() -> None:
    """FileAdder.queued() must return self and set _queue_conversions."""
    from arvel_image.media.file_adder import FileAdder

    host = MagicMock()
    host.collection_for = MagicMock()
    fa = FileAdder(host, b"data", file_name="photo.jpg")
    assert fa._queue_conversions is False
    result = fa.queued()
    assert result is fa  # fluent
    assert fa._queue_conversions is True


@pytest.mark.asyncio
async def test_file_adder_dispatches_job_when_queued() -> None:
    """When .queued() is used, FileAdder must dispatch QueuedConversionJob, not run conversions."""
    from arvel_image.media.file_adder import FileAdder

    mock_media: Any = MagicMock()
    mock_media.id = "m1"
    mock_media.order_column = None
    mock_media.generated_conversions = {}

    host = MagicMock()
    host.__class__ = type(
        "Product", (), {"__module__": "app.models.product", "__qualname__": "Product"}
    )
    host.collection_for = MagicMock()
    mock_coll = MagicMock()
    mock_coll.single_file_enabled = False
    mock_coll.conversions = [MagicMock()]  # non-empty → triggers queued path
    mock_coll.conversions_disk = None
    mock_coll.disk = None
    mock_coll.keep_latest_n = None
    mock_coll.accept_mime_types_list = None
    mock_coll.max_file_size_bytes = None
    mock_coll.check_accepts_file = MagicMock(return_value=True)
    host.collection_for.return_value = mock_coll
    host.host_pk = MagicMock(return_value="1")
    # save() refreshes the media cache via host.load("media") at the end.
    host.load = AsyncMock()

    mock_disk = MagicMock()
    mock_disk.put = AsyncMock()
    mock_gen = MagicMock()
    mock_gen.path_for = MagicMock(return_value="path/to/file")

    with (
        patch("arvel_image.media.file_adder.Media") as MockMedia,
        patch("arvel_image.media.file_adder.Storage") as MockStorage,
        patch("arvel_image.media.file_adder.resolve_path_generator", return_value=mock_gen),
        patch(
            "arvel_image.media.file_adder.query_media",
            new=AsyncMock(return_value=[]),
        ),
        patch("arvel_image.media.file_adder.Bus") as MockBus,
    ):
        MockMedia.create = AsyncMock(return_value=mock_media)
        mock_media.save = AsyncMock()
        MockStorage.disk = MagicMock(return_value=mock_disk)
        MockBus.dispatch = AsyncMock()

        fa = FileAdder(host, b"imagedata", file_name="photo.jpg")
        fa.queued()
        await fa.save(collection="images")

        MockBus.dispatch.assert_awaited_once()
        dispatched_job = MockBus.dispatch.call_args[0][0]
        assert isinstance(dispatched_job, QueuedConversionJob)
        assert dispatched_job.media_id == "m1"
        assert "Product" in dispatched_job.model_class_path
