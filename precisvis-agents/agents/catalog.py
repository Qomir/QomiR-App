"""Agent Catalogue (Shopify).

- Réécrit les fiches (titre SEO, description orientée bénéfices, caractéristiques, FAQ),
  au plus une fois tous les N jours par fiche, en n'utilisant QUE les caractéristiques autorisées.
- Ajoute systématiquement les mentions obligatoires (garantie légale 2 ans, rétractation 14 jours,
  délai de livraison réaliste).
- Ne publie JAMAIS une fiche : un brouillon complet est signalé dans « À traiter » pour validation.
- Les prix, stocks et variantes sont synchronisés par l'application DSers ; l'agent signale
  les ruptures et les fiches incomplètes.
"""
from __future__ import annotations

import hashlib
import html
from datetime import date
from typing import Any

from .base import AgentReport, BaseAgent

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["seo_title", "seo_description", "intro", "benefits", "specs", "faq"],
    "properties": {
        "seo_title": {"type": "string", "maxLength": 70},
        "seo_description": {"type": "string", "maxLength": 160},
        "intro": {"type": "string"},
        "benefits": {"type": "array", "items": {"type": "string"}},
        "specs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "value"],
                  "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}},
        "faq": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["q", "a"],
                "properties": {"q": {"type": "string"}, "a": {"type": "string"}}}},
    },
}


class CatalogAgent(BaseAgent):
    name = "catalog"
    label = "Catalogue Shopify"
    spends_money = True

    async def run(self) -> AgentReport:
        ctx = self.ctx
        products = ctx.tools.shopify.products()
        every = int(ctx.cfg.get("catalog.rewrite_listing_every_days", 14))
        rewritten, incomplete, out_of_stock = 0, 0, 0

        for p in products:
            banned = ctx.guard.banned_reason(p["title"], p["description_html"], p.get("category", ""))
            if banned:
                self.todo("validation", f"Produit à retirer : {p['title']}", f"Catégorie interdite ({banned}).", ref=f"banned:{p['id']}")
                continue
            if p.get("status") == "ACTIVE" and (p.get("inventory") or 0) <= 0:
                out_of_stock += 1
                self.todo("erreur", f"Rupture de stock : {p['title']}", "Stock à 0 dans Shopify (synchronisé par DSers). "
                          "Vérifier le fournisseur ou masquer le produit.", ref=f"oos:{p['id']}:{ctx.day}")

            last = ctx.db.kv_get(f"listing_rewritten:{p['id']}")
            due = not last or (ctx.date - date.fromisoformat(last)).days >= every
            ok, problems = ctx.guard.listing_publishable(p)
            if not due and ok:
                continue

            content = await ctx.llm.ask(self.name, self._prompt(p), SCHEMA, mock=lambda p=p: _mock(p),
                                        estimate_eur=0.08, simulated_cost_eur=0.05)
            violations = ctx.guard.copy_violations(content["intro"], " ".join(content["benefits"]),
                                                   " ".join(f["a"] for f in content["faq"]))
            if violations:
                self.action("listing_rejected", {"product": p["title"], "violations": violations}, status="skipped")
                continue
            body = self.render_html(content)
            ctx.tools.shopify.update_product(p["id"], description_html=body, seo_title=content["seo_title"],
                                             seo_description=content["seo_description"])
            ctx.db.kv_set(f"listing_rewritten:{p['id']}", ctx.day)
            rewritten += 1
            self.action("listing_updated", {"product": p["title"], "hash": hashlib.md5(body.encode()).hexdigest()[:8]})

            ok, problems = ctx.guard.listing_publishable({**p, "description_html": body})
            if p.get("status") != "ACTIVE":
                if ok:
                    self.todo("validation", f"Fiche prête à publier : {p['title']}",
                              "Photos et mentions légales présentes. Publication à valider par vous.", ref=f"ready:{p['id']}")
                else:
                    incomplete += 1
                    self.todo("validation", f"Fiche incomplète (non publiable) : {p['title']}", " ; ".join(problems),
                              ref=f"incomplete:{p['id']}")

        self.bullet(f"{len(products)} fiche(s) contrôlée(s), {rewritten} réécrite(s) (SEO, bénéfices, FAQ, mentions légales).")
        if incomplete:
            self.bullet(f"{incomplete} fiche(s) brouillon incomplète(s) : non publiées (photos ou mentions manquantes).")
        if out_of_stock:
            self.bullet(f"{out_of_stock} produit(s) actif(s) en rupture de stock signalé(s).")
        self.report.data = {"rewritten": rewritten}
        return self.report

    def _prompt(self, p: dict[str, Any]) -> str:
        return (self.prompt_context()
                + f"\nFiche à rédiger : « {p['title']} » (catégorie {p.get('category') or 'outil'}).\n"
                f"Description actuelle : {p['description_html'][:1500]}\n"
                f"Délai de livraison réel : {self.ctx.cfg.get('catalog.shipping_delay_text')}.\n"
                "Rédige en français un titre SEO (≤ 70 caractères), une méta-description (≤ 160), une intro de 2 phrases "
                "orientée bénéfices, 4 à 6 bénéfices concrets, les caractéristiques techniques (uniquement celles connues, "
                "sinon « à confirmer »), et 4 questions/réponses de FAQ (dont livraison et retours).")

    def render_html(self, c: dict[str, Any]) -> str:
        e = html.escape
        parts = [f"<p>{e(c['intro'])}</p>", "<h3>Pourquoi vous allez l'adopter</h3><ul>"]
        parts += [f"<li>{e(b)}</li>" for b in c["benefits"]]
        parts += ["</ul><h3>Caractéristiques</h3><ul>"]
        parts += [f"<li><strong>{e(s['label'])}</strong> : {e(s['value'])}</li>" for s in c["specs"]]
        parts += ["</ul><h3>Questions fréquentes</h3>"]
        parts += [f"<p><strong>{e(f['q'])}</strong><br>{e(f['a'])}</p>" for f in c["faq"]]
        parts += ["<h3>Livraison, retours et garanties</h3><ul>"]
        parts += [f"<li>{e(m)}</li>" for m in self.ctx.guard.legal_mentions()]
        parts += ["</ul>"]
        return "\n".join(parts)


def _mock(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "seo_title": f"{p['title'][:52]} | PrecisVis",
        "seo_description": "Vissez et dévissez les plus petites vis sans effort : embouts de précision, couple réglable, LED. Livraison suivie.",
        "intro": "Les petites vis ne devraient pas vous gâcher une réparation. Avec PrecisVis, chaque geste devient précis et sans effort.",
        "benefits": ["Ouvre smartphones, manettes, montres et drones sans abîmer les vis",
                     "Couple réglable : on serre juste ce qu'il faut",
                     "Éclairage LED pour voir au fond des boîtiers", "Recharge USB-C, sans piles"],
        "specs": [{"label": "Embouts", "value": "cruciforme, plat, Torx, hexagonal, Pentalobe, Tri-wing"},
                  {"label": "Alimentation", "value": "batterie rechargeable USB-C"},
                  {"label": "Couple", "value": "réglable sur plusieurs niveaux"}],
        "faq": [{"q": "Quel est le délai de livraison ?", "a": "Comptez 7 à 12 jours ouvrés, avec un numéro de suivi."},
                {"q": "Puis-je le retourner ?", "a": "Oui, vous disposez de 14 jours après réception pour changer d'avis."},
                {"q": "Convient-il à l'horlogerie ?", "a": "Oui, les embouts de précision s'adaptent aux vis de boîtiers de montre."},
                {"q": "Comment le recharger ?", "a": "Avec le câble USB-C fourni, sur n'importe quel chargeur."}],
    }
