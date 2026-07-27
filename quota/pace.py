"""Linear pace vs elapsed window time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .types import WINDOW_ORDER, WindowKey, WindowUsage

PaceLabel = Literal["ahead", "under", "on_track", "skip"]

WINDOW_PERIOD_SEC: dict[WindowKey, float] = {
    "rolling": 5 * 3600,
    "weekly": 7 * 86400,
    "monthly": 30 * 86400,
}

PROSE_LABELS: dict[WindowKey, str] = {
    "rolling": "5-hour",
    "weekly": "weekly",
    "monthly": "monthly",
}


@dataclass(frozen=True)
class PaceAssessment:
    window: WindowKey
    label: PaceLabel
    actual_pct: float
    expected_pct: float
    elapsed_sec: float
    ratio: float


def _format_elapsed(secs: float) -> str:
    if secs < 3600:
        mins = max(1, int(round(secs / 60)))
        return f"{mins} minute{'s' if mins != 1 else ''}"
    if secs < 86400:
        hours = max(1, int(round(secs / 3600)))
        return f"about {hours} hour{'s' if hours != 1 else ''}"
    days = secs / 86400
    if abs(days - round(days)) < 0.15:
        d = int(round(days))
        return f"{d} day{'s' if d != 1 else ''}"
    return f"about {days:.1f} days"


def assess_window_pace(key: WindowKey, usage: WindowUsage) -> PaceAssessment:
    period = WINDOW_PERIOD_SEC[key]
    reset = max(0.0, usage.reset_in_sec)
    elapsed = max(0.0, period - reset)
    # Ignore very early window samples (noise).
    if elapsed < 0.05 * period:
        return PaceAssessment(
            window=key,
            label="skip",
            actual_pct=usage.usage_percent,
            expected_pct=0.0,
            elapsed_sec=elapsed,
            ratio=1.0,
        )
    expected = 100.0 * elapsed / period
    actual = max(0.0, usage.usage_percent)
    ratio = actual / max(expected, 1.0)
    if ratio >= 1.25:
        label: PaceLabel = "ahead"
    elif ratio <= 0.75:
        label = "under"
    else:
        label = "on_track"
    return PaceAssessment(
        window=key,
        label=label,
        actual_pct=actual,
        expected_pct=expected,
        elapsed_sec=elapsed,
        ratio=ratio,
    )


def assess_all_paces(
    windows: dict[WindowKey, WindowUsage],
) -> list[PaceAssessment]:
    out: list[PaceAssessment] = []
    for key in WINDOW_ORDER:
        usage = windows.get(key)
        if usage is None:
            continue
        out.append(assess_window_pace(key, usage))
    return out


def format_pace_advice(assessments: list[PaceAssessment]) -> str:
    """Spoken advice from linear pace (empty if nothing notable)."""
    bits: list[str] = []
    for a in assessments:
        if a.label == "skip":
            continue
        name = PROSE_LABELS[a.window]
        elapsed = _format_elapsed(a.elapsed_sec)
        if a.label == "ahead":
            bits.append(
                f"The {name} window is a bit ahead of pace "
                f"({a.actual_pct:.0f}% used after {elapsed}; "
                f"linear would be ~{a.expected_pct:.0f}%) — "
                f"ease off for the rest of the {_rest_phrase(a.window)}"
            )
        elif a.label == "under":
            bits.append(
                f"The {name} window is under pace "
                f"({a.actual_pct:.0f}% used after {elapsed}; "
                f"linear would be ~{a.expected_pct:.0f}%)"
            )
    if not bits:
        return ""
    return ". ".join(bits) + "."


def _rest_phrase(key: WindowKey) -> str:
    if key == "rolling":
        return "5-hour window"
    if key == "weekly":
        return "week"
    return "month"


def primary_pace_tone(assessments: list[PaceAssessment]) -> Optional[PaceLabel]:
    """Worst notable pace among assessed windows (ahead > under > on_track)."""
    labels = {a.label for a in assessments if a.label != "skip"}
    if "ahead" in labels:
        return "ahead"
    if "under" in labels:
        return "under"
    if "on_track" in labels:
        return "on_track"
    return None

