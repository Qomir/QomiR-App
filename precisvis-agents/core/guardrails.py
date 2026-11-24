"""Garde-fous : TOUTE dépense et toute action sensible passe par ici.

- plafond quotidien et mensuel de coût API (Claude + images + vidéos) ;
- interrupteur d'arrêt (kill switch) ;
- interdiction de la publicité payante ;
- règles catalogue (aucun produit beauté, prix d'achat 20–60 €, mentions légales) ;
- règles de rédaction (pas de fausse urgence, de prix barrés fictifs, de faux avis).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .config import Config
from .db import DB


class GuardrailError(Exception):
    """Action refusée par un garde-fou."""


class BudgetExceeded(GuardrailError):
    pass


class KillSwitchActive(GuardrailError):
    pass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


# Formulations interdites dans les textes et visuels (droit de la conso + politiques Meta/TikTok).
FORBIDDEN_COPY_PATTERNS: list[tuple[str, str]] = [
    (r"\bplus que \d+\b", "fausse rareté (« plus que N »)"),
    (r"\bderni[eè]res? (pieces?|unites?|exemplaires?)\b", "fausse rareté"),
    (r"\bstock (tres )?limite\b", "fausse rareté"),
    (r"\bbientot en rupture\b", "fausse rareté"),
    (r"\bvite\s*!*\s*(avant|il ne reste)", "urgence mensongère"),
    (r"\bderni[eè]re chance\b", "urgence mensongère"),
    (r"\bexpire dans\b", "urgence mensongère"),
    (r"\bprix barre\b", "prix barré"),
    (r"\bau lieu de \d", "prix barré / prix de référence fictif"),
    (r"-\s?\d{2}\s?%", "réduction non justifiée"),
    (r"\bgaranti(e)? a vie\b", "promesse fausse"),
    (r"\b100 ?% (satisfait|garanti)", "promesse non vérifiable"),
    (r"\ble meilleur (du|au) monde\b", "superlatif non prouvé"),
    (r"\bn[°o] ?1\b", "superlatif non prouvé"),
    (r"\bdes milliers de clients\b", "preuve sociale non vérifiée"),
    (r"\b\d+ ?(000|k) clients\b", "preuve sociale non vérifiée"),
    (r"[«\"]\s*j'?\s?adore", "faux témoignage"),
    (r"\b(avis|temoignage) client\b", "faux avis/témoignage"),
    (r"\b(apple|iphone|samsung|nintendo|switch|playstation|ps5|xbox|rolex|dji|gopro|lego)\b", "marque tierce"),
]


class Guardrails:
    def __init__(self, cfg: Config, db: DB, day: str, dry_run: bool):
        self.cfg = cfg
        self.db = db
        self.day = day
        self.dry_run = dry_run

    # -- kill switch / pub payante ----------------------------------------
    def check_kill_switch(self) -> None:
        if self.cfg.kill_switch:
            raise KillSwitchActive("kill_switch: true dans config.yaml — toutes les actions sont stoppées.")

    def check_paid_ads_disabled(self) -> None:
        if self.cfg.get("paid_ads.enabled", False):
            raise GuardrailError(
                "paid_ads.enabled est à true, mais ce système est configuré en organique uniquement : "
                "aucune campagne payante ne sera créée. Remettez paid_ads.enabled: false."
            )
        if float(self.cfg.get("paid_ads.daily_budget_eur", 0) or 0) > 0 or float(self.cfg.get("paid_ads.monthly_budget_eur", 0) or 0) > 0:
            raise GuardrailError("Un budget publicitaire non nul est défini alors que la publicité payante est désactivée.")

    # -- budget API ---------------------------------------------------------
    @property
    def daily_cap(self) -> float:
        return float(self.cfg.get("budgets.api_daily_eur", 5.0))

    @property
    def monthly_cap(self) -> float:
        return float(self.cfg.get("budgets.api_monthly_eur", 120.0))

    def spent_today(self) -> float:
        return self.db.cost_total(self.day)

    def spent_month(self) -> float:
        return self.db.cost_total(self.day[:7])

    def remaining_eur(self) -> float:
        return max(0.0, min(self.daily_cap - self.spent_today(), self.monthly_cap - self.spent_month()))

    def authorize_spend(self, estimate_eur: float, what: str) -> None:
        """Lève BudgetExceeded si la dépense prévue ferait dépasser un plafond."""
        self.check_kill_switch()
        if estimate_eur < 0:
            raise ValueError("estimation négative")
        if self.spent_today() + estimate_eur > self.daily_cap + 1e-9:
            raise BudgetExceeded(
                f"Plafond API quotidien atteint ({self.spent_today():.2f} € dépensés / {self.daily_cap:.2f} €) — {what} annulé."
            )
        if self.spent_month() + estimate_eur > self.monthly_cap + 1e-9:
            raise BudgetExceeded(
                f"Plafond API mensuel atteint ({self.spent_month():.2f} € / {self.monthly_cap:.2f} €) — {what} annulé."
            )

    # -- catalogue ----------------------------------------------------------
    def banned_reason(self, *texts: str) -> str | None:
        blob = normalize(" ".join(t for t in texts if t))
        for kw in self.cfg.get("catalog.banned_keywords", []):
            if re.search(r"\b" + re.escape(normalize(kw)) + r"(s|x)?\b", blob):
                return f"mot interdit « {kw} » (catégorie beauté exclue)"
        return None

    def check_product_candidate(self, product: dict[str, Any]) -> None:
        reason = self.banned_reason(product.get("title", ""), product.get("description", ""),
                                    product.get("category", ""), " ".join(product.get("tags", []) or []))
        if reason:
            raise GuardrailError(f"Produit refusé : {reason}.")
        price = float(product.get("purchase_price_eur") or 0)
        lo = float(self.cfg.get("catalog.purchase_price_min_eur", 20))
        hi = float(self.cfg.get("catalog.purchase_price_max_eur", 60))
        if not (lo <= price <= hi):
            raise GuardrailError(f"Produit refusé : prix d'achat {price:.2f} € hors de la plage {lo:.0f}–{hi:.0f} €.")

    def legal_mentions(self) -> list[str]:
        delay = self.cfg.get("catalog.shipping_delay_text", "7 à 12 jours ouvrés")
        return [m.replace("{shipping_delay}", delay) for m in self.cfg.get("catalog.legal_mentions", [])]

    def listing_publishable(self, product: dict[str, Any]) -> tuple[bool, list[str]]:
        """Une fiche n'est publiable qu'avec des photos ET toutes les mentions obligatoires."""
        problems: list[str] = []
        if not product.get("images"):
            problems.append("aucune photo")
        body = normalize(product.get("description_html", ""))
        checks = {
            "garantie légale de conformité": "garantie legale",
            "droit de rétractation 14 jours": "14 jours",
            "délai de livraison": "livraison",
        }
        for label, needle in checks.items():
            if needle not in body:
                problems.append(f"mention manquante : {label}")
        if self.banned_reason(product.get("title", ""), product.get("description_html", "")):
            problems.append("produit de catégorie interdite")
        return (not problems, problems)

    # -- textes ------------------------------------------------------------
    def copy_violations(self, *texts: str) -> list[str]:
        blob = normalize(" ".join(t for t in texts if t))
        found = []
        for pattern, label in FORBIDDEN_COPY_PATTERNS:
            if re.search(pattern, blob):
                found.append(label)
        return sorted(set(found))

    def check_on_image_text(self, text: str) -> None:
        max_words = int(self.cfg.get("creatives.max_words_on_image", 7))
        n = len([w for w in re.split(r"\s+", text.strip()) if w])
        if n > max_words:
            raise GuardrailError(f"Texte sur l'image trop long ({n} mots > {max_words}).")
        bad = self.copy_violations(text)
        if bad:
            raise GuardrailError("Texte sur l'image refusé : " + ", ".join(bad))
