"""Shared types for OpenCode Go quota."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

WindowKey = Literal["rolling", "weekly", "monthly"]
WINDOW_ORDER: tuple[WindowKey, ...] = ("rolling", "weekly", "monthly")
WINDOW_LABELS: dict[WindowKey, str] = {
    "rolling": "5h",
    "weekly": "Weekly",
    "monthly": "Monthly",
}

StatusLevel = Literal["ok", "warn", "critical", "incomplete", "error"]


@dataclass(frozen=True)
class WindowUsage:
    usage_percent: float
    reset_in_sec: float
    percent_remaining: float
    reset_at: str  # ISO-8601

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuotaSnapshot:
    status: StatusLevel
    windows: dict[WindowKey, WindowUsage]
    breached: list[WindowKey]
    soonest_reset_at: Optional[str]
    message: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "windows": {k: v.to_dict() for k, v in self.windows.items()},
            "breached": list(self.breached),
            "soonest_reset_at": self.soonest_reset_at,
            "message": self.message,
            "error": self.error,
        }
