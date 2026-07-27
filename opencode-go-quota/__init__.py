"""OpenCode Go quota Hermes plugin — registration."""

from __future__ import annotations

import logging
from pathlib import Path

from .hooks import on_pre_llm_call, on_pre_tool_call
from .tools import QUOTA_CHECK_SCHEMA, quota_check, quota_slash

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    ctx.register_tool(
        name="quota_check",
        toolset="opencode_go_quota",
        schema=QUOTA_CHECK_SCHEMA,
        handler=quota_check,
    )
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_command(
        "quota",
        handler=quota_slash,
        description="Show OpenCode Go quota (5h / weekly / monthly)",
    )

    skills_dir = Path(__file__).parent / "skills"
    skill_md = skills_dir / "opencode-go-quota" / "SKILL.md"
    if skill_md.exists():
        ctx.register_skill("opencode-go-quota", skill_md)
    else:
        logger.warning("Bundled skill missing at %s", skill_md)
