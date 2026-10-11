"""Classify quota windows against warn/critical thresholds."""

from __future__ import annotations

import os
from typing import Optional

from .billing import query_opencode_billing
from .config import resolve_config
from .history import record_snapshot
from .scrape import (
    normalize_windows,
    parse_usage_api_payload,  # noqa: F401 — re-exported for tests
    query_opencode_go_quota,
    query_opencode_go_usage_api,
)
from .types import (
    WINDOW_LABELS,
    WINDOW_ORDER,
    BillingInfo,
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
    billing: Optional[BillingInfo] = None,
) -> QuotaSnapshot:
    if not windows:
        return QuotaSnapshot(
            status="incomplete",
            windows={},
            breached=[],
            soonest_reset_at=None,
            error="No usage windows available",
            billing=billing,
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
        billing=billing,
    )


def usage_api_key() -> str:
    """Go inference API key — the primary quota source (no cookie needed)."""
    return (os.environ.get("OPENCODE_GO_API_KEY") or "").strip()


def fetch_snapshot(
    *,
    opener=None,
    warn: Optional[float] = None,
    critical: Optional[float] = None,
    now_ms: Optional[float] = None,
    record_history: bool = True,
    api_key: Optional[str] = None,
) -> QuotaSnapshot:
    key = api_key if api_key is not None else usage_api_key()

    # 1. Official usage API (Go API key). Works even with a dead browser cookie.
    result = None
    api_error = ""
    if key:
        result = query_opencode_go_usage_api(key, opener=opener)
        if not result.success:
            api_error = getattr(result, "error", "usage API call failed")

    resolved = resolve_config()

    # Zen balance / Go overage toggle: console JSON APIs, cookie-based. Quota no
    # longer depends on this, so a dead cookie never blocks the quota answer.
    billing: Optional[BillingInfo] = None
    cookie = (os.environ.get("OPENCODE_GO_AUTH_COOKIE") or "").strip()
    console_token = (os.environ.get("OPENCODE_GO_CONSOLE_TOKEN") or "").strip()
    if cookie or console_token:
        billing = query_opencode_billing(
            cookie,
            console_token=console_token,
            org_id=(os.environ.get("OPENCODE_GO_ORG_ID") or "").strip(),
            opener=opener,
        )

    # 2. Legacy fallback: scrape the workspace dashboard with the auth cookie.
    if result is None or not result.success:
        if resolved.state == "configured":
            legacy = query_opencode_go_quota(
                resolved.config.workspace_id,
                resolved.config.auth_cookie,
                opener=opener,
            )
            if legacy.success:
                result = legacy
            else:
                detail = getattr(legacy, "error", "dashboard scrape failed")
                return QuotaSnapshot(
                    status="error",
                    windows={},
                    breached=[],
                    soonest_reset_at=None,
                    error=(
                        f"{api_error}; legacy dashboard scrape also failed: {detail}"
                        if api_error
                        else detail
                    ),
                    billing=billing,
                )
        elif resolved.state == "incomplete":
            return QuotaSnapshot(
                status="incomplete",
                windows={},
                breached=[],
                soonest_reset_at=None,
                error=(
                    f"Incomplete config ({resolved.source}): missing "
                    f"{resolved.missing}"
                ),
                billing=billing,
            )
        elif resolved.state == "invalid":
            return QuotaSnapshot(
                status="error",
                windows={},
                breached=[],
                soonest_reset_at=None,
                error=f"Invalid config ({resolved.source}): {resolved.error}",
                billing=billing,
            )
        elif result is not None:
            return QuotaSnapshot(
                status="error",
                windows={},
                breached=[],
                soonest_reset_at=None,
                error=api_error or "usage API call failed",
                billing=billing,
            )
        else:
            return QuotaSnapshot(
                status="incomplete",
                windows={},
                breached=[],
                soonest_reset_at=None,
                error=(
                    "Missing OPENCODE_GO_API_KEY (and no "
                    "OPENCODE_GO_WORKSPACE_ID / OPENCODE_GO_AUTH_COOKIE fallback)"
                ),
                billing=billing,
            )

    windows = normalize_windows(result.windows, now_ms=now_ms)
    snapshot = classify_windows(
        windows, warn=warn, critical=critical, billing=billing
    )
    if record_history:
        record_snapshot(snapshot)
    return snapshot
