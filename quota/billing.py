"""OpenCode workspace /billing scraper (Zen balance + useBalance).

Pattern ported from donrami/pi-go-bars (MIT) parseBilling.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Callable, Optional

from .scrape import DEFAULT_TIMEOUT_S, USER_AGENT, _sanitize
from .types import BillingInfo

BILLING_URL_PREFIX = "https://opencode.ai/workspace/"
BILLING_URL_SUFFIX = "/billing"
MICROCENTS = 1e8

_RE_BALANCE = re.compile(r"balance:(-?\d+(?:\.\d+)?)")
_RE_MONTHLY_USAGE = re.compile(r"monthlyUsage:(-?\d+(?:\.\d+)?)")
_RE_MONTHLY_LIMIT = re.compile(r"monthlyLimit:(-?\d+(?:\.\d+)?)")
_RE_RELOAD = re.compile(r"reload:(!0|!1|true|false|null)")
_RE_RELOAD_AMOUNT = re.compile(r"reloadAmount:(-?\d+(?:\.\d+)?)")
_RE_RELOAD_TRIGGER = re.compile(r"reloadTrigger:(-?\d+(?:\.\d+)?)")
_RE_USE_BALANCE = re.compile(r"useBalance:(!0|!1|true|false)")


def _parse_solid_bool(raw: str) -> bool:
    if raw in {"!0", "true"}:
        return True
    if raw in {"!1", "false", "null"}:
        return False
    try:
        return float(raw) != 0.0
    except ValueError:
        return False


def _num_or_none(text: str, pattern: re.Pattern[str]) -> Optional[float]:
    m = pattern.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _looks_like_billing(html: str) -> bool:
    return (
        "monthlyLimit" in html
        or "monthlyUsage" in html
        or bool(re.search(r"balance:-?\d", html))
    )


def extract_billing_object(html: str) -> Optional[str]:
    """Extract the SolidJS billing object anchored on customerID:\"cus_...\"."""
    start = html.find('customerID:"cus_')
    if start < 0:
        return None
    brace_start = html.rfind("{", 0, start + 1)
    if brace_start < 0:
        return None
    depth = 0
    for i in range(brace_start, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[brace_start : i + 1]
    return None


def parse_billing_html(html: str) -> BillingInfo:
    obj = extract_billing_object(html)
    if not obj:
        err = (
            "billing parser may be outdated"
            if _looks_like_billing(html)
            else "no billing data on page"
        )
        return BillingInfo(error=err)

    balance = _num_or_none(obj, _RE_BALANCE)
    monthly_usage = _num_or_none(obj, _RE_MONTHLY_USAGE)
    monthly_limit = _num_or_none(obj, _RE_MONTHLY_LIMIT)
    reload_raw = (_RE_RELOAD.search(obj) or [None, None])[1]
    reload_amount = _num_or_none(obj, _RE_RELOAD_AMOUNT)
    reload_trigger = _num_or_none(obj, _RE_RELOAD_TRIGGER)
    use_raw = (_RE_USE_BALANCE.search(obj) or [None, None])[1]

    if balance is None and monthly_usage is None and monthly_limit is None:
        return BillingInfo(error="billing parser may be outdated")

    use_balance: Optional[bool] = None
    if use_raw is not None:
        use_balance = _parse_solid_bool(use_raw)

    return BillingInfo(
        balance_usd=(balance / MICROCENTS) if balance is not None else 0.0,
        monthly_usage_usd=(monthly_usage / MICROCENTS)
        if monthly_usage is not None
        else 0.0,
        monthly_limit_usd=monthly_limit if monthly_limit is not None else 0.0,
        use_balance=use_balance,
        auto_reload=_parse_solid_bool(reload_raw) if reload_raw else False,
        reload_amount_usd=reload_amount if reload_amount is not None else 0.0,
        reload_trigger_usd=reload_trigger if reload_trigger is not None else 0.0,
    )


FetchFn = Callable[..., object]


def query_opencode_billing(
    workspace_id: str,
    auth_cookie: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    opener: Optional[FetchFn] = None,
) -> BillingInfo:
    url = (
        f"{BILLING_URL_PREFIX}"
        f"{urllib.request.quote(workspace_id, safe='')}"
        f"{BILLING_URL_SUFFIX}"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Cookie": f"auth={auth_cookie}",
        },
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(req, timeout=timeout_s) as resp:  # type: ignore[arg-type]
            status = getattr(resp, "status", None) or resp.getcode()
            body = resp.read()
            text = (
                body.decode("utf-8", errors="replace")
                if isinstance(body, bytes)
                else str(body)
            )
            if int(status) < 200 or int(status) >= 300:
                return BillingInfo(
                    error=f"OpenCode billing error {status}: {_sanitize(text)}"
                )
            return parse_billing_html(text)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc.reason)
        return BillingInfo(
            error=f"OpenCode billing error {exc.code}: {_sanitize(body)}"
        )
    except Exception as exc:  # noqa: BLE001
        return BillingInfo(error=_sanitize(str(exc)))
