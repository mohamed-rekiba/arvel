# File storage

`StorageManager` hands out disks behind a `StorageDisk` protocol. Drivers: `local`, `memory`, `s3`, `gcs`, `azure`.

**Source**: `packages/arvel/src/arvel/storage/` — `manager.py`, `disk.py`, `drivers/`, `config/storage_config.py`, `providers/storage_provider.py`.

## Disk protocol

```python
class StorageDisk(Protocol):
    async def exists(self, path) -> bool: ...
    async def get(self, path) -> bytes: ...
    async def put(self, path, contents) -> bool: ...
    async def delete(self, path) -> bool: ...
    async def list(self, directory="") -> list[str]: ...
    def url(self, path) -> str: ...
    def temporary_url(self, path, expiry) -> str: ...
```

`StorageManager.disk(name)` builds a disk from `StorageConfig.default` (`STORAGE_DEFAULT`, default `local`).

| Driver | `temporary_url` |
|---|---|
| `local` | HMAC signature via `TemporaryUrlSigner` — **requires `app_key`** |
| `memory` | in-memory signer |
| `s3` | `boto3.generate_presigned_url` |
| `gcs` | GCS signed URL |
| `azure` | SAS token via `generate_blob_sas` — **requires `STORAGE_AZURE_KEY`** |

The local signer derives its HMAC key from `app_key` via HKDF (`info=b"arvel-storage-tmp-url"`).

`AzureDriver.temporary_url` signs a read-only SAS token from the shared account key (`STORAGE_AZURE_ACCOUNT` + `STORAGE_AZURE_KEY`). Without a key it raises `ValueError` — the account-URL-only path has nothing to sign with.

## Provider

`StorageServiceProvider.register()` resolves `StorageConfig` plus per-driver configs, builds the manager, and binds the `Storage` facade. It reads `APP_KEY` from the process env (the same key source as the `Crypt` facade) and passes it into `StorageManager`, so `temporary_url()` on the default local disk works out of the box once `APP_KEY` is set. `boot()` is a no-op. Ships the `storage:link` command. Not a baseline provider.

## See also

- [Encryption](encryption.md) — both use HKDF over `APP_KEY`.
- [Configuration](../architecture/ARCH-006-configuration.md)
