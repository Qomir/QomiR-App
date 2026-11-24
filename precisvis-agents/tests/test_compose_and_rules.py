from datetime import datetime, timezone

from PIL import Image

from agents.analytics import compute_sales_metrics
from core.compose import compose
from tools.supplier import DSersMonitor


def _scene():
    return Image.new("RGB", (1200, 1200), (180, 150, 110))


def test_compose_resolutions_and_9x16_safe_zone(make_ctx):
    ctx = make_ctx()
    safe = ctx.cfg.get("creatives.safe_zone_9x16")
    for f in ctx.cfg.get("creatives.formats"):
        img, lay = compose(_scene(), width=f["width"], height=f["height"], ratio=f["ratio"], headline="Cette vis fait 1 mm.",
                           brand=ctx.brand, root=ctx.cfg.root, safe_zone=safe)
        assert img.size == (f["width"], f["height"])
        # logo en bas à droite
        assert lay.logo_box[2] > f["width"] * 0.9 and lay.logo_box[0] > f["width"] / 2
        if f["ratio"] == "9:16":
            top, bottom = f["height"] * safe["top"], f["height"] * (1 - safe["bottom"])
            for box in (lay.text_box, lay.logo_box):
                assert box[1] >= top and box[3] <= bottom, (f, box)


def test_compose_long_headline_wraps(make_ctx):
    ctx = make_ctx()
    img, lay = compose(_scene(), width=1080, height=1080, ratio="1:1", headline="Ta manette grince encore ? Ouvre-la toi-même.",
                       brand=ctx.brand, root=ctx.cfg.root, safe_zone={})
    assert lay.text_box[2] <= 1080


def test_margin_calculation(cfg):
    orders = [{"total": 49.9, "refunded": 0, "financial_status": "PAID", "lines": [{"qty": 1, "unit_cost": None}], "utm_source": "tiktok"},
              {"total": 99.8, "refunded": 0, "financial_status": "PAID", "lines": [{"qty": 2, "unit_cost": 30.0}], "utm_source": "x"},
              {"total": 49.9, "cancelled": True, "financial_status": "PAID", "lines": [{"qty": 1, "unit_cost": None}]}]
    m = compute_sales_metrics(orders, cfg)
    a = cfg["analytics"]
    expected_fees = (49.9 + 99.8) * (a["payment_fee_pct"] + a["shopify_fee_pct"]) + 2 * a["payment_fee_fixed_eur"]
    expected = 149.7 - (a["product_cost_eur"] + 60) - 2 * a["shipping_cost_eur"] - expected_fees
    assert m["orders"] == 2 and m["revenue"] == 149.7
    assert abs(m["margin"] - round(expected, 2)) < 0.011
    assert m["ad_spend_total"] == 0 and m["roas"] is None
    assert m["by_source"]["tiktok"]["orders"] == 1 and m["by_source"]["autre"]["orders"] == 1


def test_dsers_monitor_alerts():
    now = datetime(2026, 11, 24, 7, tzinfo=timezone.utc)
    mon = DSersMonitor(24, 5, 10)
    def o(name, created, f=None):
        return {"name": name, "created_at": created, "financial_status": "PAID", "fulfillments": f or []}
    res = mon.analyse([
        o("#1", "2026-11-24T01:00:00Z"),
        o("#2", "2026-11-22T01:00:00Z"),
        o("#3", "2026-11-10T01:00:00Z", [{"created_at": "2026-11-11T00:00:00Z", "tracking": ["LP1"], "delivered_at": None}]),
        o("#4", "2026-11-15T01:00:00Z", [{"created_at": "2026-11-16T00:00:00Z", "tracking": [], "delivered_at": None}]),
        o("#5", "2026-11-01T01:00:00Z", [{"created_at": "2026-11-02T00:00:00Z", "tracking": ["LP5"], "delivered_at": "2026-11-12T00:00:00Z"}]),
    ], now=now)
    assert [x["order"] for x in res["not_transmitted"]] == ["#2"]
    assert [x["order"] for x in res["stuck"]] == ["#3"]
    assert [x["order"] for x in res["no_tracking"]] == ["#4"]
    assert {x["order"] for x in res["ok"]} == {"#1", "#5"}
