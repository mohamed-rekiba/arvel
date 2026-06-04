# WI-arvel-003 — No Schema Change

**Work Item**: WI-arvel-003
**Stage**: 2c (Planning — DBA)
**Date**: 2026-06-05

> Adapted artifact. Schema's `planning-dba` stage canonically produces `db/schema/*`, `db/migrations/*`, `db/seeds/*`. This WI is documentation reorganization + dev-stack changes. There is no database touch.

## Affected models

None.

## Affected migrations

None added. None modified. None deleted.

## Affected seeds

None.

## Production data risk

Zero. The kit's existing `media` table schema is unchanged. The new `minio` compose service is a fresh container; bucket bootstrap (`createbuckets`) only creates buckets if absent.

## Storage layer

The `arvel.storage.s3` driver code is unchanged. WI-arvel-003 only makes the existing `s3` disk configuration in the kit *reachable* via the new compose services. No new driver, no protocol change, no backwards-incompatible configuration shape.
