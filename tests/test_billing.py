from __future__ import annotations

from pathlib import Path

from quota.billing import extract_billing_object, parse_billing_html


FIXTURE = Path(__file__).parent / "fixtures" / "billing.html"


def test_parse_billing_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    info = parse_billing_html(html)
    assert not info.error
    assert abs(info.balance_usd - 19.9996075) < 1e-6
    assert abs(info.monthly_usage_usd - 0.0003925) < 1e-9
    assert info.monthly_limit_usd == 50.0
    assert info.use_balance is True
    assert info.auto_reload is True
    assert info.reload_amount_usd == 10.0


def test_extract_billing_object_anchors_customer():
    html = FIXTURE.read_text(encoding="utf-8")
    obj = extract_billing_object(html)
    assert obj is not None
    assert 'customerID:"cus_TESTCUSTOMER"' in obj
    assert "useBalance:!0" in obj


def test_parse_billing_missing():
    info = parse_billing_html("<html>login please</html>")
    assert info.error
    assert "no billing" in info.error.lower() or "outdated" in info.error.lower()


def test_parse_use_balance_off():
    html = (
        'window.__SSR={customerID:"cus_X",balance:100000000,monthlyUsage:0,'
        'monthlyLimit:50,reload:!1,lite:$R[1]={useBalance:!1}};'
    )
    info = parse_billing_html(html)
    assert not info.error
    assert abs(info.balance_usd - 1.0) < 1e-9
    assert info.use_balance is False
