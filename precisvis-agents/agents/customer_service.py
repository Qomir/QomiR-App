"""Agent SAV client.

- Lit les e-mails non lus de la boîte support.
- Répond seul aux questions simples (suivi, délais, utilisation, informations retour),
  uniquement si Claude est sûr de lui (confiance ≥ seuil) et que la réponse passe les garde-fous.
- Ne rembourse JAMAIS : prépare la réponse + la demande de remboursement → « À traiter ».
- Réclamation agressive, juridique, litige PayPal/Stripe → escalade « À traiter », aucune réponse automatique.
"""
from __future__ import annotations

import html
import re
from typing import Any

from .base import AgentReport, BaseAgent

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["category", "confidence", "summary", "reply", "refund_requested", "order_number"],
    "properties": {
        "category": {"type": "string", "enum": ["suivi_colis", "delai_livraison", "utilisation_produit", "retour_info",
                                                "remboursement", "reclamation_agressive", "juridique", "litige_paiement",
                                                "autre"]},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "reply": {"type": "string"},
        "refund_requested": {"type": "boolean"},
        "order_number": {"type": "string"},
    },
}


class CustomerServiceAgent(BaseAgent):
    name = "customer_service"
    label = "SAV client"
    spends_money = True

    async def run(self) -> AgentReport:
        ctx = self.ctx
        if not ctx.cfg.get("support.enabled", True):
            self.bullet("SAV désactivé dans config.yaml.")
            return self.report
        inbox = ctx.tools.inbox
        mails = inbox.unread(int(ctx.cfg.get("support.max_emails_per_run", 30)))
        auto_cats = set(ctx.cfg.get("support.auto_reply_categories", []))
        min_conf = float(ctx.cfg.get("support.min_confidence_auto_reply", 0.8))
        replied, escalated, refunds, other = 0, 0, 0, 0

        for m in mails:
            order_no = _order_number(m.subject + " " + m.body)
            orders = ctx.tools.shopify.find_orders(email=m.sender, name=order_no or "")
            facts = [{"commande": o["name"], "statut": o["fulfillment_status"],
                      "suivi": (o["fulfillments"][0]["tracking"] if o.get("fulfillments") else []),
                      "expédiée_le": (o["fulfillments"][0]["created_at"][:10] if o.get("fulfillments") else None)}
                     for o in orders[:3]]
            prompt = (self.prompt_context()
                      + f"\nDélai de livraison annoncé : {ctx.cfg.get('catalog.shipping_delay_text')}. "
                      "Retours : 14 jours après réception (droit de rétractation), garantie légale de conformité 2 ans.\n"
                      f"Données commande (seule source de vérité, n'invente rien) : {facts}\n\n"
                      f"E-mail du client <{m.sender}> — objet « {m.subject} » :\n{m.body}\n\n"
                      "Classe la demande, résume-la en une phrase, et rédige une réponse en français, polie, exacte et brève, "
                      f"signée « {ctx.cfg.get('support.signature')} ». Ne promets JAMAIS de remboursement : indique que la demande "
                      "est transmise et traitée sous 48 h. Si une information manque, demande-la au client.")
            res = await ctx.llm.ask(self.name, prompt, SCHEMA, mock=lambda m=m: _mock(m), estimate_eur=0.05, simulated_cost_eur=0.02)
            cat = res["category"]
            self.action("email_classified", {"from": m.sender, "subject": m.subject, "category": cat, "confidence": res["confidence"]})

            if cat in ("reclamation_agressive", "juridique", "litige_paiement"):
                escalated += 1
                self.todo("litige", f"SAV à traiter vous-même : {m.subject}",
                          f"De {m.sender} · {res['summary']} · Projet de réponse (NON envoyé) : {res['reply']}", ref=f"mail:{m.message_id}")
                inbox.mark_handled(m.uid, "PrecisVis/Escalade")
                continue
            if cat == "remboursement" or res["refund_requested"]:
                refunds += 1
                self.todo("remboursement", f"Remboursement à valider — {res['order_number'] or order_no or m.sender}",
                          f"{res['summary']} · Réponse préparée (NON envoyée) : {res['reply']}", ref=f"mail:{m.message_id}")
                inbox.mark_handled(m.uid, "PrecisVis/Remboursement")
                continue
            violations = ctx.guard.copy_violations(res["reply"])
            if cat in auto_cats and res["confidence"] >= min_conf and not violations:
                ctx.tools.support_sender.send(m.sender, "Re: " + m.subject, _html(res["reply"]), in_reply_to=m.message_id)
                inbox.mark_handled(m.uid, "PrecisVis/Répondu")
                replied += 1
                self.action("email_replied", {"to": m.sender, "category": cat})
            else:
                other += 1
                self.todo("info", f"E-mail SAV sans réponse automatique : {m.subject}",
                          f"De {m.sender} · {res['summary']} · Proposition : {res['reply']}", ref=f"mail:{m.message_id}")
                inbox.mark_handled(m.uid, "PrecisVis/À-relire")

        self.bullet(f"{len(mails)} e-mail(s) lu(s) : {replied} réponse(s) envoyée(s), {refunds} remboursement(s) à valider, "
                    f"{escalated} escalade(s), {other} à relire.")
        self.report.data = {"read": len(mails), "replied": replied, "refunds": refunds, "escalated": escalated}
        return self.report


def _order_number(text: str) -> str | None:
    m = re.search(r"#\s?(\d{3,6})", text)
    return f"#{m.group(1)}" if m else None


def _html(text: str) -> str:
    return "<div style='font-family:Arial,sans-serif;font-size:14px;line-height:1.5'>" + \
        "<br>".join(html.escape(line) for line in text.splitlines()) + "</div>"


def _mock(m: Any) -> dict[str, Any]:
    body = (m.subject + " " + m.body).lower()
    sig = "\n\nBien cordialement,\nL'équipe PrecisVis"
    if "avocat" in body or "litige" in body or "arnaque" in body:
        return {"category": "litige_paiement", "confidence": 0.95, "summary": "Client mécontent, colis non reçu après 18 jours, litige PayPal ouvert.",
                "reply": "Bonjour, nous sommes désolés pour ce retard. Nous vérifions immédiatement l'acheminement de votre colis "
                         "et revenons vers vous sous 24 h." + sig, "refund_requested": False, "order_number": "#1101"}
    if "rembours" in body:
        return {"category": "remboursement", "confidence": 0.9, "summary": "Demande de remboursement (produit ne convient pas).",
                "reply": "Bonjour, nous avons bien reçu votre demande. Elle est transmise et sera traitée sous 48 h ; "
                         "nous vous enverrons les instructions de retour." + sig, "refund_requested": True, "order_number": "#1121"}
    if "suivi" in body or "où en est" in body:
        return {"category": "suivi_colis", "confidence": 0.92, "summary": "Demande de suivi pour la commande #1150.",
                "reply": "Bonjour Julien, votre commande #1150 a été expédiée et voyage avec le numéro de suivi LP001150CN. "
                         "Le délai habituel est de 7 à 12 jours ouvrés." + sig, "refund_requested": False, "order_number": "#1150"}
    return {"category": "utilisation_produit", "confidence": 0.86, "summary": "Question sur l'usage en horlogerie.",
            "reply": "Bonjour, oui : les embouts de précision (cruciforme et plat de petite taille) conviennent aux vis de fond "
                     "de boîtier. Réglez le couple au minimum et terminez le serrage en mode manuel." + sig,
            "refund_requested": False, "order_number": ""}
