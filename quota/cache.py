"""Short-TTL in-memory cache for quota snapshots."""

from __future__ import annotations

import time
from typing import Optional

from .types import QuotaSnapshot

DEFAULT_TTL_S = 60.0


class SnapshotCache:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self.ttl_s = ttl_s
        self._snapshot: Optional[QuotaSnapshot] = None
        self._stored_at: float = 0.0

    def get(self, now: Optional[float] = None) -> Optional[QuotaSnapshot]:
        if self._snapshot is None:
            return None
        t = time.monotonic() if now is None else now
        if t - self._stored_at >= self.ttl_s:
            return None
        return self._snapshot

    def set(self, snapshot: QuotaSnapshot, now: Optional[float] = None) -> None:
        # Only cache successful classifications (ok/warn/critical), not errors.
        if snapshot.status in {"error", "incomplete"}:
            return
        self._snapshot = snapshot
        self._stored_at = time.monotonic() if now is None else now

    def clear(self) -> None:
        self._snapshot = None
        self._stored_at = 0.0


# Process-wide default used by hooks/tools.
default_cache = SnapshotCache()
