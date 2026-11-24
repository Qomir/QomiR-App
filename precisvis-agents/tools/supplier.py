"""Fournisseur dropshipping.

DSers n'a pas d'API publique pour passer les commandes : c'est l'application DSers
installée sur Shopify qui transmet les commandes à AliExpress (réglage « Commande
automatique ») et qui renvoie les numéros de suivi dans Shopify (« Synchronisation
du suivi »), ce qui déclenche l'e-mail d'expédition au client.

Ce module SURVEILLE donc le flux à partir des données Shopify et détecte :
- les commandes payées non traitées par DSers après N heures ;
- les commandes expédiées sans numéro de suivi après N jours ;
- les colis sans livraison depuis plus de N jours ;
- les ruptures de stock (stock Shopify synchronisé par DSers).

`CJSupplier` est prévu pour basculer plus tard vers CJ Dropshipping (API directe).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DSersMonitor:
    name = "dsers"

    def __init__(self, unfulfilled_hours: int, no_tracking_days: int, stuck_days: int):
        self.unfulfilled_hours = unfulfilled_hours
        self.no_tracking_days = no_tracking_days
        self.stuck_days = stuck_days

    def analyse(self, orders: list[dict[str, Any]], now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
        now = now or datetime.now(timezone.utc)
        res: dict[str, list[dict[str, Any]]] = {"not_transmitted": [], "no_tracking": [], "stuck": [], "ok": []}
        for o in orders:
            if o.get("cancelled") or o.get("financial_status") not in ("PAID", "PARTIALLY_REFUNDED"):
                continue
            created = _dt(o["created_at"])
            age_h = (now - created).total_seconds() / 3600 if created else 0
            if not o.get("fulfillments"):
                if age_h > self.unfulfilled_hours:
                    res["not_transmitted"].append({**_brief(o), "age_hours": round(age_h)})
                else:
                    res["ok"].append(_brief(o))
                continue
            f = o["fulfillments"][0]
            shipped = _dt(f.get("created_at"))
            ship_days = (now - shipped).days if shipped else 0
            if not f.get("tracking"):
                if ship_days >= self.no_tracking_days:
                    res["no_tracking"].append({**_brief(o), "days": ship_days})
                continue
            if not f.get("delivered_at") and ship_days > self.stuck_days:
                res["stuck"].append({**_brief(o), "days": ship_days, "tracking": f["tracking"][0],
                                     "status": f.get("display_status")})
                continue
            res["ok"].append(_brief(o))
        return res


def _brief(o: dict[str, Any]) -> dict[str, Any]:
    return {"order": o["name"], "email": o.get("email"), "total": o.get("total")}


class CJSupplier:  # pragma: no cover - à activer plus tard
    name = "cj"

    def __init__(self, *_: Any, **__: Any):
        raise NotImplementedError("Intégration CJ Dropshipping non activée : orders.supplier doit rester 'dsers'.")
