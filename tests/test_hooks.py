from __future__ import annotations

import sys

from plugin_loader import PACKAGE_NAME, load_plugin_module


def _hooks():
    load_plugin_module()
    return sys.modules[f"{PACKAGE_NAME}.hooks"]


def _snap(status: str):
    types = sys.modules[f"{PACKAGE_NAME}.quota.types"]
    return types.QuotaSnapshot(
        status=status,
        windows={
            "rolling": types.WindowUsage(95, 60, 5, "2026-01-01T00:00:00Z"),
        },
        breached=["rolling"] if status in {"warn", "critical"} else [],
        soonest_reset_at="2026-01-01T00:00:00Z",
        message=f"{status} msg",
    )


def test_is_opencode_go_model():
    hooks = _hooks()
    assert hooks.is_opencode_go_model("opencode-go/qwen")
    assert hooks.is_opencode_go_model("provider/opencode-go")
    assert not hooks.is_opencode_go_model("openrouter/x")


def test_warn_injects(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("warn"))
    out = hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen")
    assert out is not None
    assert "context" in out
    assert "OpenCode Go" in out["context"]
    assert "2026-01-01T00:00:00Z" not in out["context"]


def test_warn_skips_healthy(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("ok"))
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is None


def test_warn_skips_non_go(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    assert hooks.on_pre_llm_call(session_id="s1", model="openrouter/x") is None


def test_warn_rate_limit(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("warn"))
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is not None
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is None


def test_warn_scrape_error_no_crash(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")

    def boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(hooks, "get_snapshot", boom)
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is None


def test_announce_ready_on_first_turn(monkeypatch):
    hooks = _hooks()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("ok"))
    out = hooks.on_pre_llm_call(
        session_id="s1", model="opencode-go/qwen", is_first_turn=True
    )
    assert out is not None
    assert "plugin is active" in out["context"].lower() or "quota monitoring" in out["context"].lower()
    # Second first-turn in same process should not re-announce
    out2 = hooks.on_pre_llm_call(
        session_id="s2", model="opencode-go/qwen", is_first_turn=True
    )
    assert out2 is None or "plugin is active" not in out2["context"].lower()


def test_block_off_never_blocks(monkeypatch):
    hooks = _hooks()
    monkeypatch.delenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", raising=False)
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    assert hooks.on_pre_tool_call(tool_name="terminal") is None


def test_block_on_critical(monkeypatch):
    hooks = _hooks()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    out = hooks.on_pre_tool_call(tool_name="terminal")
    assert out is not None
    assert out["action"] == "block"
    assert "AUTO_BLOCK" in out["message"]
    assert "critically low" in out["message"]


def test_block_allowlist(monkeypatch):
    hooks = _hooks()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    assert hooks.on_pre_tool_call(tool_name="cronjob") is None
    assert hooks.on_pre_tool_call(tool_name="opencode_go_quota_check") is None


def test_block_warn_only_no_block(monkeypatch):
    hooks = _hooks()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("warn"))
    assert hooks.on_pre_tool_call(tool_name="terminal") is None
