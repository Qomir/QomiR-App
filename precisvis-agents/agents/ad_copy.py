"""Agent Copywriting — 3 variantes de texte par créa et par plateforme (publication organique).

TikTok : direct, oral, tutoiement. Facebook : plus explicatif, vouvoiement. Instagram : visuel, court.
Chaque variante est contrôlée par les garde-fous (pas de fausse urgence, de prix barré fictif,
de faux avis, de marque tierce, de promesse fausse) ; une variante non conforme est rejetée.
"""
from __future__ import annotations

import json
from typing import Any

from .base import AgentReport, BaseAgent

PLATFORMS = ("facebook", "instagram", "tiktok")

VARIANT = {"type": "object", "additionalProperties": False, "required": ["variant", "hook", "body", "title", "cta", "hashtags"],
           "properties": {"variant": {"type": "string", "enum": ["A", "B", "C"]}, "hook": {"type": "string"},
                          "body": {"type": "string"}, "title": {"type": "string"}, "cta": {"type": "string"},
                          "hashtags": {"type": "array", "items": {"type": "string"}}}}

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["creatives"],
          "properties": {"creatives": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["creative_id", "facebook", "instagram", "tiktok"],
              "properties": {"creative_id": {"type": "string"},
                             **{p: {"type": "array", "items": VARIANT} for p in PLATFORMS}}}}}}


class AdCopyAgent(BaseAgent):
    name = "ad_copy"
    label = "Copywriting"
    spends_money = True

    async def run(self) -> AgentReport:
        ctx = self.ctx
        creatives = ctx.db.query("SELECT id, concept, angle, headline, kind FROM creatives WHERE day = ? AND status = 'ok'", [ctx.day])
        if not creatives:
            self.bullet("Aucune créa validée aujourd'hui : pas de texte à écrire.")
            return self.report
        max_tags = int(ctx.cfg.get("social.hashtags_max", 5))
        prompt = (self.prompt_context()
                  + f"\nCréas du jour : {json.dumps(creatives, ensure_ascii=False)}\n"
                  "Publication ORGANIQUE (pas de pub payante). Pour CHAQUE créa et CHAQUE plateforme (facebook, instagram, tiktok), "
                  "écris 3 variantes A, B, C : hook (1re ligne qui arrête le scroll), body (2 à 4 phrases simples et concrètes), "
                  "title (≤ 40 caractères), cta, hashtags (≤ " + str(max_tags) + ", sans #, en français).\n"
                  "TikTok : direct, oral, tutoiement. Facebook : explicatif, vouvoiement, peut contenir le lien boutique. "
                  "Instagram : visuel, court, CTA « lien en bio ». Interdits : urgence ou rareté fausses, prix barrés, "
                  "réductions, faux avis ou témoignages, superlatifs non prouvés, marques tierces.")
        data = await ctx.llm.ask(self.name, prompt, SCHEMA, mock=lambda: _mock(creatives), estimate_eur=0.2, simulated_cost_eur=0.12)

        kept, rejected = 0, 0
        reasons: set[str] = set()
        valid_ids = {c["id"] for c in creatives}
        for item in data["creatives"]:
            if item["creative_id"] not in valid_ids:
                continue
            for platform in PLATFORMS:
                for v in item[platform][:3]:
                    bad = ctx.guard.copy_violations(v["hook"], v["body"], v["title"], v["cta"])
                    if bad:
                        rejected += 1
                        reasons.update(bad)
                        self.action("copy_rejected", {"creative": item["creative_id"], "platform": platform, "variant": v["variant"],
                                                      "violations": bad}, status="skipped")
                        continue
                    ctx.db.insert("copies", {"creative_id": item["creative_id"], "platform": platform, "variant": v["variant"],
                                             "hook": v["hook"], "body": v["body"], "title": v["title"], "cta": v["cta"],
                                             "hashtags": json.dumps(v["hashtags"][:max_tags], ensure_ascii=False), "day": ctx.day})
                    kept += 1
        self.action("copies_saved", {"kept": kept, "rejected": rejected})
        self.bullet(f"{kept} textes écrits pour {len(creatives)} créas (3 variantes × Facebook, Instagram, TikTok).")
        if rejected:
            self.bullet(f"{rejected} variante(s) rejetée(s) par les garde-fous : {', '.join(sorted(reasons))}.")
        self.report.data = {"kept": kept, "rejected": rejected}
        return self.report


def _mock(creatives: list[dict[str, Any]]) -> dict[str, Any]:
    out = []
    for c in creatives:
        h = c["headline"]
        out.append({
            "creative_id": c["id"],
            "facebook": [
                {"variant": "A", "hook": h, "body": "Smartphone, manette, montre ou maquette : les petites vis ne résistent plus. "
                 "Embouts de précision, couple réglable et LED pour voir ce que vous faites.", "title": "Le bon outil pour les petites vis",
                 "cta": "Découvrir PrecisVis", "hashtags": ["bricolage", "reparation", "atelier"]},
                {"variant": "B", "hook": "Vous aussi, vous avez abîmé une vis minuscule ?", "body": "Le couple réglable serre juste ce qu'il "
                 "faut. Résultat : des réparations propres, sans forcer.", "title": "Réparer sans abîmer", "cta": "Voir le tournevis",
                 "hashtags": ["diy", "electronique"]},
                {"variant": "C", "hook": "Plus de vis perdues", "body": "Plus que 2 en stock, profitez-en !", "title": "Stock limité",
                 "cta": "Commander", "hashtags": ["promo"]},   # doit être rejeté (fausse rareté)
            ],
            "instagram": [
                {"variant": "A", "hook": h, "body": "Le geste précis, sans forcer.", "title": "PrecisVis", "cta": "Lien en bio",
                 "hashtags": ["atelier", "maker", "horlogerie"]},
                {"variant": "B", "hook": "Petites vis, grand soulagement.", "body": "Embouts de précision + LED intégrée.",
                 "title": "Précision d'atelier", "cta": "Lien en bio", "hashtags": ["reparation", "maquette"]},
                {"variant": "C", "hook": "Votre établi mérite mieux.", "body": "Recharge USB-C, couple réglable.",
                 "title": "L'outil des makers", "cta": "Lien en bio", "hashtags": ["outils", "maker"]},
            ],
            "tiktok": [
                {"variant": "A", "hook": "Regarde cette vis. 1 mm.", "body": "Avec PrecisVis, tu la sors en 5 secondes, sans l'abîmer.",
                 "title": "Vis minuscule ? Facile.", "cta": "Lien en bio", "hashtags": ["reparation", "astuce", "diy"]},
                {"variant": "B", "hook": "Ta manette fait des siennes ?", "body": "Ouvre-la toi-même, c'est plus simple que tu crois.",
                 "title": "Répare ta manette", "cta": "Lien en bio", "hashtags": ["gaming", "reparation"]},
                {"variant": "C", "hook": "POV : tu répares enfin ta montre.", "body": "Couple réglable, LED, embouts de précision.",
                 "title": "Horlogerie maison", "cta": "Lien en bio", "hashtags": ["montre", "horlogerie"]},
            ],
        })
    return {"creatives": out}
