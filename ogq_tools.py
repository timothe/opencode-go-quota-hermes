"""Tool + slash handlers for OpenCode Go quota and Zen balance."""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    from .quota.cache import SnapshotCache, default_cache
    from .quota.check import fetch_snapshot
    from .quota.format import (
        format_balance_summary,
        format_natural_summary,
        format_tool_guidance,
    )
    from .quota.types import QuotaSnapshot
except ImportError:  # pragma: no cover
    from quota.cache import SnapshotCache, default_cache
    from quota.check import fetch_snapshot
    from quota.format import (
        format_balance_summary,
        format_natural_summary,
        format_tool_guidance,
    )
    from quota.types import QuotaSnapshot


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


def opencode_go_quota_check(args: Optional[dict[str, Any]] = None, **_: Any) -> str:
    """Hermes tool — natural-language OpenCode Go quota for the LLM to relay."""
    args = args or {}
    force = bool(args.get("force") or args.get("refresh"))
    as_json = bool(args.get("json") or args.get("raw"))
    balance_only = bool(args.get("balance") or args.get("billing"))
    snapshot = get_snapshot(force=force)
    if as_json:
        return json.dumps(snapshot.to_dict(), indent=2)
    if balance_only:
        if snapshot.billing is None:
            return (
                "No billing data on this fetch. "
                "Try force=true, or refresh the console session (OPENCODE_GO_AUTH_COOKIE)."
            )
        return f"{format_balance_summary(snapshot.billing)}\n\n({format_tool_guidance()})"
    return f"{format_natural_summary(snapshot)}\n\n({format_tool_guidance()})"


quota_check = opencode_go_quota_check


def go_quota_slash(raw_args: str = "") -> str:
    """Slash command /go-quota handler."""
    text = (raw_args or "").strip().lower()
    if text in {"help", "-h", "--help"}:
        return (
            "Usage: /go-quota [refresh|balance|json]\n"
            "Show OpenCode Go remaining quota (5-hour / weekly / monthly) with "
            "pace advice, plus Zen balance when available.\n"
            "In chat: \"What's my current quota?\" or "
            "\"What's my remaining balance on OpenCode Go?\"\n"
            "Also: /go-balance\n"
            "Optional: OPENCODE_GO_QUOTA_AUTO_BLOCK=true to block tools near limit."
        )
    force = text in {"refresh", "--refresh", "-r", "json", "balance", "billing"}
    as_json = text == "json"
    balance_only = text in {"balance", "billing"}
    snapshot = get_snapshot(force=force or as_json or balance_only)
    if as_json:
        return json.dumps(snapshot.to_dict(), indent=2)
    if balance_only:
        if snapshot.billing is None:
            return "No billing data on this fetch. Try /go-balance after refreshing the console auth cookie."
        return format_balance_summary(snapshot.billing)
    return format_natural_summary(snapshot)


def go_balance_slash(raw_args: str = "") -> str:
    """Slash command /go-balance — Zen balance + useBalance toggle."""
    text = (raw_args or "").strip().lower()
    if text in {"help", "-h", "--help"}:
        return (
            "Usage: /go-balance [refresh]\n"
            "Show OpenCode Zen balance and whether "
            "Use-balance-after-Go-limits is enabled."
        )
    force = text in {"refresh", "--refresh", "-r"}
    snapshot = get_snapshot(force=force)
    if snapshot.billing is None:
        return (
            "No billing data on this fetch. "
            "Refresh the console session (OPENCODE_GO_AUTH_COOKIE) and try again."
        )
    return format_balance_summary(snapshot.billing)


quota_slash = go_quota_slash

TOOL_NAME = "opencode_go_quota_check"

QUOTA_CHECK_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Check the user's OpenCode Go subscription quota "
        "(5-hour rolling, weekly, and monthly windows on opencode.ai) and "
        "Zen balance / Use-balance-after-Go-limits. "
        "PREFERRED when the user asks about quota, remaining allowance, "
        "pace/burn, balance, or Zen credits while using OpenCode Go — e.g. "
        "\"What's my current quota?\", \"What's my remaining balance on OpenCode Go?\". "
        "Do NOT use provider-usage-tracking or send them to the web dashboard "
        "for Go — this tool reads the Go usage API with the Go API key. "
        "Returns natural-language prose to relay to the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "force": {
                "type": "boolean",
                "description": "Bypass short TTL cache and re-fetch usage.",
            },
            "json": {
                "type": "boolean",
                "description": "If true, return machine JSON instead of prose (rarely needed).",
            },
            "balance": {
                "type": "boolean",
                "description": "If true, return only Zen balance / useBalance prose.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}
