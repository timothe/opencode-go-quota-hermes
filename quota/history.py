"""Append-only local usage history for trend advice."""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .types import WINDOW_ORDER, QuotaSnapshot, WindowKey

DEFAULT_HISTORY_PATH = (
    Path.home() / ".hermes" / "cache" / "opencode-go-quota-history.jsonl"
)
RETENTION_DAYS = 90
DEDUP_WINDOW_S = 3600.0
DEDUP_USAGE_EPS = 0.5
TREND_MIN_SAMPLES = 3
TREND_MIN_SPAN_S = 24 * 3600
CYCLE_DROP_PP = 15.0  # usage drop suggesting a window reset


@dataclass(frozen=True)
class HistorySample:
    ts: datetime
    windows: dict[WindowKey, dict[str, float]]  # u, left, reset
    balance_usd: Optional[float] = None
    use_balance: Optional[bool] = None

    def to_line(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "ts": self.ts.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "w": {
                k: {
                    "u": v["u"],
                    "left": v["left"],
                    "reset": v["reset"],
                }
                for k, v in self.windows.items()
            },
        }
        if self.balance_usd is not None or self.use_balance is not None:
            row["b"] = {
                "usd": self.balance_usd if self.balance_usd is not None else 0.0,
                "use": bool(self.use_balance) if self.use_balance is not None else False,
            }
        return row


def _parse_ts(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def snapshot_to_sample(
    snapshot: QuotaSnapshot,
    *,
    now: Optional[datetime] = None,
) -> HistorySample:
    now = now or datetime.now(timezone.utc)
    windows: dict[WindowKey, dict[str, float]] = {}
    for key in WINDOW_ORDER:
        usage = snapshot.windows.get(key)
        if usage is None:
            continue
        windows[key] = {
            "u": usage.usage_percent,
            "left": usage.percent_remaining,
            "reset": usage.reset_in_sec,
        }
    bal: Optional[float] = None
    use: Optional[bool] = None
    if snapshot.billing and not snapshot.billing.error:
        bal = snapshot.billing.balance_usd
        use = snapshot.billing.use_balance
    return HistorySample(ts=now, windows=windows, balance_usd=bal, use_balance=use)


def _load_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _row_to_sample(row: dict[str, Any]) -> Optional[HistorySample]:
    ts = _parse_ts(str(row.get("ts") or ""))
    if ts is None:
        return None
    raw_w = row.get("w") or {}
    windows: dict[WindowKey, dict[str, float]] = {}
    for key in WINDOW_ORDER:
        entry = raw_w.get(key)
        if not isinstance(entry, dict):
            continue
        try:
            windows[key] = {
                "u": float(entry["u"]),
                "left": float(entry.get("left", 100.0 - float(entry["u"]))),
                "reset": float(entry.get("reset", 0.0)),
            }
        except (KeyError, TypeError, ValueError):
            continue
    bal = None
    use = None
    b = row.get("b")
    if isinstance(b, dict):
        try:
            bal = float(b.get("usd", 0.0))
        except (TypeError, ValueError):
            bal = None
        if "use" in b:
            use = bool(b["use"])
    return HistorySample(ts=ts, windows=windows, balance_usd=bal, use_balance=use)


def load_samples(path: Optional[Path] = None) -> list[HistorySample]:
    p = path or DEFAULT_HISTORY_PATH
    out: list[HistorySample] = []
    for row in _load_lines(p):
        sample = _row_to_sample(row)
        if sample is not None:
            out.append(sample)
    return out


def _should_skip_dedup(prev: HistorySample, cur: HistorySample) -> bool:
    dt = abs((cur.ts - prev.ts).total_seconds())
    if dt >= DEDUP_WINDOW_S:
        return False
    for key in WINDOW_ORDER:
        a = prev.windows.get(key)
        b = cur.windows.get(key)
        if a is None and b is None:
            continue
        if a is None or b is None:
            return False
        if abs(a["u"] - b["u"]) > DEDUP_USAGE_EPS:
            return False
    return True


def _trim(rows: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_ts(str(row.get("ts") or ""))
        if ts is None:
            continue
        if ts >= cutoff:
            kept.append(row)
    return kept


def append_sample(
    sample: HistorySample,
    *,
    path: Optional[Path] = None,
) -> bool:
    """Append sample if not a near-duplicate. Returns True if written."""
    p = path or DEFAULT_HISTORY_PATH
    existing = _load_lines(p)
    samples = [s for s in (_row_to_sample(r) for r in existing) if s is not None]
    if samples and _should_skip_dedup(samples[-1], sample):
        return False

    rows = _trim(existing + [sample.to_line()], now=sample.ts)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    except OSError:
        return False
    return True


def record_snapshot(
    snapshot: QuotaSnapshot,
    *,
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> bool:
    if snapshot.status in {"error", "incomplete"} or not snapshot.windows:
        return False
    return append_sample(snapshot_to_sample(snapshot, now=now), path=path)


def _cycle_break(prev_u: float, cur_u: float, prev_reset: float, cur_reset: float) -> bool:
    # Usage dropped a lot while reset jumped up → new window cycle.
    return (prev_u - cur_u) >= CYCLE_DROP_PP and cur_reset > prev_reset + 3600


def _burn_rates(
    points: list[tuple[datetime, float]],
) -> list[float]:
    """Usage percent per day between consecutive points."""
    rates: list[float] = []
    for i in range(1, len(points)):
        t0, u0 = points[i - 1]
        t1, u1 = points[i]
        dt_days = (t1 - t0).total_seconds() / 86400.0
        if dt_days <= 0:
            continue
        rates.append((u1 - u0) / dt_days)
    return rates


def format_trend_advice(
    snapshot: QuotaSnapshot,
    *,
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    """Compare current burn to recent history; empty if not enough data."""
    now = now or datetime.now(timezone.utc)
    samples = load_samples(path)
    if len(samples) < TREND_MIN_SAMPLES:
        return ""

    bits: list[str] = []
    for key in WINDOW_ORDER:
        usage = snapshot.windows.get(key)
        if usage is None:
            continue
        points: list[tuple[datetime, float, float]] = []
        for s in samples:
            w = s.windows.get(key)
            if w is None:
                continue
            points.append((s.ts, w["u"], w["reset"]))
        # Add current as tip.
        points.append((now, usage.usage_percent, usage.reset_in_sec))

        # Keep only current cycle (drop older after a reset break).
        cycle: list[tuple[datetime, float]] = []
        for i, (ts, u, reset) in enumerate(points):
            if cycle and i > 0:
                prev_ts, prev_u = cycle[-1]
                prev_reset = points[i - 1][2]
                if _cycle_break(prev_u, u, prev_reset, reset):
                    cycle = []
            cycle.append((ts, u))

        if len(cycle) < TREND_MIN_SAMPLES:
            continue
        span = (cycle[-1][0] - cycle[0][0]).total_seconds()
        if span < TREND_MIN_SPAN_S:
            continue

        rates = _burn_rates(cycle)
        if len(rates) < 2:
            continue
        recent = rates[-1]
        prior = rates[:-1]
        med = statistics.median(prior)
        # Need a meaningful prior burn to compare.
        if abs(med) < 0.5 and abs(recent) < 0.5:
            continue
        if med <= 0 and recent <= 0:
            continue
        if recent > med * 1.35 and recent - med >= 1.0:
            label = {"rolling": "5-hour", "weekly": "weekly", "monthly": "monthly"}[key]
            bits.append(
                f"Recent {label} burn is faster than your recent average "
                f"(~{recent:.1f}%/day vs ~{med:.1f}%/day)"
            )
        elif recent < med * 0.65 and med - recent >= 1.0:
            label = {"rolling": "5-hour", "weekly": "weekly", "monthly": "monthly"}[key]
            bits.append(
                f"Recent {label} burn is slower than your recent average "
                f"(~{recent:.1f}%/day vs ~{med:.1f}%/day)"
            )

    if not bits:
        return ""
    return bits[0] + ("." if not bits[0].endswith(".") else "")

