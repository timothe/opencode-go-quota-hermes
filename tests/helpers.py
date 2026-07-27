"""Shared HTML builders for OpenCode Go dashboard fixtures."""

from __future__ import annotations

from typing import Optional


def build_ssr_html(
    windows: dict[str, tuple[float, float]],
    *,
    reset_first: bool = False,
) -> str:
    chunks = []
    for index, key in enumerate(("rolling", "weekly", "monthly")):
        if key not in windows:
            continue
        usage, reset = windows[key]
        field = f"{key}Usage"
        if reset_first:
            body = f"resetInSec:{reset},usagePercent:{usage}"
        else:
            body = f"usagePercent:{usage},resetInSec:{reset}"
        chunks.append(f"{field}:$R[{10 + index}]={{{body}}}")
    return " " + "".join(chunks) + " "


def build_data_slot_html(
    windows: dict[str, tuple[float, str]],
    *,
    reset_now: Optional[str] = None,
) -> str:
    labels = {
        "rolling": "Rolling Usage",
        "weekly": "Weekly Usage",
        "monthly": "Monthly Usage",
    }
    items = []
    for key in ("rolling", "weekly", "monthly"):
        if key not in windows:
            continue
        usage, reset_time = windows[key]
        if reset_now == key:
            reset_block = '<span data-slot="reset-now">now</span>'
        else:
            reset_block = (
                f'<span data-slot="reset-time">Resets in {reset_time}</span>'
            )
        items.append(
            f'<div data-slot="usage-item">'
            f'<span data-slot="usage-label">{labels[key]}</span>'
            f'<span data-slot="usage-value">{usage} %</span>'
            f"{reset_block}"
            f"</div>"
        )
    return " ".join(items)
