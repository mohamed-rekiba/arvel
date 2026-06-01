"""BroadcastConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_config_defaults_to_null_driver() -> None:
    """Default broadcaster name is 'null' (fail-closed in dev)."""
    from arvel.broadcasting.config import BroadcastConfig

    config = BroadcastConfig()
    assert config.default == "null"


def test_config_accepts_valid_driver_names() -> None:
    from arvel.broadcasting.config import BroadcastConfig

    for name in ("log", "null", "redis-pubsub", "pusher"):
        BroadcastConfig.model_validate({"default": name})


def test_config_rejects_unknown_driver_name() -> None:
    """unknown default fails validation."""
    from arvel.broadcasting.config import BroadcastConfig

    with pytest.raises(ValidationError):
        BroadcastConfig.model_validate({"default": "zeromq"})


def test_config_extra_forbid() -> None:
    """extra='forbid' rejects unknown keys."""
    from arvel.broadcasting.config import BroadcastConfig

    with pytest.raises(ValidationError):
        BroadcastConfig(unknown_field="x")  # type: ignore[call-arg]


def test_config_auth_endpoint_default() -> None:
    from arvel.broadcasting.config import BroadcastConfig

    assert BroadcastConfig().auth_endpoint == "/broadcasting/auth"


def test_reverb_config_port_range_validation() -> None:
    """ReverbConfig.port is bounded to a valid port range."""
    from arvel.broadcasting.config import ReverbConfig

    with pytest.raises(ValidationError):
        ReverbConfig(app_id="x", key="k", secret="s", port=70000)
    with pytest.raises(ValidationError):
        ReverbConfig(app_id="x", key="k", secret="s", port=0)


def test_reverb_config_activity_timeout_bounded() -> None:
    from arvel.broadcasting.config import ReverbConfig

    ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=120)
    with pytest.raises(ValidationError):
        ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=10)
    with pytest.raises(ValidationError):
        ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=99999)


def test_reverb_config_trusted_proxies_default_is_empty() -> None:
    """Stage 4b MEDIUM-3: trusted_proxies defaults to empty (X-Forwarded-For ignored)."""
    from arvel.broadcasting.config import ReverbConfig

    config = ReverbConfig(app_id="x", key="k", secret="s")
    assert config.trusted_proxies == []


def test_reverb_config_trusted_proxies_accepts_cidrs_and_ips() -> None:
    """Stage 4b MEDIUM-3: trusted_proxies accepts IPs and CIDR ranges."""
    from arvel.broadcasting.config import ReverbConfig

    config = ReverbConfig(
        app_id="x",
        key="k",
        secret="s",
        trusted_proxies=["10.0.0.1", "192.168.0.0/16"],
    )
    assert config.trusted_proxies == ["10.0.0.1", "192.168.0.0/16"]
