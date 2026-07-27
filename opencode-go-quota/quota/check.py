"""Classify quota windows against warn/critical thresholds."""

from __future__ import annotations

import os
from typing import Optional

from .config import resolve_config
from .scrape import normalize_windows, query_opencode_go_quota
from .types import (
    WINDOW_LABELS,
    WINDOW_ORDER,
    QuotaSnapshot,
    StatusLevel,
    WindowKey,
    WindowUsage,
)


def _float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def warn_threshold() -> float:
    return _float_env("OPENCODE_GO_QUOTA_WARN", 20.0)


def critical_threshold() -> float:
    return _float_env("OPENCODE_GO_QUOTA_CRITICAL", 5.0)


def classify_windows(
    windows: dict[WindowKey, WindowUsage],
    *,
    warn: Optional[float] = None,
    critical: Optional[float] = None,
) -> QuotaSnapshot:
    if not windows:
        return QuotaSnapshot(
            status="incomplete",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error="No usage windows available",
        )

    w = warn if warn is not None else warn_threshold()
    c = critical if critical is not None else critical_threshold()

    breached: list[WindowKey] = []
    level: StatusLevel = "ok"
    for key in WINDOW_ORDER:
        usage = windows.get(key)
        if usage is None:
            continue
        remaining = usage.percent_remaining
        if remaining <= c:
            level = "critical"
            breached.append(key)
        elif remaining <= w:
            if level != "critical":
                level = "warn"
            breached.append(key)

    soonest: Optional[str] = None
    soonest_sec: Optional[float] = None
    for key in breached:
        usage = windows[key]
        if soonest_sec is None or usage.reset_in_sec < soonest_sec:
            soonest_sec = usage.reset_in_sec
            soonest = usage.reset_at

    parts = []
    for key in WINDOW_ORDER:
        usage = windows.get(key)
        if usage is None:
            continue
        parts.append(
            f"{WINDOW_LABELS[key]} {usage.percent_remaining:.1f}% left "
            f"(resets {usage.reset_at})"
        )
    message = "; ".join(parts)
    if breached:
        labels = ", ".join(WINDOW_LABELS[k] for k in breached)
        message = f"{level.upper()} on {labels}. {message}"

    return QuotaSnapshot(
        status=level,
        windows=windows,
        breached=breached,
        soonest_reset_at=soonest,
        message=message,
    )


def fetch_snapshot(
    *,
    opener=None,
    warn: Optional[float] = None,
    critical: Optional[float] = None,
    now_ms: Optional[float] = None,
) -> QuotaSnapshot:
    resolved = resolve_config()
    if resolved.state == "none":
        return QuotaSnapshot(
            status="incomplete",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error="Missing OPENCODE_GO_WORKSPACE_ID and OPENCODE_GO_AUTH_COOKIE",
        )
    if resolved.state == "incomplete":
        return QuotaSnapshot(
            status="incomplete",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error=f"Incomplete config ({resolved.source}): missing {resolved.missing}",
        )
    if resolved.state == "invalid":
        return QuotaSnapshot(
            status="error",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error=f"Invalid config ({resolved.source}): {resolved.error}",
        )

    result = query_opencode_go_quota(
        resolved.config.workspace_id,
        resolved.config.auth_cookie,
        opener=opener,
    )
    if not result.success:
        return QuotaSnapshot(
            status="error",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error=getattr(result, "error", "scrape failed"),
        )

    windows = normalize_windows(result.windows, now_ms=now_ms)
    return classify_windows(windows, warn=warn, critical=critical)
