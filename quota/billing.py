"""OpenCode Console billing client: Zen balance + Go use-balance toggle.

The old `/workspace/{id}/billing` SSR page is gone. opencode.ai now serves a
console SPA backed by JSON APIs under `/console/api`, so balance comes from:

  GET /console/api/billing/status        balanceMicroCents, availableMicroCents, mode
  GET /console/api/billing/auto-recharge auto-recharge settings (plain dollars)
  GET /console/api/go/status             useBalance + Go window meters

All three need the browser session cookie named `auth`. The Go API key cannot
read billing (the console answers 403 for a bearer key, 401 for a dead cookie),
so this half of the plugin stays cookie-based while quota runs on the API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Callable, Optional

from .scrape import DEFAULT_TIMEOUT_S, USER_AGENT, _sanitize
from .types import BillingInfo

CONSOLE_ORIGIN = "https://opencode.ai"
BILLING_STATUS_PATH = "/console/api/billing/status"
AUTO_RECHARGE_PATH = "/console/api/billing/auto-recharge"
GO_STATUS_PATH = "/console/api/go/status"
# 1e8 microcents = $1 (dollars x 100 cents x 1e6 microcents).
MICROCENTS_PER_USD = 1e8

FetchFn = Callable[..., object]


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _usd_from_microcents(value: Any) -> Optional[float]:
    raw = _as_float(value)
    return None if raw is None else raw / MICROCENTS_PER_USD


def _http_error_message(status: int, path: str) -> str:
    if status in (401, 403):
        return (
            f"console session rejected ({status}) for {path}: the auth cookie is "
            "missing, expired or not signed in"
        )
    return f"OpenCode console error {status} ({path})"


def console_auth_headers(
    auth_cookie: str = "",
    console_token: str = "",
    org_id: str = "",
) -> dict[str, str]:
    """Console auth headers. A bearer token wins over the browser cookie."""
    token = (console_token or "").strip()
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        if (org_id or "").strip():
            headers["x-org-id"] = org_id.strip()
        return headers
    return {"Cookie": f"auth={(auth_cookie or '').strip()}"}


def console_get_json(
    path: str,
    auth_headers: dict[str, str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    opener: Optional[FetchFn] = None,
) -> tuple[Optional[Any], str, int]:
    """GET a console JSON endpoint. Returns (payload, error, http_status)."""
    req = urllib.request.Request(
        f"{CONSOLE_ORIGIN}{path}",
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **auth_headers,
        },
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(req, timeout=timeout_s) as resp:  # type: ignore[arg-type]
            status = int(getattr(resp, "status", None) or resp.getcode())
            body = resp.read()
            text = (
                body.decode("utf-8", errors="replace")
                if isinstance(body, bytes)
                else str(body)
            )
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = str(exc.reason)
        if exc.code in (401, 403):
            return None, _http_error_message(exc.code, path), exc.code
        return (
            None,
            f"OpenCode console error {exc.code} ({path}): {_sanitize(text)}",
            exc.code,
        )
    except Exception as exc:  # noqa: BLE001
        return None, _sanitize(str(exc)), 0

    if status < 200 or status >= 300:
        return None, f"OpenCode console error {status} ({path}): {_sanitize(text)}", status
    try:
        return json.loads(text), "", status
    except ValueError:
        return (
            None,
            f"OpenCode console returned non-JSON for {path}: {_sanitize(text, 60)}",
            status,
        )


def parse_billing_status(payload: object) -> BillingInfo:
    """Parse GET /console/api/billing/status."""
    if not isinstance(payload, dict):
        return BillingInfo(error="console billing status was not an object")
    balance = _usd_from_microcents(payload.get("balanceMicroCents"))
    if balance is None:
        return BillingInfo(error="console billing status carried no balanceMicroCents")
    available = _usd_from_microcents(payload.get("availableMicroCents"))
    return BillingInfo(
        balance_usd=balance,
        available_usd=balance if available is None else available,
        mode=str(payload.get("mode") or ""),
        billing_mode=str(payload.get("billingMode") or ""),
        can_purchase_credits=bool(payload.get("canPurchaseCredits")),
    )


def apply_auto_recharge(info: BillingInfo, payload: object) -> BillingInfo:
    """Fold GET /console/api/billing/auto-recharge into a BillingInfo."""
    if not isinstance(payload, dict):
        return info
    amount = _as_float(payload.get("rechargeAmountDollars"))
    threshold = _as_float(payload.get("thresholdDollars"))
    return replace(
        info,
        auto_reload=bool(payload.get("enabled")),
        reload_amount_usd=0.0 if amount is None else amount,
        reload_trigger_usd=0.0 if threshold is None else threshold,
        pending_auto_recharge=bool(payload.get("pending")),
        failure_reason=str(payload.get("failureReason") or ""),
    )


def apply_go_status(info: BillingInfo, payload: object) -> BillingInfo:
    """Fold GET /console/api/go/status: useBalance + Go monthly money meter."""
    if not isinstance(payload, dict):
        return info
    use_balance = payload.get("useBalance")
    access = payload.get("access")
    month: object = None
    if isinstance(access, dict):
        meters = access.get("meters")
        if isinstance(meters, dict):
            month = meters.get("month")
    used = (
        _usd_from_microcents(month.get("usedMicroCents"))
        if isinstance(month, dict)
        else None
    )
    limit = (
        _usd_from_microcents(month.get("limitMicroCents"))
        if isinstance(month, dict)
        else None
    )
    return replace(
        info,
        use_balance=use_balance if isinstance(use_balance, bool) else None,
        monthly_usage_usd=0.0 if used is None else used,
        monthly_limit_usd=0.0 if limit is None else limit,
    )


def query_opencode_billing(
    auth_cookie: str = "",
    *,
    console_token: str = "",
    org_id: str = "",
    timeout_s: float = DEFAULT_TIMEOUT_S,
    opener: Optional[FetchFn] = None,
) -> BillingInfo:
    """Zen balance + Go overage toggle from the console APIs."""
    headers = console_auth_headers(auth_cookie, console_token, org_id)
    if not (console_token or "").strip() and not (auth_cookie or "").strip():
        return BillingInfo(
            error=(
                "no console credentials: Zen balance needs either "
                "OPENCODE_GO_AUTH_COOKIE (browser session) or "
                "OPENCODE_GO_CONSOLE_TOKEN (console bearer token)"
            )
        )

    billing_payload, error, _ = console_get_json(
        BILLING_STATUS_PATH, headers, timeout_s=timeout_s, opener=opener
    )
    if billing_payload is None:
        return BillingInfo(error=error)

    info = parse_billing_status(billing_payload)
    if info.error:
        return info

    auto_payload, _, _ = console_get_json(
        AUTO_RECHARGE_PATH, headers, timeout_s=timeout_s, opener=opener
    )
    if auto_payload is not None:
        info = apply_auto_recharge(info, auto_payload)

    go_payload, _, _ = console_get_json(
        GO_STATUS_PATH, headers, timeout_s=timeout_s, opener=opener
    )
    if go_payload is not None:
        info = apply_go_status(info, go_payload)

    return info
