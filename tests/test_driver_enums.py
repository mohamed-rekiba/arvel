"""The Manager driver selectors are StrEnums (not Literals): typed for the built-ins, but still a
plain str so they flow through the `create_<driver>_driver` dispatch and custom drivers stay open."""

from __future__ import annotations

import pytest

from arvel.broadcasting import BroadcastDriver
from arvel.cache import CacheDriver
from arvel.filesystem import FilesystemDriver
from arvel.mail import MailDriver
from arvel.queue import QueueDriver
from arvel.search import SearchDriver


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (FilesystemDriver.S3, "s3"),
        (CacheDriver.REDIS, "redis"),
        (QueueDriver.AMQP, "amqp"),
        (MailDriver.SMTP, "smtp"),
        (MailDriver.ROUND_ROBIN, "round_robin"),
        (SearchDriver.MEILISEARCH, "meilisearch"),
        (BroadcastDriver.LOG, "log"),
    ],
)
def test_driver_enum_is_its_str_value_and_flows_through_dispatch(member: str, value: str) -> None:
    assert member == value  # StrEnum member equals its str
    assert isinstance(member, str)
    assert f"create_{member}_driver" == f"create_{value}_driver"  # dispatch key is the value
