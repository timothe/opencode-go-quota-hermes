"""Human-friendly OpenCode Go quota wording for the LLM and user."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .types import WINDOW_LABELS, WINDOW_ORDER, QuotaSnapshot, WindowKey, WindowUsage

# Spoken labels used in prose (not machine keys).
PROSE_LABELS: dict[WindowKey, str] = {
    "rolling": "5-hour",
    "weekly": "weekly",
    "monthly": "monthly",
}


def _parse_reset_at(iso: str) -> Optional[datetime]:
    text = (iso or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_reset_phrase(
    usage: WindowUsage,
    *,
    now: Optional[datetime] = None,
) -> str:
    """Turn reset_in_sec / reset_at into spoken English."""
    now = now or datetime.now(timezone.utc)
    secs = max(0.0, usage.reset_in_sec)
    if secs <= 90:
        return "resets any moment now"
    if secs < 3600:
        mins = max(1, int(round(secs / 60)))
        return f"resets in about {mins} minute{'s' if mins != 1 else ''}"
    if secs < 86400:
        hours = max(1, int(round(secs / 3600)))
        return f"resets in about {hours} hour{'s' if hours != 1 else ''}"
    if secs < 86400 * 2:
        return "resets tomorrow"

    reset_dt = _parse_reset_at(usage.reset_at)
    if reset_dt is not None:
        # Same calendar month → "on the 14th"; else "on 14 Mar"
        day = reset_dt.day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        if reset_dt.year == now.year and reset_dt.month == now.month:
            return f"resets on the {day}{suffix}"
        return f"resets on {day}{suffix} {reset_dt.strftime('%b')}"

    days = max(1, int(round(secs / 86400)))
    return f"resets in about {days} day{'s' if days != 1 else ''}"


def _pct(remaining: float) -> str:
    # Prefer whole numbers when close; keep one decimal otherwise.
    if abs(remaining - round(remaining)) < 0.05:
        return f"{int(round(remaining))}%"
    return f"{remaining:.1f}%"


def format_natural_summary(
    snapshot: QuotaSnapshot,
    *,
    now: Optional[datetime] = None,
) -> str:
    """Prose summary the model can relay to the user."""
    if snapshot.status in {"error", "incomplete"}:
        detail = snapshot.error or snapshot.message or "unknown error"
        return (
            "I couldn't read your OpenCode Go quota just now "
            f"({detail}). "
            "The dashboard auth cookie may have expired — refresh "
            "OPENCODE_GO_AUTH_COOKIE from opencode.ai and try again."
        )

    now = now or datetime.now(timezone.utc)
    parts: list[str] = []
    for key in WINDOW_ORDER:
        usage = snapshot.windows.get(key)
        if usage is None:
            continue
        label = PROSE_LABELS[key]
        rem = _pct(usage.percent_remaining)
        reset = format_reset_phrase(usage, now=now)
        parts.append(f"{rem} remaining on the {label} window ({reset})")

    if not parts:
        return "OpenCode Go quota data came back empty — try refreshing."

    if len(parts) == 1:
        body = parts[0]
    elif len(parts) == 2:
        body = f"{parts[0]}, and {parts[1]}"
    else:
        body = ", ".join(parts[:-1]) + f", and {parts[-1]}"

    if snapshot.status == "ok":
        lead = "Your OpenCode Go quota is looking good for now"
    elif snapshot.status == "warn":
        lead = "Your OpenCode Go quota is getting low"
    else:  # critical
        lead = "Your OpenCode Go quota is critically low"

    advice = ""
    if snapshot.status in {"warn", "critical"}:
        advice = (
            " Consider postponing non-urgent work until the tightest window "
            "resets, or switch to a fallback provider if you need to continue now."
        )

    return f"{lead}: {body}.{advice}"


def format_tool_guidance() -> str:
    return (
        "This is OpenCode Go subscription quota only (not OpenRouter, Zen billing, "
        "or hermes insights). Reply to the user in natural language using this "
        "summary — do not dump ISO timestamps or raw JSON."
    )
