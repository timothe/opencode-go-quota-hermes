from __future__ import annotations

from quota.scrape import (
    parse_dashboard_html,
    parse_data_slot_format,
    parse_human_readable_time,
    parse_window_usage,
    query_opencode_go_quota,
    _WINDOW_RES,
)
from tests.helpers import build_data_slot_html, build_ssr_html


def test_parse_ssr_pct_first():
    html = build_ssr_html({"rolling": (10, 3600), "weekly": (20, 86400), "monthly": (30, 2_592_000)})
    result = parse_dashboard_html(html)
    assert result.success
    assert result.windows["rolling"].usage_percent == 10
    assert result.windows["rolling"].reset_in_sec == 3600
    assert result.windows["weekly"].usage_percent == 20
    assert result.windows["monthly"].usage_percent == 30


def test_parse_ssr_reset_first():
    html = build_ssr_html(
        {"rolling": (55, 7200), "weekly": (11, 1000), "monthly": (22, 2000)},
        reset_first=True,
    )
    result = parse_dashboard_html(html)
    assert result.success
    assert result.windows["rolling"].usage_percent == 55
    assert result.windows["rolling"].reset_in_sec == 7200


def test_parse_ssr_partial_windows():
    html = build_ssr_html({"monthly": (66.5, 100)})
    result = parse_dashboard_html(html)
    assert result.success
    assert set(result.windows) == {"monthly"}


def test_parse_window_usage_both_orderings():
    re_pct, re_reset = _WINDOW_RES["rolling"]
    assert parse_window_usage(
        "rollingUsage:$R[42]={usagePercent:55,resetInSec:3600}", re_pct, re_reset
    ) == parse_window_usage(  # type equality via fields
        "rollingUsage:$R[7]={resetInSec:3600,usagePercent:55}", re_pct, re_reset
    )


def test_unparseable_html_error():
    result = parse_dashboard_html("<html>no quota here</html>")
    assert not result.success
    assert "Could not parse" in result.error


def test_data_slot_fallback():
    html = build_data_slot_html(
        {
            "rolling": (1, "1 hour 56 minutes"),
            "weekly": (10, "6 days 2 hours"),
            "monthly": (50, "26 days 17 hours"),
        }
    )
    result = parse_dashboard_html(html)
    assert result.success
    assert result.windows["rolling"].reset_in_sec == 6960
    assert result.windows["weekly"].reset_in_sec == 525600
    assert result.windows["monthly"].reset_in_sec == 2307600


def test_data_slot_reset_now():
    html = build_data_slot_html({"rolling": (5, "ignored")}, reset_now="rolling")
    parsed = parse_data_slot_format(html)
    assert parsed["rolling"].reset_in_sec == 0


def test_ssr_preferred_over_data_slot():
    ssr = build_ssr_html({"rolling": (7, 18000)})
    slot = build_data_slot_html({"rolling": (99, "1 hour")})
    result = parse_dashboard_html(ssr + slot)
    assert result.windows["rolling"].usage_percent == 7


def test_human_readable_time():
    assert parse_human_readable_time("1 hour 56 minutes") == 6960
    assert parse_human_readable_time("now") == 0
    assert parse_human_readable_time("nonsense") is None


def test_query_http_success_headers():
    html = build_ssr_html({"rolling": (1, 60)})
    captured = {}

    class Resp:
        status = 200

        def read(self):
            return html.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=10):
        captured["url"] = req.full_url
        captured["cookie"] = req.get_header("Cookie")
        captured["timeout"] = timeout
        return Resp()

    result = query_opencode_go_quota("ws-123", "cookie-abc", opener=opener)
    assert result.success
    assert "ws-123" in captured["url"]
    assert captured["cookie"] == "auth=cookie-abc"


def test_query_http_error_status():
    class Resp:
        status = 401

        def read(self):
            return b"unauthorized"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=10):
        return Resp()

    result = query_opencode_go_quota("ws", "c", opener=opener)
    assert not result.success
    assert "401" in result.error


def test_query_network_error():
    def opener(req, timeout=10):
        raise TimeoutError("timed out")

    result = query_opencode_go_quota("ws", "c", opener=opener)
    assert not result.success
    assert "timed out" in result.error
