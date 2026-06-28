"""arvel.kernel — the inner ring: container, lifecycle, providers, config, pipeline, hooks.

Imports only ``arvel.contracts`` and ``arvel.support`` (+ stdlib); never a capability
module (G1, enforced by import-linter). Grows across Phase 1 (T1.x).
"""

from __future__ import annotations

from arvel.kernel.application import Application, ApplicationBuilder, AppSettings
from arvel.kernel.boot_report import BootReporter
from arvel.kernel.bootstrap import lifespan
from arvel.kernel.config import Repository, config, env
from arvel.kernel.container import (
    BindingResolutionError,
    CircularDependencyError,
    Container,
    ContextualBindingBuilder,
)
from arvel.kernel.discovery import bootstrap_providers, clear_cache, discover_providers
from arvel.kernel.exceptions import ExceptionHandler
from arvel.kernel.globals import app, has_application, set_application
from arvel.kernel.logging import LogManager
from arvel.kernel.service_provider import ServiceProvider
from arvel.kernel.settings import Settings, load_dotenv

__all__ = [
    "AppSettings",
    "Application",
    "ApplicationBuilder",
    "BindingResolutionError",
    "BootReporter",
    "CircularDependencyError",
    "Container",
    "ContextualBindingBuilder",
    "ExceptionHandler",
    "LogManager",
    "Repository",
    "ServiceProvider",
    "Settings",
    "app",
    "bootstrap_providers",
    "clear_cache",
    "config",
    "discover_providers",
    "env",
    "has_application",
    "lifespan",
    "load_dotenv",
    "set_application",
]
