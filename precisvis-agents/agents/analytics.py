"""Agent Analytics.

Calcule chaque jour (calcul déterministe, sans IA) : CA, commandes, panier moyen, dépense pub
(0 € : organique), ventes attribuées par plateforme (UTM), marge nette estimée, coût du système,
et les statistiques organiques (vues, likes, commentaires, partages, enregistrements).
Classe les créas et renvoie les gagnantes à l'agent Visuels pour qu'il crée des variantes.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any

from .base import AgentReport, BaseAgent

PLATFORMS = ("facebook", "instagram", "tiktok")


def compute_sales_metrics(orders: list[dict[str, Any]], cfg) -> dict[str, Any]:
    a = cfg.get("analytics", {})
    valid = [o for o in orders if not o.get("cancelled") and o.get("financial_status") in ("PAID", "PARTIALLY_REFUNDED", "REFUNDED")]
    revenue = sum(o["total"] - o.get("refunded", 0) for o in valid)
    units = sum(li["qty"] for o in valid for li in o["lines"])
    cogs = sum((li["unit_cost"] if li.get("unit_cost") is not None else a.get("product_cost_eur", 0)) * li["qty"]
               for o in valid for li in o["lines"])
    shipping = a.get("shipping_cost_eur", 0) * len(valid)
    fees = sum(o["total"] * (a.get("payment_fee_pct", 0) + a.get("shopify_fee_pct", 0)) + a.get("payment_fee_fixed_eur", 0)
               for o in valid)
    ad_spend = {p: 0.0 for p in PLATFORMS}    # publication organique : aucune dépense publicitaire
    margin = revenue - cogs - shipping - fees - sum(ad_spend.values())
    by_source: dict[str, dict[str, float]] = {}
    for o in valid:
        src = o.get("utm_source") if o.get("utm_source") in PLATFORMS else "autre"
        s = by_source.setdefault(src, {"orders": 0, "revenue": 0.0})
        s["orders"] += 1
        s["revenue"] += o["total"]
    n = len(valid)
    return {
        "orders": n, "units": units, "revenue": round(revenue, 2), "aov": round(revenue / n, 2) if n else 0.0,
        "cogs": round(cogs, 2), "shipping": round(shipping, 2), "fees": round(fees, 2),
        "ad_spend": ad_spend, "ad_spend_total": 0.0, "roas": None, "cpa": None,
        "margin": round(margin, 2), "margin_pct": round(margin / revenue * 100, 1) if revenue else 0.0,
        "by_source": {k: {"orders": v["orders"], "revenue": round(v["revenue"], 2)} for k, v in by_source.items()},
        "sales_by_creative": _sales_by_creative(valid),
    }


def _sales_by_creative(orders: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for o in orders:
        c = o.get("utm_content")
        if c:
            out[c] = out.get(c, 0) + 1
    return out


def _n(v: int) -> str:
    return f"{v:,}".replace(",", "\u202f")


def engagement(m: dict[str, Any]) -> float:
    views = m.get("views") or m.get("reach") or 0
    inter = sum(m.get(k, 0) or 0 for k in ("likes", "comments", "shares", "saves"))
    return inter / views if views else 0.0


class AnalyticsAgent(BaseAgent):
    name = "analytics"
    label = "Analytics"

    def __init__(self, ctx, target_day: str | None = None):
        super().__init__(ctx)
        self.target_day = target_day or ctx.day

    async def run(self) -> AgentReport:
        ctx = self.ctx
        day = self.target_day
        tz = ctx.tz
        start = datetime.combine(datetime.fromisoformat(day).date(), time(0), tz)
        end = start + timedelta(days=1)
        orders = [o for o in ctx.tools.shopify.orders_since(start) if datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")) < end]
        sales = compute_sales_metrics(orders, ctx.cfg)
        organic = self._refresh_organic()
        api_cost = ctx.db.cost_total(day)
        payload = {**sales, "organic": organic, "api_cost": round(api_cost, 2),
                   "net_after_system": round(sales["margin"] - api_cost, 2),
                   "posts_published": ctx.db.one("SELECT COUNT(*) n FROM posts WHERE day = ? AND status = 'published'", [day])["n"]}
        ctx.db.insert("metrics_daily", {"day": day, "payload": json.dumps(payload, ensure_ascii=False), "dry_run": int(ctx.dry_run)})
        self.action("metrics_computed", {"day": day, "orders": sales["orders"], "revenue": sales["revenue"]})

        winners = self._rank_creatives(sales["sales_by_creative"])
        if winners:
            ctx.db.publish_insight(day=ctx.day, source=self.name, topic="winners",
                                   payload=winners[: int(ctx.cfg.get("analytics.winners_to_variate", 2))])
        label = "aujourd'hui" if day == ctx.day else f"le {day[8:10]}/{day[5:7]}"
        self.bullet(f"{label.capitalize()} : {sales['orders']} commande(s), {sales['revenue']:.2f} € de CA, "
                    f"panier moyen {sales['aov']:.2f} €, marge estimée {sales['margin']:.2f} € ({sales['margin_pct']} %).")
        self.bullet(f"Organique (7 derniers jours) : {_n(organic['total']['views'])} vues, {_n(organic['total']['interactions'])} "
                    f"interactions, taux d'engagement {organic['total']['engagement_pct']} %.")
        if sales["by_source"]:
            src = ", ".join(f"{k} {v['orders']}" for k, v in sorted(sales["by_source"].items(), key=lambda kv: -kv[1]["orders"]))
            self.bullet(f"Ventes par source (UTM) : {src}.")
        if winners:
            self.bullet("Créas gagnantes renvoyées aux Visuels : " + ", ".join(f"{w['id']} ({w['headline']})" for w in winners[:2]) + ".")
        self.report.data = payload
        return self.report

    def _refresh_organic(self) -> dict[str, Any]:
        ctx = self.ctx
        since = (datetime.fromisoformat(self.target_day) - timedelta(days=7)).date().isoformat()
        posts = ctx.db.query("SELECT * FROM posts WHERE status = 'published' AND day >= ?", [since])
        tiktok_ids = [p["external_id"] for p in posts if p["platform"] == "tiktok"]
        tt = {}
        if tiktok_ids:
            try:
                tt = ctx.tools.tiktok.video_metrics(tiktok_ids)
            except Exception as exc:
                self.action("tiktok_metrics", status="error", error=str(exc))
        per = {p: {"posts": 0, "views": 0, "interactions": 0} for p in PLATFORMS}
        for p in posts:
            try:
                if p["platform"] == "facebook":
                    m = ctx.tools.meta.facebook_post_metrics(p["external_id"])
                elif p["platform"] == "instagram":
                    m = ctx.tools.meta.instagram_media_metrics(p["external_id"])
                else:
                    m = tt.get(p["external_id"], {})
            except Exception as exc:
                self.action("post_metrics", {"post": p["id"]}, status="error", error=str(exc))
                continue
            ctx.db.update("posts", "id", p["id"], {"metrics": m, "metrics_updated": ctx.now().isoformat(timespec="seconds")})
            agg = per[p["platform"]]
            agg["posts"] += 1
            agg["views"] += int(m.get("views") or m.get("reach") or 0)
            agg["interactions"] += sum(int(m.get(k, 0) or 0) for k in ("likes", "comments", "shares", "saves"))
        views = sum(v["views"] for v in per.values())
        inter = sum(v["interactions"] for v in per.values())
        return {"platforms": per, "total": {"views": views, "interactions": inter,
                                            "engagement_pct": round(inter / views * 100, 2) if views else 0.0}}

    def _rank_creatives(self, sales_by_creative: dict[str, int]) -> list[dict[str, Any]]:
        rows = self.ctx.db.query("""SELECT c.id, c.concept, c.angle, c.headline, c.kind, p.metrics FROM posts p
                                    JOIN creatives c ON c.id = p.creative_id
                                    WHERE p.status = 'published' AND p.metrics IS NOT NULL""")
        scores: dict[str, dict[str, Any]] = {}
        for r in rows:
            m = json.loads(r["metrics"] or "{}")
            s = scores.setdefault(r["id"], {"id": r["id"], "concept": r["concept"], "angle": r["angle"], "headline": r["headline"],
                                            "kind": r["kind"], "views": 0, "eng": []})
            s["views"] += int(m.get("views") or m.get("reach") or 0)
            s["eng"].append(engagement(m))
        ranked = []
        for s in scores.values():
            eng = sum(s["eng"]) / len(s["eng"]) if s["eng"] else 0
            sales = sales_by_creative.get(s["id"], 0)
            ranked.append({**{k: v for k, v in s.items() if k != "eng"}, "engagement_pct": round(eng * 100, 2), "sales": sales,
                           "score": round(eng * 100 + sales * 5 + min(s["views"], 50000) / 10000, 2)})
        ranked.sort(key=lambda x: -x["score"])
        self.ctx.db.kv_set(f"creative_ranking:{self.target_day}", ranked[:10])
        return ranked
