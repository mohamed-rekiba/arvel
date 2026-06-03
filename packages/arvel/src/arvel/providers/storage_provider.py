"""StorageServiceProvider — registers the StorageManager and Storage facade."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, TypeVar

from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.config.storage_config import LocalConfig, StorageConfig
    from arvel.console import Command
    from arvel.storage import StorageManager

_T = TypeVar("_T")


class StorageServiceProvider(ServiceProvider):
    """Binds StorageManager to the container and wires the Storage facade."""

    def register(self) -> None:
        from arvel.config.storage_config import (
            AzureConfig,
            GcsConfig,
            LocalConfig,
            S3Config,
            StorageConfig,
        )
        from arvel.facades.storage import Storage
        from arvel.storage import StorageManager

        c = self.app.container

        def _cfg(cls: type[_T], default: _T) -> _T:
            return c.make(cls) if c.bound(cls) else default

        config = _cfg(StorageConfig, StorageConfig())
        local_config = _cfg(LocalConfig, LocalConfig())
        s3_config = _cfg(S3Config, S3Config())
        gcs_config = _cfg(GcsConfig, GcsConfig())
        azure_config = _cfg(AzureConfig, AzureConfig())

        c.instance(StorageConfig, config)

        # Same APP_KEY source as the Crypt facade — it lives in the process env, not .env-only.
        app_key = os.environ.get("APP_KEY", "")
        manager = StorageManager(
            config=config,
            local_config=local_config,
            s3_config=s3_config,
            gcs_config=gcs_config,
            azure_config=azure_config,
            app_key=app_key,
        )
        c.instance(StorageManager, manager)
        Storage.bind(c)

        # Routes must be registered in register(), not boot(): Router.register_with_app()
        # runs synchronously during create_asgi(), before the async boot pass (see ADR-080).
        self._register_serve_route(manager, config, local_config, app_key)

    def _register_serve_route(
        self,
        manager: StorageManager,
        config: StorageConfig,
        local_config: LocalConfig,
        app_key: str,
    ) -> None:
        """Serve local-disk files at STORAGE_LOCAL_URL when serve is on (Laravel serve => true)."""
        url_path = local_config.url
        if config.default != "local" or not local_config.serve or not url_path.startswith("/"):
            return

        import mimetypes

        from starlette.responses import Response

        from arvel.routing import Route
        from arvel.storage.exceptions import StoragePathError
        from arvel.storage.url_signer import TemporaryUrlSigner

        disk = manager.disk("local")
        signer = TemporaryUrlSigner(app_key.encode(), url_path) if app_key else None
        prefix = url_path.rstrip("/")

        async def serve_local(
            path: str, token: str | None = None, expires: str | None = None
        ) -> Response:
            if (
                token is not None
                and expires is not None
                and (signer is None or not signer.verify(path, token, expires))
            ):
                return Response(status_code=403)
            try:
                contents = await disk.get(path)
            except FileNotFoundError, StoragePathError:
                return Response(status_code=404)
            media_type, _ = mimetypes.guess_type(path)
            return Response(
                contents,
                media_type=media_type or "application/octet-stream",
                headers={"Cache-Control": "public, max-age=3600"},
            )

        Route.get(f"{prefix}/{{path:path}}", name="storage.local", include_in_schema=False)(
            serve_local
        )

    async def boot(self) -> None:
        pass

    def commands(self) -> list[type[Command] | Command]:
        from arvel.console.commands.storage_link import StorageLinkCommand

        return [StorageLinkCommand]


__all__ = ["StorageServiceProvider"]
