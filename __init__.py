"""OpenCode Go quota Hermes plugin — registration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Hermes loads this as a package; pytest may import it as a bare module.
# Putting the plugin dir on sys.path lets sibling imports work either way.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from hooks import on_pre_llm_call, on_pre_tool_call  # noqa: E402
from tools import (  # noqa: E402
    QUOTA_CHECK_SCHEMA,
    TOOL_NAME,
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
        description="Show OpenCode Go quota (5h / weekly / monthly)",
    )

    skills_dir = Path(__file__).parent / "skills"
    skill_md = skills_dir / "opencode-go-quota" / "SKILL.md"
    if skill_md.exists():
        ctx.register_skill("opencode-go-quota", skill_md)
    else:
        logger.warning("Bundled skill missing at %s", skill_md)
