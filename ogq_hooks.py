"""Warn, optional auto-block, ready announce, and quota/balance routing."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

try:
    from .ogq_tools import TOOL_NAME, get_snapshot
    from .quota.format import format_balance_summary, format_natural_summary
    from .quota.types import QuotaSnapshot
except ImportError:  # pragma: no cover
    from ogq_tools import TOOL_NAME, get_snapshot
    from quota.format import format_balance_summary, format_natural_summary
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

# Balance / Zen PAYG / use-balance-after-limits (prefer over quota regex).
# NOTE: bare "balance" is intentionally NOT a trigger — it's a common English
# verb ("you balance effectiveness with fun mood"). Require financial phrasing.
_BALANCE_ASK_RE = re.compile(
    r"(?i)\b("
    r"(?:my|the|account|zen|opencode|go|available)\s+balance|"
    r"balance\s+(?:on|of|left|remaining|shows?|is|in|at|usd)|"
    r"(?:remaining|left|check|see|show|how\s+much)\s+balance|"
    r"zen\s+credits?|"
    r"use[\s-]?(?:your\s+)?(?:available\s+)?balance|"
    r"(?:after|beyond).{0,30}(?:usage\s+)?limits?|"
    r"(?:remaining|left).{0,20}balance|"
    r"balance.{0,30}(?:opencode|go|zen)"
    r")\b"
)

# Natural-language asks that should hit OpenCode Go quota — not other skills.
_QUOTA_ASK_RE = re.compile(
    r"(?i)\b("
    r"quota|allowance|rate[\s-]?limit|"
    r"(how\s+much|remaining|left).{0,40}(go|quota|allowance|usage)|"
    r"(?:go|opencode)\b.{0,40}(?:quota|limit|remaining|left|usage)|"
    r"usage\s+limit|"
    r"\bpace\b|\bburn\b"
    r")\b"
)

# Telegram prefixes quoted replies with [Replying to: "..."]. Strip that block
# so quoting our own previous answer (which may mention balance/quota) can't
# re-trigger a fetch+inject on a message that isn't actually asking.
_REPLY_QUOTE_RE = re.compile(r"\[Replying to: \"(?:[^\"\\]|\\.)*\"\]", re.DOTALL)


def _strip_reply_quote(user_message: str) -> str:
    return _REPLY_QUOTE_RE.sub("", user_message or "").strip()

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


def looks_like_balance_question(user_message: str) -> bool:
    return bool(_BALANCE_ASK_RE.search(_strip_reply_quote(user_message)))


def looks_like_quota_question(user_message: str) -> bool:
    if looks_like_balance_question(user_message):
        return False
    return bool(_QUOTA_ASK_RE.search(_strip_reply_quote(user_message)))


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
        "This is OpenCode Go quota (+ Zen balance as Go overage fallback)."
    )


def _ready_context() -> str:
    return (
        "[OpenCode Go quota — first-install notice] "
        "REQUIRED: Your very first sentence to the user must be exactly: "
        "'OpenCode Go quota monitoring is on — ask what\'s left anytime, or use /go-quota.' "
        "Then answer their message normally. Do not dump env var names."
    )


def _quota_answer_context(snapshot: QuotaSnapshot) -> str:
    return (
        "[OpenCode Go quota — live result already fetched] "
        f"{format_natural_summary(snapshot)} "
        "Relay this answer to the user in natural language. "
        "Do NOT say you lack a quota tool. Do NOT load provider-usage-tracking. "
        "Do NOT send them to the web dashboard for this."
    )


def _balance_answer_context(snapshot: QuotaSnapshot) -> str:
    if snapshot.billing is None:
        prose = (
            "I couldn't read Zen balance (no billing data on this fetch). "
            "Try /go-balance or refresh OPENCODE_GO_AUTH_COOKIE."
        )
    else:
        prose = format_balance_summary(snapshot.billing)
    return (
        "[OpenCode Go / Zen balance — live result already fetched] "
        f"{prose} "
        "Relay this answer to the user in natural language. "
        "Do NOT say you lack a balance tool. Do NOT send them to the dashboard."
    )


def _should_announce_ready() -> bool:
    """Once ever after install (disk marker), not on every gateway restart."""
    global _announced_this_process
    if not announce_enabled() or _announced_this_process:
        return False
    if _READY_MARKER.exists():
        _announced_this_process = True
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

    # Telegram quoted-reply prefixes carry our own previous text; strip them so
    # quoting an answer that mentions balance/quota doesn't re-trigger a fetch.
    user_message = _strip_reply_quote(user_message)

    if _should_announce_ready():
        chunks.append(_ready_context())

    # Balance asks first (otherwise "remaining … go" can match quota).
    if looks_like_balance_question(user_message):
        try:
            snapshot = get_snapshot()
            chunks.append(_balance_answer_context(snapshot))
        except Exception:  # noqa: BLE001
            chunks.append(
                "[OpenCode Go balance] Could not fetch billing just now. "
                "Ask the user to try /go-balance, or refresh OPENCODE_GO_AUTH_COOKIE."
            )
    elif looks_like_quota_question(user_message):
        try:
            snapshot = get_snapshot()
            chunks.append(_quota_answer_context(snapshot))
        except Exception:  # noqa: BLE001
            chunks.append(
                "[OpenCode Go quota] Could not fetch quota just now. "
                "Ask the user to try /go-quota, or refresh OPENCODE_GO_AUTH_COOKIE."
            )

    asked = looks_like_balance_question(user_message) or looks_like_quota_question(
        user_message
    )
    if is_opencode_go_model(model) and not asked:
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
