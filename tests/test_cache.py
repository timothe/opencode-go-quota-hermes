from __future__ import annotations

from quota.cache import SnapshotCache
from quota.types import QuotaSnapshot


def _snap(status: str) -> QuotaSnapshot:
    return QuotaSnapshot(
        status=status,  # type: ignore[arg-type]
        windows={},
        breached=[],
        soonest_reset_at=None,
        message="m",
    )


def test_cache_hit_within_ttl():
    c = SnapshotCache(ttl_s=10)
    c.set(_snap("ok"), now=100.0)
    assert c.get(now=105.0) is not None
    assert c.get(now=105.0).status == "ok"


def test_cache_miss_after_ttl():
    c = SnapshotCache(ttl_s=10)
    c.set(_snap("warn"), now=100.0)
    assert c.get(now=111.0) is None


def test_errors_not_cached():
    c = SnapshotCache(ttl_s=10)
    c.set(_snap("error"), now=100.0)
    assert c.get(now=101.0) is None
    c.set(_snap("incomplete"), now=100.0)
    assert c.get(now=101.0) is None


def test_clear():
    c = SnapshotCache(ttl_s=10)
    c.set(_snap("ok"), now=1.0)
    c.clear()
    assert c.get(now=2.0) is None
