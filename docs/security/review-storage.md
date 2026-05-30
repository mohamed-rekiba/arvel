# Security Review — Storage

Area: Filesystem and S3-compatible object storage, media upload pipeline.

## Scope

`Storage` facade, disk drivers (local, S3), media conversion pipeline, file upload
validation, and path traversal mitigations.

## Findings

No critical or high findings. Upload validation rejects non-image MIME types and
enforces a maximum file size. Storage paths are constructed from UUIDs, not
user-supplied filenames, eliminating path traversal risk.

## Controls Verified

- MIME type validated against an allowlist before accepting uploads
- File extension derived from detected MIME type, not client-supplied name
- Storage paths use UUID-based keys — no user input in path construction
- S3 presigned URLs expire after a configurable TTL (default 15 minutes)
- Local disk driver restricts paths to the configured storage root

## Next Review

Revisit when adding user-controlled upload paths or public URL generation.
