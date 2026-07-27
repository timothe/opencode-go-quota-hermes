from __future__ import annotations

import json
import sys

from plugin_loader import PACKAGE_NAME, load_plugin_module
from tests.helpers import build_ssr_html


def _tools():
    load_plugin_module()
    return sys.modules[f"{PACKAGE_NAME}.tools"]


def test_quota_check_natural_language(monkeypatch):
    tools = _tools()
    monkeypatch.setenv("OPENCODE_GO_WORKSPACE_ID", "ws")
    monkeypatch.setenv("OPENCODE_GO_AUTH_COOKIE", "tok")
    tools.default_cache.clear()
    html = build_ssr_html({"rolling": (10, 60), "weekly": (20, 120), "monthly": (30, 180)})
    scrape = sys.modules["quota.scrape"]
    monkeypatch.setattr(
        "quota.check.query_opencode_go_quota",
        lambda workspace_id, auth_cookie, opener=None, timeout_s=10: scrape.parse_dashboard_html(
            html
        ),
    )
    out = tools.opencode_go_quota_check({})
    assert "OpenCode Go" in out
    assert "remaining" in out.lower()
    assert "T00:00:00" not in out


def test_quota_check_json_opt_in(monkeypatch):
    tools = _tools()
    types = sys.modules["quota.types"]
    snap = types.QuotaSnapshot(
        status="ok",
        windows={"rolling": types.WindowUsage(0, 60, 100, "2026-01-01T00:00:00Z")},
        breached=[],
        soonest_reset_at=None,
    )
    monkeypatch.setattr(tools, "get_snapshot", lambda force=False, **k: snap)
    out = json.loads(tools.opencode_go_quota_check({"json": True}))
    assert out["status"] == "ok"


def test_go_quota_slash_help():
    help_text = _tools().go_quota_slash("help")
    assert "What's my current quota?" in help_text
    assert "/go-quota" in help_text


def test_go_quota_slash_human(monkeypatch):
    tools = _tools()
    types = sys.modules["quota.types"]
    snap = types.QuotaSnapshot(
        status="warn",
        windows={
            "rolling": types.WindowUsage(90, 60, 10, "2026-01-01T00:00:00Z"),
        },
        breached=["rolling"],
        soonest_reset_at="2026-01-01T00:00:00Z",
        message="WARN",
    )
    monkeypatch.setattr(tools, "get_snapshot", lambda force=False, **k: snap)
    text = tools.go_quota_slash("")
    assert "OpenCode Go" in text
    assert "getting low" in text
    assert "2026-01-01T00:00:00Z" not in text
