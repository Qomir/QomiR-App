"""Agent Commandes (DSers).

DSers transmet les commandes à AliExpress et renvoie les suivis dans Shopify (le client reçoit
l'e-mail d'expédition de Shopify). Cet agent vérifie que ce flux fonctionne et alerte sur :
commande non transmise, commande sans suivi, colis bloqué > 10 jours, litige de paiement.
"""
from __future__ import annotations

from .base import AgentReport, BaseAgent


class OrdersAgent(BaseAgent):
    name = "orders"
    label = "Commandes"

    async def run(self) -> AgentReport:
        ctx = self.ctx
        orders = ctx.tools.shopify.open_orders()
        res = ctx.tools.supplier.analyse(orders)
        self.action("orders_checked", {k: len(v) for k, v in res.items()})

        for o in res["not_transmitted"]:
            self.todo("erreur", f"Commande {o['order']} non transmise au fournisseur",
                      f"Payée depuis {o['age_hours']} h sans expédition. Vérifier dans DSers (« Commandes en attente ») "
                      "que la commande automatique est active et que le moyen de paiement AliExpress est valide.",
                      ref=f"not_transmitted:{o['order']}")
        for o in res["no_tracking"]:
            self.todo("erreur", f"Commande {o['order']} sans numéro de suivi",
                      f"Expédiée il y a {o['days']} jours sans suivi. Vérifier la synchronisation du suivi dans DSers.",
                      ref=f"no_tracking:{o['order']}")
        for o in res["stuck"]:
            self.todo("erreur", f"Colis {o['order']} bloqué depuis {o['days']} jours",
                      f"Suivi {o['tracking']} (statut : {o.get('status') or 'inconnu'}). Contacter le fournisseur via DSers ; "
                      "prévenir le client si besoin.", ref=f"stuck:{o['order']}")

        disputes = ctx.tools.shopify.disputes()
        for d in disputes:
            self.todo("litige", f"Litige de paiement sur {d['order']} ({d['amount']:.2f} €)",
                      f"Motif : {d['reason']} · statut {d['status']}. Répondre dans Shopify > Paiements > Litiges.",
                      ref=f"dispute:{d['id']}")

        total = sum(len(v) for v in res.values())
        self.bullet(f"{total} commande(s) en cours vérifiée(s) : {len(res['ok'])} normales, "
                    f"{len(res['not_transmitted'])} non transmise(s), {len(res['no_tracking'])} sans suivi, "
                    f"{len(res['stuck'])} colis bloqué(s) > {ctx.cfg.get('orders.alert_stuck_days', 10)} j.")
        if disputes:
            self.bullet(f"{len(disputes)} litige(s) de paiement ouvert(s) — voir « À traiter ».")
        self.report.data = {k: len(v) for k, v in res.items()} | {"disputes": len(disputes)}
        return self.report
