from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from plugin_loader import load_plugin_module


def test_register_wires_everything():
    plugin = load_plugin_module()
    ctx = MagicMock()
    plugin.register(ctx)
    ctx.register_tool.assert_called_once()
    assert ctx.register_tool.call_args.kwargs["name"] == "opencode_go_quota_check"
    hook_names = [c.args[0] for c in ctx.register_hook.call_args_list]
    assert "pre_llm_call" in hook_names
    assert "pre_tool_call" in hook_names
    ctx.register_command.assert_called_once()
    assert ctx.register_command.call_args.args[0] == "go-quota"
    ctx.register_skill.assert_called_once()
    assert ctx.register_skill.call_args.args[0] == "opencode-go-quota"


def test_skill_frontmatter():
    skill = (
        Path(__file__).resolve().parents[1]
        / "opencode-go-quota"
        / "skills"
        / "opencode-go-quota"
        / "SKILL.md"
    )
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: opencode-go-quota" in text
    assert "What's my current quota?" in text
    assert "opencode_go_quota_check" in text
