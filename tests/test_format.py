from __future__ import annotations

from datetime import datetime, timezone

from quota.format import format_balance_summary, format_natural_summary, format_reset_phrase
from quota.pace import WINDOW_PERIOD_SEC
from quota.types import BillingInfo, QuotaSnapshot, WindowUsage


def _usage(remaining: float, reset_in: float, reset_at: str) -> WindowUsage:
    return WindowUsage(
        usage_percent=100.0 - remaining,
        reset_in_sec=reset_in,
        percent_remaining=remaining,
        reset_at=reset_at,
    )


def test_format_reset_hours():
    u = _usage(100, 5 * 3600, "2026-07-27T16:00:00Z")
    assert "hour" in format_reset_phrase(u)


def test_format_reset_on_the_nth():
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    u = _usage(50, 86400, "2026-07-28T12:00:00Z")
    phrase = format_reset_phrase(u, now=now)
    assert "28" in phrase or "day" in phrase or "tomorrow" in phrase


def test_natural_ok_summary_on_pace():
    # Fresh windows (almost full remaining, full reset) → skip pace noise.
    snap = QuotaSnapshot(
        status="ok",
        windows={
            "rolling": _usage(100, 18000, "2026-07-27T16:00:00Z"),
            "weekly": _usage(100, WINDOW_PERIOD_SEC["weekly"], "2026-08-02T00:00:00Z"),
            "monthly": _usage(100, WINDOW_PERIOD_SEC["monthly"], "2026-08-14T00:00:00Z"),
        },
        breached=[],
        soonest_reset_at=None,
    )
    text = format_natural_summary(
        snap, now=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    )
    assert "OpenCode Go quota" in text
    assert "reasonable pace" in text or "comfortable" in text or "room" in text
    assert "100%" in text
    assert "5-hour" in text
    assert "T00:00:00Z" not in text


def test_natural_ahead_of_pace_weekly():
    reset = WINDOW_PERIOD_SEC["weekly"] - 86400
    snap = QuotaSnapshot(
        status="ok",
        windows={"weekly": _usage(82.0, reset, "2026-08-02T00:00:00Z")},  # 18% used
        breached=[],
        soonest_reset_at=None,
    )
    text = format_natural_summary(
        snap, now=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    )
    assert "ahead of pace" in text
    assert "18%" in text or "82%" in text


def test_natural_critical_has_advice():
    snap = QuotaSnapshot(
        status="critical",
        windows={"rolling": _usage(2, 600, "2026-07-27T12:10:00Z")},
        breached=["rolling"],
        soonest_reset_at="2026-07-27T12:10:00Z",
    )
    text = format_natural_summary(snap)
    assert "critically low" in text
    assert "postponing" in text.lower() or "fallback" in text.lower()


def test_natural_error():
    snap = QuotaSnapshot(
        status="error",
        windows={},
        breached=[],
        soonest_reset_at=None,
        error="dashboard error 401",
    )
    text = format_natural_summary(snap)
    assert "couldn't read" in text.lower()
    assert "AUTH_COOKIE" in text or "cookie" in text.lower()


def test_balance_summary_use_on():
    text = format_balance_summary(
        BillingInfo(balance_usd=20.0, use_balance=True, monthly_limit_usd=50.0)
    )
    assert "$20.00" in text
    assert "Use-balance-after-Go-limits is on" in text


def test_balance_summary_use_off():
    text = format_balance_summary(BillingInfo(balance_usd=5.5, use_balance=False))
    assert "$5.50" in text
    assert "is off" in text
