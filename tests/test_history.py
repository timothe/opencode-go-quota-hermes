from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quota.history import (
    HistorySample,
    append_sample,
    format_trend_advice,
    load_samples,
    record_snapshot,
    snapshot_to_sample,
)
from quota.types import QuotaSnapshot, WindowUsage


def _snap(weekly_u: float = 18.0) -> QuotaSnapshot:
    return QuotaSnapshot(
        status="ok",
        windows={
            "weekly": WindowUsage(
                usage_percent=weekly_u,
                reset_in_sec=6 * 86400,
                percent_remaining=100.0 - weekly_u,
                reset_at="x",
            )
        },
        breached=[],
        soonest_reset_at=None,
    )


def test_append_and_dedup(tmp_path):
    path = tmp_path / "hist.jsonl"
    now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    s1 = snapshot_to_sample(_snap(18.0), now=now)
    assert append_sample(s1, path=path) is True
    s2 = snapshot_to_sample(_snap(18.2), now=now + timedelta(minutes=10))
    assert append_sample(s2, path=path) is False  # dedup
    s3 = snapshot_to_sample(_snap(25.0), now=now + timedelta(hours=2))
    assert append_sample(s3, path=path) is True
    samples = load_samples(path)
    assert len(samples) == 2


def test_record_snapshot_skips_errors(tmp_path):
    path = tmp_path / "hist.jsonl"
    bad = QuotaSnapshot(
        status="error",
        windows={},
        breached=[],
        soonest_reset_at=None,
        error="nope",
    )
    assert record_snapshot(bad, path=path) is False


def test_trend_faster_burn(tmp_path):
    path = tmp_path / "hist.jsonl"
    base = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    # Slow burn days 0-2, then accelerate.
    usages = [5.0, 7.0, 9.0, 20.0]
    for i, u in enumerate(usages[:-1]):
        sample = HistorySample(
            ts=base + timedelta(days=i),
            windows={
                "weekly": {
                    "u": u,
                    "left": 100.0 - u,
                    "reset": (7 - i) * 86400.0,
                }
            },
        )
        append_sample(sample, path=path)
    snap = QuotaSnapshot(
        status="ok",
        windows={
            "weekly": WindowUsage(
                usage_percent=usages[-1],
                reset_in_sec=(7 - 3) * 86400.0,
                percent_remaining=100.0 - usages[-1],
                reset_at="x",
            )
        },
        breached=[],
        soonest_reset_at=None,
    )
    advice = format_trend_advice(
        snap, path=path, now=base + timedelta(days=3)
    )
    assert "faster" in advice.lower()
