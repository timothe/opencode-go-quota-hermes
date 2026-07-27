from __future__ import annotations

from quota.check import classify_windows, fetch_snapshot
from quota.types import WindowUsage
from tests.helpers import build_ssr_html


def _win(remaining: float, reset_in: float = 100.0) -> WindowUsage:
    return WindowUsage(
        usage_percent=100.0 - remaining,
        reset_in_sec=reset_in,
        percent_remaining=remaining,
        reset_at=f"reset-{reset_in}",
    )


def test_classify_ok():
    snap = classify_windows(
        {"rolling": _win(50), "weekly": _win(80), "monthly": _win(90)},
        warn=20,
        critical=5,
    )
    assert snap.status == "ok"
    assert snap.breached == []


def test_classify_warn():
    snap = classify_windows(
        {"rolling": _win(15), "weekly": _win(80)},
        warn=20,
        critical=5,
    )
    assert snap.status == "warn"
    assert snap.breached == ["rolling"]


def test_classify_critical_wins():
    snap = classify_windows(
        {"rolling": _win(15), "weekly": _win(3, reset_in=50), "monthly": _win(2, reset_in=10)},
        warn=20,
        critical=5,
    )
    assert snap.status == "critical"
    assert snap.breached == ["rolling", "weekly", "monthly"]
    assert snap.soonest_reset_at == "reset-10"


def test_classify_empty_incomplete():
    snap = classify_windows({}, warn=20, critical=5)
    assert snap.status == "incomplete"


def test_fetch_snapshot_missing_config(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("OPENCODE_GO_AUTH_COOKIE", raising=False)
    snap = fetch_snapshot()
    assert snap.status == "incomplete"


def test_fetch_snapshot_success(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_WORKSPACE_ID", "ws")
    monkeypatch.setenv("OPENCODE_GO_AUTH_COOKIE", "tok")
    html = build_ssr_html({"rolling": (90, 60)})  # 10% remaining → warn at 20

    class Resp:
        status = 200

        def read(self):
            return html.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    snap = fetch_snapshot(
        opener=lambda req, timeout=10: Resp(),
        warn=20,
        critical=5,
        record_history=False,
    )
    assert snap.status == "warn"
    assert "rolling" in snap.windows
    assert snap.billing is not None
    assert snap.billing.error  # go HTML is not a billing page

