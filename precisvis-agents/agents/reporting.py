"""Agent Reporting — e-mail HTML quotidien à 20h00 (Europe/Paris) + alerte immédiate en cas d'échec."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tools.email import InlineImage

from .base import AgentReport, BaseAgent

AGENT_ORDER = [
    ("product_research", "Veille produit & concurrence"), ("catalog", "Catalogue Shopify"), ("ad_visuals", "Visuels IA"),
    ("ad_copy", "Copywriting"), ("social_publisher", "Publication organique"), ("orders", "Commandes (DSers)"),
    ("customer_service", "SAV client"), ("analytics", "Analytics"),
]
TODO_LABELS = {"remboursement": "Remboursements à valider", "litige": "Litiges et réclamations", "erreur": "Erreurs bloquantes",
               "produit_brouillon": "Produits proposés en brouillon", "validation": "Validations demandées", "info": "À relire"}

SUMMARY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines"],
                  "properties": {"lines": {"type": "array", "items": {"type": "string"}}}}


def fmt_eur(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",")


def delta(cur: float | None, ref: float | None) -> str:
    if cur is None or ref in (None, 0):
        return "—"
    pct = (cur - ref) / ref * 100
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "=")
    return f"{arrow} {abs(pct):.0f} %"


class ReportingAgent(BaseAgent):
    name = "reporting"
    label = "Reporting"

    async def run(self) -> AgentReport:
        ctx = self.ctx
        data = self.collect()
        data["summary"] = await self._summary(data)
        subject = self.subject(data)
        html, images = self.render(data)
        to = ctx.cfg.get("reporting.to")
        if ctx.dry_run and not ctx.send_test_email:
            subject = "[SIMULATION] " + subject
        elif ctx.dry_run:
            subject = "[TEST — SIMULATION] " + subject
        ref = ctx.tools.report_sender.send(to, subject, html, images)
        self.action("report_sent", {"to": to, "subject": subject, "ref": ref})
        self.bullet(f"Bilan envoyé à {to}.")
        self.report.data = {"subject": subject, "ref": ref, "html": html}
        return self.report

    # ------------------------------------------------------------------------------------
    def metrics(self, day: str) -> dict[str, Any] | None:
        row = self.ctx.db.one("SELECT payload FROM metrics_daily WHERE day = ?", [day])
        return json.loads(row["payload"]) if row else None

    def collect(self) -> dict[str, Any]:
        ctx = self.ctx
        today = self.metrics(ctx.day) or {}
        yday = self.metrics(ctx.day_offset(-1)) or {}
        last7 = [m for m in (self.metrics(ctx.day_offset(-k)) for k in range(1, 8)) if m]

        def avg(key: str) -> float | None:
            vals = [m.get(key) for m in last7 if m.get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        def views(m: dict[str, Any]) -> int:
            return int((m.get("organic") or {}).get("total", {}).get("views", 0)) if m else 0

        rows = []
        for label, key, money in [("Chiffre d'affaires", "revenue", True), ("Commandes", "orders", False),
                                  ("Panier moyen", "aov", True), ("Marge nette estimée", "margin", True),
                                  ("Dépense pub", "ad_spend_total", True), ("Coût du système (IA)", "api_cost", True)]:
            cur, prev, mean = today.get(key), yday.get(key), avg(key)
            f = fmt_eur if money else (lambda v: "—" if v is None else f"{v:g}" if isinstance(v, (int, float)) else str(v))
            rows.append({"label": label, "today": f(cur), "yday": f(prev), "avg7": f(mean),
                         "d1": delta(cur, prev), "d7": delta(cur, mean)})
        v7 = [views(m) for m in last7]
        rows.append({"label": "Vues organiques (7 j glissants)", "today": f"{views(today):,}".replace(",", " "),
                     "yday": f"{views(yday):,}".replace(",", " ") if yday else "—",
                     "avg7": f"{sum(v7) / len(v7):,.0f}".replace(",", " ") if v7 else "—",
                     "d1": delta(views(today), views(yday) if yday else None), "d7": delta(views(today), sum(v7) / len(v7) if v7 else None)})
        rows.append({"label": "ROAS", "today": "n/a (organique)", "yday": "—", "avg7": "—", "d1": "", "d7": ""})

        todos: dict[str, list[dict[str, Any]]] = {}
        for t in ctx.db.open_todos():
            todos.setdefault(TODO_LABELS.get(t["category"], t["category"]), []).append(t)

        runs = ctx.db.query("SELECT * FROM agent_runs WHERE day = ? ORDER BY id", [ctx.day])
        agents = []
        for key, label in AGENT_ORDER:
            mine = [r for r in runs if r["agent"] == key]
            bullets: list[str] = []
            status = "non lancé"
            for r in mine:
                bullets += json.loads(r["bullets"] or "[]")
                status = r["status"]
                if r["status"] == "failed":
                    bullets.append(f"⚠ Échec après {r['attempts']} tentative(s) : {r['error']}")
            agents.append({"label": label, "status": status, "bullets": bullets[:6] or ["Aucune action aujourd'hui."]})

        creatives = ctx.db.query("SELECT * FROM creatives WHERE day = ? ORDER BY status, score DESC", [ctx.day])
        thumbs_dir = ctx.cfg.output_dir / "creatives" / ctx.day / "_thumbs"
        thumbs = []
        for c in creatives:
            p = thumbs_dir / f"{c['id']}.jpg"
            if c["status"] == "ok" and p.exists():
                thumbs.append({"id": c["id"], "path": p, "headline": c["headline"], "score": c["score"], "kind": c["kind"]})
        thumbs = thumbs[: int(ctx.cfg.get("reporting.thumbnails_max", 8))]
        ranking = ctx.db.kv_get(f"creative_ranking:{ctx.day}", []) or ctx.db.kv_get(f"creative_ranking:{ctx.day_offset(-1)}", []) or []
        best_posts = []
        for r in ranking[:3]:
            p = ctx.db.one("SELECT permalink, platform FROM posts WHERE creative_id = ? AND status = 'published' ORDER BY id DESC", [r["id"]])
            best_posts.append({**r, "permalink": (p or {}).get("permalink", ""), "platform": (p or {}).get("platform", "")})

        posts = ctx.db.query("SELECT * FROM posts WHERE day = ? ORDER BY scheduled_at, platform", [ctx.day])
        costs = ctx.db.costs_by_kind(ctx.day)
        cost_rows = {"Claude (IA texte et vision)": sum(v for k, v in costs.items() if k.endswith(":llm")),
                     "Génération d'images": sum(v for k, v in costs.items() if k.endswith(":image")),
                     "Génération de vidéos": sum(v for k, v in costs.items() if k.endswith(":video"))}
        failures = [r for r in runs if r["status"] == "failed"]
        return {"day": ctx.day, "today": today, "yday": yday, "rows": rows, "todos": todos, "agents": agents, "thumbs": thumbs,
                "best_posts": best_posts, "posts": posts, "cost_rows": cost_rows, "cost_total": sum(cost_rows.values()),
                "cap": ctx.guard.daily_cap, "month_total": ctx.db.cost_total(ctx.day[:7]), "month_cap": ctx.guard.monthly_cap,
                "failures": failures, "plan": self.plan_tomorrow(), "dry_run": ctx.dry_run,
                "kill_switch": ctx.cfg.kill_switch, "rejected": [c for c in creatives if c["status"] == "rejected"]}

    def plan_tomorrow(self) -> list[str]:
        ctx, cfg = self.ctx, self.ctx.cfg
        tomorrow = date.fromisoformat(ctx.day) + timedelta(days=1)
        if cfg.kill_switch:
            return ["Kill switch actif : aucun agent ne travaillera tant que kill_switch n'est pas remis à false."]
        types = cfg.get("creatives.creative_types", [])
        offset = tomorrow.toordinal() % len(types) if types else 0
        plan = [types[(offset + k) % len(types)] for k in range(min(3, len(types)))]
        winners = ctx.db.latest_insight("winners") or []
        lines = [
            f"{cfg.get('schedule.morning')} — veille concurrentielle, contrôle du catalogue, "
            f"{cfg.get('creatives.daily_images')} images ({', '.join(plan)}…) + {cfg.get('creatives.daily_videos')} vidéos.",
            (f"Variantes des créas gagnantes : {', '.join(w['id'] for w in winners[:2])}." if winners else
             "Pas encore assez de données pour désigner des gagnantes : on continue de tester des angles variés."),
            f"Publications organiques aux créneaux {', '.join(cfg.get('schedule.publish_slots', []))}.",
            "Contrôle des commandes DSers, réponses SAV, puis bilan à 20h00.",
        ]
        if tomorrow.weekday() == int(cfg.get("schedule.research_weekday", 0)):
            lines.insert(1, "Lundi : proposition de 1 à 3 produits complémentaires (en brouillon).")
        return lines

    async def _summary(self, data: dict[str, Any]) -> list[str]:
        t = data["today"]
        n_todo = sum(len(v) for v in data["todos"].values())
        fallback = [
            f"{t.get('orders', 0)} vente(s) pour {fmt_eur(t.get('revenue', 0))} de CA, marge estimée {fmt_eur(t.get('margin', 0))} "
            f"({delta(t.get('revenue'), data['yday'].get('revenue'))} vs hier).",
            f"{len(data['thumbs'])} créa(s) validée(s), {sum(1 for p in data['posts'] if p['status'] == 'published')} publication(s) "
            f"organique(s) en ligne, {(t.get('organic') or {}).get('total', {}).get('views', 0):,} vues sur 7 jours.".replace(",", "\u202f")
            .replace("\u202f ", ", "),
            (f"{n_todo} point(s) à traiter par vous" + (f", dont {len(data['failures'])} agent(s) en échec." if data["failures"] else ".")
             if n_todo or data["failures"] else "Rien à traiter de votre côté aujourd'hui."),
        ]
        if self.ctx.dry_run:
            return fallback
        try:
            res = await self.ctx.llm.ask(self.name, "Voici les faits de la journée :\n" + "\n".join(fallback) +
                                         "\nRéécris-les en exactement 3 lignes courtes, factuelles, sans rien inventer.",
                                         SUMMARY_SCHEMA, mock=lambda: {"lines": fallback}, estimate_eur=0.03, effort="low")
            return res["lines"][:3] or fallback
        except Exception:
            return fallback

    def subject(self, data: dict[str, Any]) -> str:
        t = data["today"]
        d = date.fromisoformat(data["day"])
        views = (t.get("organic") or {}).get("total", {}).get("views", 0)
        ca = f"{t.get('revenue', 0):,.0f}".replace(",", " ")
        return (f"PrecisVis — Bilan du {d:%d/%m} : {t.get('orders', 0)} ventes · {ca} € CA · "
                f"ROAS n/a (organique) · {views:,} vues".replace(",", " "))

    def render(self, data: dict[str, Any]) -> tuple[str, list[InlineImage]]:
        env = Environment(loader=FileSystemLoader(str(self.ctx.cfg.root / "templates")), autoescape=select_autoescape(["html"]))
        env.filters["eur"] = fmt_eur
        images = [InlineImage(cid=f"thumb-{t['id']}", path=Path(t["path"])) for t in data["thumbs"]]
        html = env.get_template("daily_report.html").render(**data, brand=self.ctx.brand)
        return html, images


async def send_failure_alert(ctx, error: str) -> None:
    """E-mail court envoyé immédiatement si une exécution échoue complètement."""
    subject = f"⚠ PrecisVis — échec de l'exécution du {ctx.day} ({ctx.phase})"
    if ctx.dry_run:
        subject = "[SIMULATION] " + subject
    html = (f"<div style='font-family:Arial,sans-serif'><h2 style='color:#b3261e'>Exécution {ctx.phase} en échec</h2>"
            f"<p><b>Date :</b> {ctx.day} — <b>run :</b> {ctx.run_id}</p><pre style='background:#f4f1ea;padding:12px;white-space:pre-wrap'>"
            f"{error[:3000]}</pre><p>Les agents reprendront à la prochaine exécution planifiée. Pour tout arrêter : "
            f"<code>kill_switch: true</code> dans config.yaml.</p></div>")
    try:
        ctx.tools.report_sender.send(ctx.cfg.get("reporting.to"), subject, html)
    except Exception:  # pragma: no cover - dernier recours : le journal GitHub Actions
        import logging
        logging.getLogger("precisvis").exception("Impossible d'envoyer l'alerte")
