from __future__ import annotations

from quota.pace import (
    WINDOW_PERIOD_SEC,
    assess_window_pace,
    format_pace_advice,
    primary_pace_tone,
)
from quota.types import WindowUsage


def _win(usage: float, reset_in: float) -> WindowUsage:
    return WindowUsage(
        usage_percent=usage,
        reset_in_sec=reset_in,
        percent_remaining=100.0 - usage,
        reset_at="x",
    )


def test_weekly_ahead_after_one_day():
    # 18% used, ~1 day into 7-day week → ahead of ~14% linear.
    reset = WINDOW_PERIOD_SEC["weekly"] - 86400
    a = assess_window_pace("weekly", _win(18.0, reset))
    assert a.label == "ahead"
    assert 13.0 <= a.expected_pct <= 15.0
    text = format_pace_advice([a])
    assert "ahead of pace" in text
    assert "18%" in text


def test_under_pace():
    reset = WINDOW_PERIOD_SEC["weekly"] - 3 * 86400
    a = assess_window_pace("weekly", _win(5.0, reset))
    assert a.label == "under"


def test_skip_early_window():
    reset = WINDOW_PERIOD_SEC["weekly"] - 100  # tiny elapsed
    a = assess_window_pace("weekly", _win(1.0, reset))
    assert a.label == "skip"


def test_primary_tone_ahead():
    reset = WINDOW_PERIOD_SEC["weekly"] - 86400
    a = assess_window_pace("weekly", _win(18.0, reset))
    assert primary_pace_tone([a]) == "ahead"
