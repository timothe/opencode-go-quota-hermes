"""Human-friendly OpenCode Go quota wording for the LLM and user."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .history import format_trend_advice
from .pace import assess_all_paces, format_pace_advice, primary_pace_tone
from .types import (
    WINDOW_ORDER,
    BillingInfo,
    QuotaSnapshot,
    WindowKey,
    WindowUsage,
)

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


def format_usd(amount: float) -> str:
    return f"${amount:,.2f}"


def format_balance_summary(billing: BillingInfo) -> str:
    """Prose for Zen balance + Go use-balance-after-limits toggle."""
    if billing.error:
        if "cookie" in billing.error.lower() or "session rejected" in billing.error:
            advice = (
                "The console session cookie is stale. Copy a fresh `auth` cookie "
                "from opencode.ai into OPENCODE_GO_AUTH_COOKIE."
            )
        else:
            advice = "Try again shortly; if it keeps failing, check the console session cookie."
        return (
            "I couldn't read your OpenCode Zen balance just now "
            f"({billing.error}). {advice}"
        )

    parts = [f"Your OpenCode Zen balance is {format_usd(billing.balance_usd)}"]
    if billing.available_usd and abs(billing.available_usd - billing.balance_usd) > 0.005:
        parts.append(f"{format_usd(billing.available_usd)} of it available to spend")
    body = parts[0] if len(parts) == 1 else f"{parts[0]} ({parts[1]})"
    if billing.mode:
        body += f", on {billing.mode} billing"
    if billing.monthly_limit_usd > 0:
        body += (
            f"; your Go monthly window is {format_usd(billing.monthly_usage_usd)} "
            f"used of {format_usd(billing.monthly_limit_usd)}"
        )

    if billing.use_balance is True:
        toggle = (
            "Use-balance-after-Go-limits is on: when Go quota windows are "
            "exhausted, usage falls back to this Zen balance"
        )
    elif billing.use_balance is False:
        toggle = (
            "Use-balance-after-Go-limits is off: hitting Go quota windows "
            "will block requests instead of drawing from Zen balance"
        )
    else:
        toggle = (
            "Could not tell whether Use-balance-after-Go-limits is enabled "
            "from the console"
        )

    text = f"{body}. {toggle}."
    if billing.auto_reload:
        text += (
            f" Auto-recharge is on: tops up {format_usd(billing.reload_amount_usd)} "
            f"when the balance drops below {format_usd(billing.reload_trigger_usd)}."
        )
    return text


def format_natural_summary(
    snapshot: QuotaSnapshot,
    *,
    now: Optional[datetime] = None,
    history_path: Optional[Path] = None,
    include_balance: bool = True,
) -> str:
    """Prose summary the model can relay to the user."""
    if snapshot.status in {"error", "incomplete"}:
        detail = snapshot.error or snapshot.message or "unknown error"
        if "usage API" in detail or "API_KEY" in detail:
            advice = (
                "The Go usage API rejected the request — check that "
                "OPENCODE_GO_API_KEY is valid and unused/revoked."
            )
        else:
            advice = (
                "The dashboard auth cookie may have expired — refresh "
                "OPENCODE_GO_AUTH_COOKIE from opencode.ai and try again."
            )
        return (
            "I couldn't read your OpenCode Go quota just now "
            f"({detail}). {advice}"
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

    paces = assess_all_paces(snapshot.windows)
    tone = primary_pace_tone(paces)

    if snapshot.status == "critical":
        lead = "Your OpenCode Go quota is critically low"
    elif snapshot.status == "warn":
        lead = "Your OpenCode Go quota is getting low"
    elif tone == "ahead":
        lead = "Your OpenCode Go quota still has room, but burn is ahead of pace"
    elif tone == "under":
        lead = "Your OpenCode Go quota is comfortable and under pace so far"
    else:
        lead = "Your OpenCode Go quota is on a reasonable pace for now"

    advice_bits: list[str] = []
    pace_text = format_pace_advice(paces)
    if pace_text:
        advice_bits.append(pace_text.rstrip("."))

    trend = format_trend_advice(snapshot, path=history_path, now=now)
    if trend:
        advice_bits.append(trend.rstrip("."))

    if snapshot.status in {"warn", "critical"}:
        advice_bits.append(
            "Consider postponing non-urgent work until the tightest window "
            "resets, or switch to a fallback provider if you need to continue now"
        )

    text = f"{lead}: {body}."
    if advice_bits:
        text += " " + ". ".join(advice_bits) + "."

    if include_balance and snapshot.billing and not snapshot.billing.error:
        text += " " + format_balance_summary(snapshot.billing)

    return text


def format_tool_guidance() -> str:
    return (
        "This is OpenCode Go subscription quota (and Zen balance as Go overage "
        "fallback) — not OpenRouter or hermes insights. Reply to the user in "
        "natural language using this summary — do not dump ISO timestamps or "
        "raw JSON."
    )
