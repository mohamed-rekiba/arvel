# File Storage

Uploads, exports, private documents, public assets—files show up everywhere. Arvel models storage behind **`StorageContract`**, so your code talks to an abstraction while configuration picks **local disk**, **S3-compatible object storage**, or a **null** driver for tests.

At **v0.1.0**, the same pattern applies as elsewhere in the framework: bind the contract in the container, inject it where you need blobs, and swap drivers per environment without branching business logic.

## Drivers you will see

- **Local** — filesystem paths under your app’s control; great for development and single-node deploys
- **S3** — AWS or compatible APIs for production-scale object storage
- **Null** — discards or no-ops, so tests do not touch disk or the network

Media and other subsystems may compose **`StorageContract`**—for example, a media manager can store originals and derivatives through the same interface.

## What the contract gives you

`StorageContract` is an ABC with async methods for the operations you expect from a cloud disk adapter: read, write, delete, exists, copy, visibility, and URL generation where applicable. Your feature code should depend on the contract, not on `boto3` or `pathlib` directly.

```python
from arvel.storage.contracts import StorageContract


async def store_avatar(storage: StorageContract, user_id: int, data: bytes) -> str:
    path = f"avatars/{user_id}/profile.bin"
    await storage.put(path, data)
    return path
```

## Configuration and testing

Production typically points S3 credentials and buckets at environment variables; local development might use a `./storage` directory. In tests, **`StorageFake`** (or the null driver) lets you assert paths and contents without I/O.

## Laravel parallels

If you have used Laravel’s `Storage::disk()`, this is the same separation: **named capabilities in code, physical location in config**. Arvel leans on async I/O and explicit contracts so type checkers and tests stay honest.

Treat uploads as **untrusted input**: validate size and MIME type at the boundary, virus-scan if your threat model requires it, and never expose raw internal paths in public URLs—generate signed URLs or proxy through your app when needed.

That way storage stays boring, which is exactly what you want it to be.
