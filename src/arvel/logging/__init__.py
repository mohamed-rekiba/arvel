"""Public logger module for application and framework usage."""

from __future__ import annotations

from arvel.logging.channels import configure_channels as configure_channels
from arvel.logging.channels import reset_channels as reset_channels
from arvel.logging.context import bind_log_context as bind_log_context
from arvel.logging.context import clear_log_context as clear_log_context
from arvel.logging.context import scoped_log_context as scoped_log_context
from arvel.logging.context import unbind_log_context as unbind_log_context
from arvel.logging.errors import (
    InvalidLogChannelConfigurationError as InvalidLogChannelConfigurationError,
)
from arvel.logging.errors import UnknownLogChannelError as UnknownLogChannelError
from arvel.logging.facade import LoggerFacade as LoggerFacade
from arvel.logging.facade import create_log_facade

Log = create_log_facade()

__all__ = [
    "InvalidLogChannelConfigurationError",
    "Log",
    "LoggerFacade",
    "UnknownLogChannelError",
    "bind_log_context",
    "clear_log_context",
    "configure_channels",
    "reset_channels",
    "scoped_log_context",
    "unbind_log_context",
]
