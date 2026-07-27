"""Warn, optional auto-block, ready announce, and quota-question routing."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

try:
    from .ogq_tools import TOOL_NAME, get_snapshot
    from .quota.format import format_natural_summary
    from .quota.types import QuotaSnapshot
except ImportError:  # pragma: no cover
    from ogq_tools import TOOL_NAME, get_snapshot
    from quota.format import format_natural_summary
    from quota.types import QuotaSnapshot

DEFAULT_ALLOWLIST = (
    TOOL_NAME,
    "opencode_go_quota_check",
    "quota_check",
    "cronjob",
    "memory",
    "session_search",
    "skill_view",
    "skills_list",
    "todo",
)

# Natural-language asks that should hit OpenCode Go quota — not other skills.
_QUOTA_ASK_RE = re.compile(
    r"(?i)\b("
    r"quota|allowance|rate[\s-]?limit|"
    r"(how\s+much|remaining|left).{0,40}(go|quota|allowance|usage)|"
    r"(go|opencode).{0,40}(quota|limit|remaining|left|usage)|"
    r"usage\s+limit"
    r")\b"
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
        return True
    return "opencode-go" in m or m.startswith("opencode-go") or m.startswith("opencode/")


def looks_like_quota_question(user_message: str) -> bool:
    return bool(_QUOTA_ASK_RE.search(user_message or ""))


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
        "This is OpenCode Go only — not OpenRouter or Zen billing."
    )


def _ready_context() -> str:
    return (
        "[OpenCode Go quota plugin is active] "
        "Briefly tell the user (one short sentence) that OpenCode Go quota "
        "monitoring is active — they can ask \"What's my current quota?\" "
        "or use /go-quota. Do not dump env var names."
    )


def _quota_answer_context(snapshot: QuotaSnapshot) -> str:
    return (
        "[OpenCode Go quota — live result already fetched] "
        f"{format_natural_summary(snapshot)} "
        "Relay this answer to the user in natural language. "
        "Do NOT say you lack a quota tool. Do NOT load provider-usage-tracking. "
        "Do NOT send them to the web dashboard for this."
    )


def _should_announce_ready() -> bool:
    """Once per gateway/CLI process — not tied to is_first_turn.

    Gateway sessions often continue across restarts with existing history, so
    is_first_turn is frequently false after `hermes gateway restart`.
    """
    global _announced_this_process
    if not announce_enabled() or _announced_this_process:
        return False
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

    if _should_announce_ready():
        chunks.append(_ready_context())

    # Natural-language quota asks: fetch here so the answer works even when
    # Tool Search has deferred opencode_go_quota_check behind tool_search.
    if looks_like_quota_question(user_message):
        try:
            snapshot = get_snapshot()
            chunks.append(_quota_answer_context(snapshot))
        except Exception:  # noqa: BLE001
            chunks.append(
                "[OpenCode Go quota] Could not fetch quota just now. "
                "Ask the user to try /go-quota, or refresh OPENCODE_GO_AUTH_COOKIE."
            )

    if is_opencode_go_model(model) and not looks_like_quota_question(user_message):
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
