"""OpenCode Go quota Hermes plugin — registration."""

from __future__ import annotations

import logging
from pathlib import Path

# Hermes loads us as a package (relative imports). Pytest may also import this
# file as a bare module when walking the repo — fall back to absolute imports.
try:
    from .ogq_hooks import on_pre_llm_call, on_pre_tool_call
    from .ogq_tools import (
        QUOTA_CHECK_SCHEMA,
        TOOL_NAME,
        go_balance_slash,
        go_quota_slash,
        opencode_go_quota_check,
    )
except ImportError:  # pragma: no cover — bare-module / path fallback
    from ogq_hooks import on_pre_llm_call, on_pre_tool_call
    from ogq_tools import (
        QUOTA_CHECK_SCHEMA,
        TOOL_NAME,
        go_balance_slash,
        go_quota_slash,
        opencode_go_quota_check,
    )

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    ctx.register_tool(
        name=TOOL_NAME,
        toolset="opencode_go_quota",
        schema=QUOTA_CHECK_SCHEMA,
        handler=opencode_go_quota_check,
    )
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_command(
        "go-quota",
        handler=go_quota_slash,
        description="Show OpenCode Go quota (5h / weekly / monthly) + pace",
    )
    ctx.register_command(
        "go-balance",
        handler=go_balance_slash,
        description="Show Zen balance and Use-balance-after-Go-limits",
    )

    skills_dir = Path(__file__).parent / "skills"
    skill_md = skills_dir / "opencode-go-quota" / "SKILL.md"
    if skill_md.exists():
        ctx.register_skill("opencode-go-quota", skill_md)
    else:
        logger.warning("Bundled skill missing at %s", skill_md)
