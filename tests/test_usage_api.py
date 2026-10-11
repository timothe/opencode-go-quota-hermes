"""Tests for the official Go usage API path (/zen/go/v1/usage)."""

from __future__ import annotations

import json
import urllib.error

from quota.scrape import (
    parse_usage_api_payload,
    query_opencode_go_usage_api,
)

NOW_MS = 1_791_705_600_000.0  # 2026-10-11T08:00:00Z, fixed clock for reset maths


def _payload(**windows) -> dict:
    return {"usage": {k: v for k, v in windows.items()}}


def _win(percent: float, resets_at: str, status: str = "ok") -> dict:
    return {"status": status, "percent": percent, "resetsAt": resets_at}


class _Resp:
    def __init__(self, body: str, status: int = 200):
        self.status = status
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_ok_computes_reset_seconds():
    payload = _payload(
        rolling=_win(0, "2026-10-11T13:01:09.000Z"),
        weekly=_win(46, "2026-10-12T00:00:00.000Z"),
        monthly=_win(82, "2026-10-14T21:34:50.000Z"),
    )
    res = parse_usage_api_payload(payload, now_ms=NOW_MS)
    assert res.success
    assert set(res.windows) == {"rolling", "weekly", "monthly"}
    assert res.windows["weekly"].usage_percent == 46
    assert round(res.windows["weekly"].reset_in_sec) == 57600  # 16h to reset
    assert round(res.windows["rolling"].reset_in_sec) == 18069
    assert res.windows["rolling"].usage_percent == 0


def test_parse_rate_limited_pins_to_100_percent():
    res = parse_usage_api_payload(
        _payload(rolling=_win(37, "2026-10-11T13:01:09.000Z", status="rate-limited")),
        now_ms=NOW_MS,
    )
    assert res.success
    assert res.windows["rolling"].usage_percent == 100


def test_parse_clamps_out_of_range_percent():
    res = parse_usage_api_payload(
        _payload(weekly=_win(120, "2026-10-12T00:00:00.000Z")), now_ms=NOW_MS
    )
    assert res.success
    assert res.windows["weekly"].usage_percent == 100


def test_parse_expired_reset_floors_at_zero():
    res = parse_usage_api_payload(
        _payload(rolling=_win(10, "2020-01-01T00:00:00.000Z")), now_ms=NOW_MS
    )
    assert res.success
    assert res.windows["rolling"].reset_in_sec == 0


def test_parse_missing_usage_is_error():
    assert not parse_usage_api_payload({}).success
    assert not parse_usage_api_payload([]).success


def test_parse_bad_resets_at_is_error():
    res = parse_usage_api_payload(_payload(weekly=_win(46, "not-a-date")), now_ms=NOW_MS)
    assert not res.success
    assert "resetsAt" in res.error


def test_parse_offload_window_without_offset_is_still_usable():
    res = parse_usage_api_payload(
        _payload(monthly=_win(82, "2026-10-14T21:34:50")), now_ms=NOW_MS
    )
    assert res.success
    assert res.windows["monthly"].usage_percent == 82


def test_query_sends_bearer_token_and_parses():
    seen = {}

    def opener(req, timeout=10):
        seen["auth"] = req.get_header("Authorization")
        seen["accept"] = req.get_header("Accept")
        seen["url"] = req.full_url
        return _Resp(
            json.dumps(_payload(rolling=_win(5, "2026-10-11T13:01:09.000Z")))
        )

    res = query_opencode_go_usage_api("sk-test", opener=opener)
    assert res.success
    assert seen["auth"] == "Bearer sk-test"
    assert seen["url"].endswith("/zen/go/v1/usage")
    assert "json" in (seen["accept"] or "")


def test_query_http_error_surfaces_status():
    def opener(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    res = query_opencode_go_usage_api("bad", opener=opener)
    assert not res.success
    assert "401" in res.error


def test_query_non_json_body_is_error():
    res = query_opencode_go_usage_api("sk", opener=lambda req, timeout=10: _Resp("<html>"))
    assert not res.success
    assert "non-JSON" in res.error
