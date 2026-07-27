"""Tool + slash handlers for OpenCode Go quota."""

from __future__ import annotations

import json
from typing import Any, Optional

from .quota.cache import SnapshotCache, default_cache
from .quota.check import fetch_snapshot
from .quota.types import WINDOW_LABELS, WINDOW_ORDER, QuotaSnapshot


def _format_human(snapshot: QuotaSnapshot) -> str:
    if snapshot.status in {"error", "incomplete"}:
        return f"OpenCode Go quota unavailable ({snapshot.status}): {snapshot.error or snapshot.message}"
    lines = [f"OpenCode Go quota: {snapshot.status}"]
    for key in WINDOW_ORDER:
        usage = snapshot.windows.get(key)
        if usage is None:
            continue
        mark = " !" if key in snapshot.breached else ""
        lines.append(
            f"  {WINDOW_LABELS[key]}:{mark} {usage.percent_remaining:.1f}% remaining, "
            f"resets {usage.reset_at}"
        )
    if snapshot.soonest_reset_at:
        lines.append(f"  Soonest reset among breached: {snapshot.soonest_reset_at}")
    return "\n".join(lines)


def get_snapshot(
    *,
    cache: Optional[SnapshotCache] = None,
    force: bool = False,
    opener=None,
) -> QuotaSnapshot:
    c = cache if cache is not None else default_cache
    if not force:
        hit = c.get()
        if hit is not None:
            return hit
    snapshot = fetch_snapshot(opener=opener)
    c.set(snapshot)
    return snapshot


def quota_check(args: Optional[dict[str, Any]] = None, **_: Any) -> str:
    """Hermes tool handler — returns JSON quota status."""
    args = args or {}
    force = bool(args.get("force") or args.get("refresh"))
    snapshot = get_snapshot(force=force)
    return json.dumps(snapshot.to_dict(), indent=2)


def quota_slash(raw_args: str = "") -> str:
    """Slash command /quota handler."""
    text = (raw_args or "").strip().lower()
    if text in {"help", "-h", "--help"}:
        return (
            "Usage: /quota [refresh]\n"
            "Show OpenCode Go rolling (5h), weekly, and monthly remaining quota.\n"
            "Optional: OPENCODE_GO_QUOTA_AUTO_BLOCK=true to block tools near limit."
        )
    force = text in {"refresh", "--refresh", "-r"}
    snapshot = get_snapshot(force=force)
    return _format_human(snapshot)


QUOTA_CHECK_SCHEMA: dict[str, Any] = {
    "name": "quota_check",
    "description": (
        "Check OpenCode Go subscription quota windows (5h rolling, weekly, monthly). "
        "Returns remaining percent, reset times, and status ok|warn|critical. "
        "Use before long tasks or when hitting rate/quota errors."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "force": {
                "type": "boolean",
                "description": "Bypass short TTL cache and re-scrape the dashboard.",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
}
