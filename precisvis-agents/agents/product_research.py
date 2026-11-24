"""Agent Veille produit & concurrence.

- Analyse les pubs concurrentes actives (Meta Ad Library, lecture seule) et les tendances
  organiques TikTok (recherche web : TikTok Creative Center n'a pas d'API publique).
- Publie les angles qui marchent pour les agents Visuels et Copywriting.
- Le jour configuré (lundi par défaut), propose 1 à 3 produits complémentaires (20–60 € d'achat,
  jamais de beauté), les crée en BROUILLON dans Shopify et les liste dans « À traiter ».
"""
from __future__ import annotations

from typing import Any

from .base import AgentReport, BaseAgent

SEARCH_TERMS = ["tournevis électrique précision", "kit tournevis précision", "outil réparation smartphone",
                "tournevis horlogerie", "outil maquettisme"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["angles", "formats", "products"],
    "properties": {
        "angles": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["angle", "hook", "why", "creative_type"],
                   "properties": {"angle": {"type": "string"}, "hook": {"type": "string"}, "why": {"type": "string"},
                                  "creative_type": {"type": "string", "enum": ["packshot_atelier", "mise_en_situation",
                                                    "avant_apres", "comparatif", "gros_plan_detail"]}}}},
        "formats": {"type": "array", "items": {"type": "string"}},
        "products": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["title", "category", "purchase_price_eur", "suggested_price_eur", "supplier_hint", "why", "description"],
                     "properties": {"title": {"type": "string"}, "category": {"type": "string"},
                                    "purchase_price_eur": {"type": "number"}, "suggested_price_eur": {"type": "number"},
                                    "supplier_hint": {"type": "string"}, "why": {"type": "string"},
                                    "description": {"type": "string"}}}},
    },
}


class ProductResearchAgent(BaseAgent):
    name = "product_research"
    label = "Veille produit & concurrence"
    spends_money = True

    async def run(self) -> AgentReport:
        ctx = self.ctx
        ads: list[dict[str, Any]] = []
        for term in SEARCH_TERMS[:3]:
            try:
                ads += ctx.tools.meta.ad_library_search(term)
            except Exception as exc:  # la bibliothèque publicitaire peut refuser l'accès : on continue
                self.action("ad_library_search", {"term": term}, status="error", error=str(exc))
        self.action("ad_library_search", {"ads_found": len(ads)})

        propose = ctx.date.weekday() == int(ctx.cfg.get("schedule.research_weekday", 0))
        n_products = int(ctx.cfg.get("catalog.max_new_products_per_week", 3)) if propose else 0
        compact = [{"page": a.get("page_name"), "texte": (a.get("ad_creative_bodies") or [""])[0][:300],
                    "titre": (a.get("ad_creative_link_titles") or [""])[0], "depuis": a.get("ad_delivery_start_time")}
                   for a in ads[:40]]
        prompt = (
            self.prompt_context()
            + "\nPubs concurrentes actives en France (une pub active depuis longtemps est probablement rentable) :\n"
            + "\n".join(f"- {c}" for c in compact)
            + "\n\nNous publions UNIQUEMENT en organique (TikTok, Reels, fil Facebook/Instagram). "
            "Cherche aussi sur le web les formats organiques qui fonctionnent en ce moment sur TikTok et Reels "
            "pour les outils de précision, la réparation d'électronique, l'horlogerie et le maquettisme.\n"
            "Donne 4 à 6 angles marketing exploitables (accroche courte, pourquoi ça marche, type de créa) "
            "et les formats/durées qui marchent.\n"
            + (f"Propose aussi {n_products} produits complémentaires (embouts, tapis magnétique, loupe, kits de réparation…) "
               "avec un prix d'achat fournisseur entre 20 et 60 €, JAMAIS de produit beauté ou soin."
               if n_products else "Ne propose aucun produit cette fois (products = []).")
        )
        result = await ctx.llm.ask(self.name, prompt, SCHEMA, tools=["WebSearch", "WebFetch"], mock=lambda: _mock(n_products),
                                   estimate_eur=0.25, simulated_cost_eur=0.18)

        ctx.db.publish_insight(day=ctx.day, source=self.name, topic="angles", payload=result["angles"])
        self.action("angles_published", {"count": len(result["angles"])})
        self.bullet(f"{len(ads)} pubs concurrentes analysées, {len(result['angles'])} angles transmis aux agents Visuels et Copywriting.")
        if result["angles"]:
            self.bullet("Angle principal : « " + result["angles"][0]["hook"] + " » — " + result["angles"][0]["why"])

        created, refused = 0, 0
        for p in result.get("products", [])[:n_products]:
            try:
                ctx.guard.check_product_candidate(p)
            except Exception as exc:
                refused += 1
                self.action("product_refused", p, status="skipped", error=str(exc))
                continue
            desc = f"<p>{p['description']}</p>" + "".join(f"<p><small>{m}</small></p>" for m in ctx.guard.legal_mentions())
            pid = ctx.tools.shopify.create_draft_product({**p, "description_html": desc, "tags": ["proposition-agent"]})
            created += 1
            self.action("product_draft_created", {"id": pid, **p})
            self.todo("produit_brouillon", f"Produit proposé en brouillon : {p['title']}",
                      f"Achat ≈ {p['purchase_price_eur']:.2f} € · vente conseillée {p['suggested_price_eur']:.2f} € · "
                      f"{p['why']} · Fournisseur : {p['supplier_hint']}. Vérifier le marquage CE avant publication.",
                      ref=f"draft:{p['title']}")
        if propose:
            self.bullet(f"{created} produit(s) complémentaire(s) ajouté(s) en brouillon (non publiés)"
                        + (f", {refused} refusé(s) par les garde-fous." if refused else "."))
        self.report.data = {"angles": result["angles"], "products_created": created}
        return self.report


def _mock(n_products: int) -> dict[str, Any]:
    products = [
        {"title": "Tapis de réparation magnétique en silicone", "category": "Accessoires d'atelier", "purchase_price_eur": 21.5,
         "suggested_price_eur": 39.9, "supplier_hint": "AliExpress via DSers — fournisseur noté 4,8",
         "why": "Complément naturel : les vis ne se perdent plus.", "description": "Tapis antidérapant avec zones magnétiques et repères."},
        {"title": "Loupe d'établi LED avec bras articulé", "category": "Optique d'atelier", "purchase_price_eur": 27.0,
         "suggested_price_eur": 54.9, "supplier_hint": "AliExpress via DSers",
         "why": "Indispensable pour l'horlogerie et la micro-soudure.", "description": "Loupe ×5 sur bras articulé, éclairage LED."},
        {"title": "Kit d'ongles décoratifs", "category": "Beauté", "purchase_price_eur": 22.0, "suggested_price_eur": 39.0,
         "supplier_hint": "—", "why": "Exemple qui doit être refusé par le garde-fou.", "description": "Kit beauté."},
    ]
    return {
        "angles": [
            {"angle": "Vis minuscule", "hook": "Cette vis fait 1 mm.", "why": "Le gros plan crée la curiosité dans les 2 premières secondes.",
             "creative_type": "avant_apres"},
            {"angle": "Réparer soi-même", "hook": "Ta manette grince ? Ouvre-la.", "why": "Tendance « repair » forte sur TikTok.",
             "creative_type": "mise_en_situation"},
            {"angle": "Geste d'artisan", "hook": "La précision, sans forcer.", "why": "Esthétique atelier = forte rétention en Reels.",
             "creative_type": "packshot_atelier"},
            {"angle": "Manuel vs électrique", "hook": "5 minutes ou 5 secondes ?", "why": "Les comparatifs génèrent des commentaires.",
             "creative_type": "comparatif"},
            {"angle": "Couple réglable", "hook": "Zéro vis abîmée.", "why": "Rassure les maquettistes et horlogers.",
             "creative_type": "gros_plan_detail"},
        ],
        "formats": ["9:16 de 10–12 s, accroche texte à l'écran dès la 1re seconde", "carrousel avant/après en 4:5"],
        "products": products[:n_products],
    }
