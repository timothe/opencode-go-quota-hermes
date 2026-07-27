"""Warn (pre_llm_call) and optional auto-block (pre_tool_call) hooks."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .quota.types import QuotaSnapshot
from .tools import get_snapshot

DEFAULT_ALLOWLIST = (
    "quota_check",
    "cronjob",
    "memory",
    "session_search",
    "skill_view",
    "skills_list",
    "todo",
)


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def auto_block_enabled() -> bool:
    return _truthy("OPENCODE_GO_QUOTA_AUTO_BLOCK")


def block_allowlist() -> set[str]:
    raw = (os.environ.get("OPENCODE_GO_QUOTA_BLOCK_ALLOWLIST") or "").strip()
    if not raw:
        return set(DEFAULT_ALLOWLIST)
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_opencode_go_model(model: str) -> bool:
    m = (model or "").lower()
    if not m:
        return True  # ambiguous — still warn
    return "opencode-go" in m or m.startswith("opencode/") or "/go" in m.split(":", 1)[0]


class InjectRateLimiter:
    def __init__(self, interval_s: float = 300.0) -> None:
        self.interval_s = interval_s
        self._last: dict[str, float] = {}

    def should_inject(self, session_id: str, now: Optional[float] = None) -> bool:
        t = time.monotonic() if now is None else now
        last = self._last.get(session_id)
        if last is not None and (t - last) < self.interval_s:
            return False
        self._last[session_id] = t
        return True

    def clear(self) -> None:
        self._last.clear()


_inject_limiter = InjectRateLimiter()


def _context_block(snapshot: QuotaSnapshot) -> str:
    reset = snapshot.soonest_reset_at or "unknown"
    return (
        "[OpenCode Go quota] "
        f"status={snapshot.status}; {snapshot.message} "
        f"Soonest reset among breached windows: {reset}. "
        "Prefer postponing non-urgent work via cronjob until after reset, "
        "or switch to a fallback provider. "
        "Load skill opencode-go-quota for the postpone playbook."
    )


def on_pre_llm_call(
    session_id: str = "",
    user_message: str = "",
    conversation_history: Optional[list] = None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    **_: Any,
) -> Optional[dict[str, str]]:
    if not is_opencode_go_model(model):
        return None
    try:
        snapshot = get_snapshot()
    except Exception:  # noqa: BLE001
        return None
    if snapshot.status not in {"warn", "critical"}:
        return None
    sid = session_id or "default"
    if not _inject_limiter.should_inject(sid):
        return None
    return {"context": _context_block(snapshot)}


def on_pre_tool_call(
    tool_name: str = "",
    args: Any = None,
    task_id: str = "",
    **_: Any,
) -> Optional[dict[str, str]]:
    if not auto_block_enabled():
        return None
    if tool_name in block_allowlist():
        return None
    try:
        snapshot = get_snapshot()
    except Exception:  # noqa: BLE001
        return None
    if snapshot.status != "critical":
        return None
    reset = snapshot.soonest_reset_at or "unknown"
    return {
        "action": "block",
        "message": (
            "opencode-go-quota blocked this tool: quota critically low. "
            f"{snapshot.message} "
            f"Soonest reset: {reset}. "
            "Schedule the task with cronjob after reset, or unset "
            "OPENCODE_GO_QUOTA_AUTO_BLOCK to override."
        ),
    }
