"""Pagination bounds shared by every list endpoint."""

from __future__ import annotations

from arvel.support.env import env as _env

# Hard ceiling for any client-supplied page size — stops ?limit=10000000 from
# forcing a full-table scan.
max_limit: int = _env("PAGINATION_MAX_LIMIT", 100)
