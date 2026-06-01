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
| `azure` | **`NotImplementedError`** |

The local signer derives its HMAC key from `app_key` via HKDF (`info=b"arvel-storage-tmp-url"`).

## A wiring gap

`StorageServiceProvider` constructs `StorageManager` **without** passing `app_key`:

```python
manager = StorageManager(config=config, local_config=..., s3_config=..., ...)  # no app_key
```

> **Warning**: Because the provider doesn't pass `app_key`, `temporary_url()` on the default local disk raises `RuntimeError("LocalDriver requires app_key to generate temporary URLs")` unless something supplies the key manually (tests do). `TODO/QUESTION:` Should the provider wire `APP_KEY` into `StorageManager`?

> **Warning**: `AzureDriver.temporary_url` is not implemented — it raises. Use a different driver if you need signed URLs on Azure.

## Provider

`StorageServiceProvider.register()` resolves `StorageConfig` plus per-driver configs, builds the manager, and binds the `Storage` facade. `boot()` is a no-op. Ships the `storage:link` command. Not a baseline provider.

## See also

- [Encryption](encryption.md) — both use HKDF over `APP_KEY`.
- [Configuration](../architecture/configuration.md)
