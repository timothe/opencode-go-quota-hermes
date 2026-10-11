"""Tests for the console billing client (Zen balance + useBalance)."""

from __future__ import annotations

import json
import urllib.error

from quota.billing import (
    apply_auto_recharge,
    apply_go_status,
    parse_billing_status,
    query_opencode_billing,
)
from quota.types import BillingInfo

BILLING_STATUS = {
    "billingMode": "credit",
    "mode": "pay-as-you-go",
    "balanceMicroCents": "1999960750",
    "availableMicroCents": "1999960750",
    "canPurchaseCredits": True,
    "canEnableAutoRecharge": True,
}
AUTO_RECHARGE = {
    "enabled": True,
    "thresholdDollars": 5,
    "rechargeAmountDollars": 20,
    "pending": False,
}
GO_STATUS = {
    "useBalance": True,
    "access": {
        "meters": {
            "fiveHour": {"usedMicroCents": 0, "limitMicroCents": 1200000000},
            "week": {"usedMicroCents": 3600000000, "limitMicroCents": 3000000000},
            "month": {"usedMicroCents": 4920000000, "limitMicroCents": 6000000000},
        }
    },
}


class _Resp:
    def __init__(self, body, status: int = 200):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _routing_opener(routes, calls=None):
    def opener(req, timeout=10):
        url = req.full_url
        if calls is not None:
            calls.append(url)
        for path, resp in routes.items():
            if url.endswith(path):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected url {url}")

    return opener


def test_parse_billing_status_microcents_to_dollars():
    info = parse_billing_status(BILLING_STATUS)
    assert not info.error
    assert abs(info.balance_usd - 19.9996075) < 1e-9
    assert info.mode == "pay-as-you-go"
    assert info.billing_mode == "credit"
    assert info.can_purchase_credits is True


def test_parse_billing_status_accepts_numbers_and_rejects_missing():
    info = parse_billing_status({"balanceMicroCents": 100000000, "availableMicroCents": 50000000})
    assert abs(info.balance_usd - 1.0) < 1e-12
    assert abs(info.available_usd - 0.5) < 1e-12
    assert parse_billing_status({"mode": "pay-as-you-go"}).error
    assert parse_billing_status([]).error


def test_apply_auto_recharge_dollars_are_not_microcents():
    info = apply_auto_recharge(BillingInfo(balance_usd=1.0), AUTO_RECHARGE)
    assert info.auto_reload is True
    assert info.reload_amount_usd == 20.0
    assert info.reload_trigger_usd == 5.0
    assert info.pending_auto_recharge is False


def test_apply_go_status_reads_toggle_and_monthly_meter():
    info = apply_go_status(BillingInfo(balance_usd=1.0), GO_STATUS)
    assert info.use_balance is True
    assert abs(info.monthly_usage_usd - 49.2) < 1e-9
    assert abs(info.monthly_limit_usd - 60.0) < 1e-9


def test_apply_go_status_without_access_leaves_toggle_unknown():
    info = apply_go_status(BillingInfo(balance_usd=1.0), {"useBalance": False})
    assert info.use_balance is False
    assert info.monthly_limit_usd == 0.0


def test_query_without_cookie_explains_itself():
    info = query_opencode_billing("")
    assert info.error
    assert "OPENCODE_GO_AUTH_COOKIE" in info.error


def test_console_auth_headers_prefers_bearer_token():
    from quota.billing import console_auth_headers

    assert console_auth_headers("tok") == {"Cookie": "auth=tok"}
    assert console_auth_headers("tok", "bearer") == {"Authorization": "Bearer bearer"}
    assert console_auth_headers("tok", "bearer", "org_1") == {
        "Authorization": "Bearer bearer",
        "x-org-id": "org_1",
    }


def test_query_with_console_token_uses_bearer_auth():
    seen = {}

    def opener(req, timeout=10):
        seen["auth"] = req.get_header("Authorization")
        seen["cookie"] = req.get_header("Cookie")
        return _Resp(BILLING_STATUS)

    info = query_opencode_billing(
        "", console_token="bearer-tok", org_id="org_1", opener=opener
    )
    assert not info.error
    assert seen["auth"] == "Bearer bearer-tok"
    assert seen["cookie"] is None


def test_query_happy_path_merges_three_endpoints():
    calls: list[str] = []
    opener = _routing_opener(
        {
            "/console/api/billing/status": _Resp(BILLING_STATUS),
            "/console/api/billing/auto-recharge": _Resp(AUTO_RECHARGE),
            "/console/api/go/status": _Resp(GO_STATUS),
        },
        calls,
    )
    info = query_opencode_billing("tok", opener=opener)
    assert not info.error
    assert abs(info.balance_usd - 19.9996075) < 1e-9
    assert info.use_balance is True
    assert info.auto_reload is True
    assert len(calls) == 3


def test_query_survives_optional_endpoint_failures():
    opener = _routing_opener(
        {
            "/console/api/billing/status": _Resp(BILLING_STATUS),
            "/console/api/billing/auto-recharge": _Resp("nope", status=500),
            "/console/api/go/status": urllib.error.HTTPError(
                "https://opencode.ai/console/api/go/status", 404, "Not Found", None, None
            ),
        }
    )
    info = query_opencode_billing("tok", opener=opener)
    assert not info.error
    assert abs(info.balance_usd - 19.9996075) < 1e-9
    assert info.use_balance is None


def test_query_stale_cookie_is_reported_as_session_problem():
    opener = _routing_opener(
        {
            "/console/api/billing/status": urllib.error.HTTPError(
                "https://opencode.ai/console/api/billing/status",
                401,
                "Unauthorized",
                None,
                None,
            )
        }
    )
    info = query_opencode_billing("dead", opener=opener)
    assert info.error
    assert "401" in info.error
    assert "cookie" in info.error.lower()


def test_query_non_json_body_is_reported():
    opener = _routing_opener({"/console/api/billing/status": _Resp(b"<html>login</html>")})
    info = query_opencode_billing("tok", opener=opener)
    assert "non-JSON" in info.error
