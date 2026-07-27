"""Warn, optional auto-block, and first-session ready announcement."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

from .quota.format import format_natural_summary
from .quota.types import QuotaSnapshot
from .tools import TOOL_NAME, get_snapshot

DEFAULT_ALLOWLIST = (
    TOOL_NAME,
    "opencode_go_quota_check",
    "quota_check",  # legacy alias if present
    "cronjob",
    "memory",
    "session_search",
    "skill_view",
    "skills_list",
    "todo",
)

_READY_MARKER = Path.home() / ".hermes" / "cache" / "opencode-go-quota-announced"
_announced_this_process = False


def _truthy(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def auto_block_enabled() -> bool:
    return _truthy("OPENCODE_GO_QUOTA_AUTO_BLOCK", default=False)


def announce_enabled() -> bool:
    return _truthy("OPENCODE_GO_QUOTA_ANNOUNCE", default=True)


def block_allowlist() -> set[str]:
    raw = (os.environ.get("OPENCODE_GO_QUOTA_BLOCK_ALLOWLIST") or "").strip()
    if not raw:
        return set(DEFAULT_ALLOWLIST)
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_opencode_go_model(model: str) -> bool:
    m = (model or "").lower()
    if not m:
        return True  # ambiguous — still warn when Go is likely in use
    return (
        "opencode-go" in m
        or m.startswith("opencode-go")
        or m.startswith("opencode/")
    )


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
    return (
        "[OpenCode Go quota — plugin opencode-go-quota] "
        f"{format_natural_summary(snapshot)} "
        "Prefer postponing non-urgent work via cronjob until after the tightest "
        "window resets, or switch to a fallback provider. "
        "Load skill opencode-go-quota for the postpone playbook. "
        "This is OpenCode Go only — not OpenRouter or Zen billing."
    )


def _ready_context() -> str:
    return (
        "[OpenCode Go quota plugin is active] "
        "The opencode-go-quota plugin is loaded: it watches OpenCode Go "
        "5-hour / weekly / monthly limits, can warn when low, and optionally "
        "auto-block tools when critically low. "
        "Briefly tell the user that OpenCode Go quota monitoring is in place, "
        "and that they can ask naturally anytime — e.g. \"What's my current quota?\". "
        "Do not dump env var names unless they ask how it works."
    )


def _should_announce_ready(is_first_turn: bool) -> bool:
    global _announced_this_process
    if not announce_enabled() or not is_first_turn or _announced_this_process:
        return False
    # Once per gateway/CLI process after restart (marker is process-lifetime only).
    _announced_this_process = True
    try:
        _READY_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _READY_MARKER.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    return True


def reset_announce_state_for_tests() -> None:
    global _announced_this_process
    _announced_this_process = False


def on_pre_llm_call(
    session_id: str = "",
    user_message: str = "",
    conversation_history: Optional[list] = None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    **_: Any,
) -> Optional[dict[str, str]]:
    chunks: list[str] = []

    if _should_announce_ready(is_first_turn):
        chunks.append(_ready_context())

    if is_opencode_go_model(model):
        try:
            snapshot = get_snapshot()
        except Exception:  # noqa: BLE001
            snapshot = None
        if snapshot is not None and snapshot.status in {"warn", "critical"}:
            sid = session_id or "default"
            if _inject_limiter.should_inject(sid):
                chunks.append(_context_block(snapshot))

    if not chunks:
        return None
    return {"context": "\n\n".join(chunks)}


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
    return {
        "action": "block",
        "message": (
            "opencode-go-quota blocked this tool: OpenCode Go quota is critically low. "
            f"{format_natural_summary(snapshot)} "
            "Schedule the task with cronjob after reset, or unset "
            "OPENCODE_GO_QUOTA_AUTO_BLOCK to override."
        ),
    }
