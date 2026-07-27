from __future__ import annotations

import json
import sys

from plugin_loader import PACKAGE_NAME, load_plugin_module
from tests.helpers import build_ssr_html


def _tools():
    load_plugin_module()
    return sys.modules[f"{PACKAGE_NAME}.tools"]


def test_quota_check_json(monkeypatch):
    tools = _tools()
    monkeypatch.setenv("OPENCODE_GO_WORKSPACE_ID", "ws")
    monkeypatch.setenv("OPENCODE_GO_AUTH_COOKIE", "tok")
    tools.default_cache.clear()
    html = build_ssr_html({"rolling": (10, 60), "weekly": (20, 120), "monthly": (30, 180)})
    scrape = sys.modules[f"{PACKAGE_NAME}.quota.scrape"]
    monkeypatch.setattr(
        f"{PACKAGE_NAME}.quota.check.query_opencode_go_quota",
        lambda workspace_id, auth_cookie, opener=None, timeout_s=10: scrape.parse_dashboard_html(
            html
        ),
    )
    out = json.loads(tools.quota_check({}))
    assert out["status"] in {"ok", "warn", "critical"}
    assert "rolling" in out["windows"]


def test_quota_slash_help():
    assert "Usage" in _tools().quota_slash("help")


def test_quota_slash_human(monkeypatch):
    tools = _tools()
    types = sys.modules[f"{PACKAGE_NAME}.quota.types"]
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
    text = tools.quota_slash("")
    assert "warn" in text
    assert "5h" in text
