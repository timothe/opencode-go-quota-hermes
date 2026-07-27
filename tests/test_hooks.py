from __future__ import annotations

import sys

from plugin_loader import PACKAGE_NAME, load_plugin_module


def _hooks():
    load_plugin_module()
    return sys.modules[f"{PACKAGE_NAME}.ogq_hooks"]


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
    assert not hooks.is_opencode_go_model("openrouter/x")


def test_looks_like_quota_question():
    hooks = _hooks()
    assert hooks.looks_like_quota_question("What's my remaining quota?")
    assert hooks.looks_like_quota_question("how much OpenCode Go do I have left?")
    assert not hooks.looks_like_quota_question("what's the weather?")
    assert not hooks.looks_like_quota_question(
        "What's my remaining balance on Opencode go?"
    )


def test_looks_like_balance_question():
    hooks = _hooks()
    assert hooks.looks_like_balance_question(
        "What's my remaining balance on Opencode go?"
    )
    assert hooks.looks_like_balance_question(
        "Did I enable use balance after reaching the usage limits?"
    )
    assert not hooks.looks_like_balance_question("What's my remaining quota?")


def test_quota_question_injects_live_answer(monkeypatch):
    hooks = _hooks()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("ok"))
    out = hooks.on_pre_llm_call(
        session_id="s1",
        model="opencode-go/qwen",
        user_message="what's my remaining quota?",
    )
    assert out is not None
    assert "already fetched" in out["context"]
    assert "provider-usage-tracking" in out["context"]
    assert "lack a quota tool" in out["context"]


def test_balance_question_injects_billing(monkeypatch):
    hooks = _hooks()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    types = sys.modules[f"{PACKAGE_NAME}.quota.types"]
    snap = _snap("ok")
    # Rebuild with billing — frozen dataclass via replace pattern
    snap = types.QuotaSnapshot(
        status=snap.status,
        windows=snap.windows,
        breached=snap.breached,
        soonest_reset_at=snap.soonest_reset_at,
        message=snap.message,
        billing=types.BillingInfo(balance_usd=20.0, use_balance=True),
    )
    monkeypatch.setattr(hooks, "get_snapshot", lambda: snap)
    out = hooks.on_pre_llm_call(
        session_id="s1",
        model="opencode-go/qwen",
        user_message="What's my remaining balance on Opencode go?",
    )
    assert out is not None
    assert "$20.00" in out["context"]
    assert "Use-balance-after-Go-limits is on" in out["context"]


def test_warn_injects(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("warn"))
    out = hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen")
    assert out is not None
    assert "OpenCode Go" in out["context"]


def test_warn_skips_healthy(monkeypatch):
    hooks = _hooks()
    hooks._inject_limiter.clear()
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "false")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("ok"))
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is None


def test_announce_ready_once_after_install(monkeypatch, tmp_path):
    hooks = _hooks()
    marker = tmp_path / "announced"
    monkeypatch.setattr(hooks, "_READY_MARKER", marker)
    hooks.reset_announce_state_for_tests()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_ANNOUNCE", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("ok"))

    out = hooks.on_pre_llm_call(
        session_id="s1", model="opencode-go/qwen", is_first_turn=False
    )
    assert out is not None
    assert "first-install notice" in out["context"]
    assert marker.exists()

    # Later process / restart: disk marker present → no re-announce.
    hooks._announced_this_process = False
    assert hooks.on_pre_llm_call(session_id="s1", model="opencode-go/qwen") is None


def test_block_on_critical(monkeypatch):
    hooks = _hooks()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    out = hooks.on_pre_tool_call(tool_name="terminal")
    assert out is not None
    assert out["action"] == "block"


def test_block_allowlist(monkeypatch):
    hooks = _hooks()
    monkeypatch.setenv("OPENCODE_GO_QUOTA_AUTO_BLOCK", "true")
    monkeypatch.setattr(hooks, "get_snapshot", lambda: _snap("critical"))
    assert hooks.on_pre_tool_call(tool_name="opencode_go_quota_check") is None

