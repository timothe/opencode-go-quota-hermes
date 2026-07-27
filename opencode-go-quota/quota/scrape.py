"""OpenCode Go dashboard scraper.

Inspired by slkiser/opencode-quota (MIT) src/lib/opencode-go.ts.
Fetches workspace Go page and parses rolling / weekly / monthly usage.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from .types import WINDOW_ORDER, WindowKey, WindowUsage

DASHBOARD_URL_PREFIX = "https://opencode.ai/workspace/"
DASHBOARD_URL_SUFFIX = "/go"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "Gecko/20100101 Firefox/148.0"
)
DEFAULT_TIMEOUT_S = 10.0

_NUM = r"(-?\d+(?:\.\d+)?)"

_WINDOW_RES: dict[WindowKey, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "rolling": (
        re.compile(
            rf"rollingUsage:\$R\[\d+\]=\{{[^}}]*usagePercent:{_NUM}[^}}]*resetInSec:{_NUM}[^}}]*\}}"
        ),
        re.compile(
            rf"rollingUsage:\$R\[\d+\]=\{{[^}}]*resetInSec:{_NUM}[^}}]*usagePercent:{_NUM}[^}}]*\}}"
        ),
    ),
    "weekly": (
        re.compile(
            rf"weeklyUsage:\$R\[\d+\]=\{{[^}}]*usagePercent:{_NUM}[^}}]*resetInSec:{_NUM}[^}}]*\}}"
        ),
        re.compile(
            rf"weeklyUsage:\$R\[\d+\]=\{{[^}}]*resetInSec:{_NUM}[^}}]*usagePercent:{_NUM}[^}}]*\}}"
        ),
    ),
    "monthly": (
        re.compile(
            rf"monthlyUsage:\$R\[\d+\]=\{{[^}}]*usagePercent:{_NUM}[^}}]*resetInSec:{_NUM}[^}}]*\}}"
        ),
        re.compile(
            rf"monthlyUsage:\$R\[\d+\]=\{{[^}}]*resetInSec:{_NUM}[^}}]*usagePercent:{_NUM}[^}}]*\}}"
        ),
    ),
}


@dataclass(frozen=True)
class ScrapedWindow:
    usage_percent: float
    reset_in_sec: float


@dataclass(frozen=True)
class ScrapeOk:
    windows: dict[WindowKey, ScrapedWindow] = field(default_factory=dict)
    success: bool = True


@dataclass(frozen=True)
class ScrapeErr:
    error: str = ""
    success: bool = False


ScrapeResult = Union[ScrapeOk, ScrapeErr]


def parse_window_usage(
    html: str,
    re_pct_first: re.Pattern[str],
    re_reset_first: re.Pattern[str],
) -> Optional[ScrapedWindow]:
    m = re_pct_first.search(html)
    if m:
        usage, reset = float(m.group(1)), float(m.group(2))
        if usage == usage and reset == reset:  # finite
            return ScrapedWindow(usage_percent=usage, reset_in_sec=reset)
    m = re_reset_first.search(html)
    if m:
        reset, usage = float(m.group(1)), float(m.group(2))
        if usage == usage and reset == reset:
            return ScrapedWindow(usage_percent=usage, reset_in_sec=reset)
    return None


def parse_human_readable_time(time_str: str) -> Optional[float]:
    normalized = re.sub(r"\s+", " ", time_str.lower().strip())
    if normalized in {"reset-now", "reset now", "now", "resets now"}:
        return 0.0
    total = 0.0
    day = re.search(r"(\d+(?:\.\d+)?)\s*days?", normalized)
    hour = re.search(r"(\d+(?:\.\d+)?)\s*hours?", normalized)
    minute = re.search(r"(\d+(?:\.\d+)?)\s*minutes?", normalized)
    second = re.search(r"(\d+(?:\.\d+)?)\s*seconds?", normalized)
    has = bool(day or hour or minute or second)
    if day:
        total += float(day.group(1)) * 86400
    if hour:
        total += float(hour.group(1)) * 3600
    if minute:
        total += float(minute.group(1)) * 60
    if second:
        total += float(second.group(1))
    return total if has else None


def parse_data_slot_format(html: str) -> dict[WindowKey, ScrapedWindow]:
    result: dict[WindowKey, ScrapedWindow] = {}
    items = re.split(r'data-slot="usage-item"', html)
    for content in items[1:]:
        label_m = re.search(r'data-slot="usage-label">([^<]+)<', content)
        if not label_m:
            continue
        label = label_m.group(1).strip().lower()
        usage_m = re.search(r'data-slot="usage-value">[^0-9]*(\d+(?:\.\d+)?)', content)
        if not usage_m:
            continue
        usage_percent = float(usage_m.group(1))
        reset_m = re.search(
            r'data-slot="(reset-time|reset-now)">([\s\S]*?)</span>', content
        )
        if not reset_m:
            continue
        raw = (
            reset_m.group(2)
            .replace("<!--$", "")
            .replace("-->", "")
            .strip()
        )
        raw = re.sub(r"(?i)Resets?\s*in\s*", "", raw).strip()
        reset_in_sec = (
            0.0 if reset_m.group(1) == "reset-now" else parse_human_readable_time(raw)
        )
        if reset_in_sec is None or usage_percent != usage_percent:
            continue
        window: Optional[WindowKey] = None
        if "rolling" in label:
            window = "rolling"
        elif "weekly" in label:
            window = "weekly"
        elif "monthly" in label:
            window = "monthly"
        if window:
            result[window] = ScrapedWindow(
                usage_percent=usage_percent, reset_in_sec=float(reset_in_sec)
            )
    return result


def parse_dashboard_html(html: str) -> ScrapeResult:
    windows: dict[WindowKey, ScrapedWindow] = {}
    for key in WINDOW_ORDER:
        re_pct, re_reset = _WINDOW_RES[key]
        parsed = parse_window_usage(html, re_pct, re_reset)
        if parsed:
            windows[key] = parsed
    if not windows:
        windows = parse_data_slot_format(html)
    if not windows:
        return ScrapeErr(
            error=(
                "Could not parse any known OpenCode Go dashboard usage windows "
                "(rollingUsage, weeklyUsage, monthlyUsage)"
            )
        )
    return ScrapeOk(windows=windows)


def _sanitize(text: str, max_length: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return (cleaned or "unknown")[:max_length]


def normalize_windows(
    scraped: dict[WindowKey, ScrapedWindow],
    *,
    now_ms: Optional[float] = None,
) -> dict[WindowKey, WindowUsage]:
    now = now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp() * 1000
    out: dict[WindowKey, WindowUsage] = {}
    for key, win in scraped.items():
        usage = max(0.0, win.usage_percent)
        reset = max(0.0, win.reset_in_sec)
        reset_at = datetime.fromtimestamp(
            (now / 1000.0) + reset, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        out[key] = WindowUsage(
            usage_percent=usage,
            reset_in_sec=reset,
            percent_remaining=100.0 - usage,
            reset_at=reset_at,
        )
    return out


FetchFn = Callable[..., object]


def query_opencode_go_quota(
    workspace_id: str,
    auth_cookie: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    opener: Optional[FetchFn] = None,
) -> ScrapeResult:
    url = f"{DASHBOARD_URL_PREFIX}{urllib.request.quote(workspace_id, safe='')}{DASHBOARD_URL_SUFFIX}"
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
            if isinstance(body, bytes):
                text = body.decode("utf-8", errors="replace")
            else:
                text = str(body)
            if int(status) < 200 or int(status) >= 300:
                return ScrapeErr(
                    error=f"OpenCode Go dashboard error {status}: {_sanitize(text)}"
                )
            return parse_dashboard_html(text)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc.reason)
        return ScrapeErr(
            error=f"OpenCode Go dashboard error {exc.code}: {_sanitize(body)}"
        )
    except Exception as exc:  # noqa: BLE001 — surface any transport failure
        return ScrapeErr(error=_sanitize(str(exc)))
