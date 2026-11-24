"""Classe commune à tous les agents."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.context import RunContext


@dataclass
class AgentReport:
    bullets: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    name: str = "base"
    label: str = "Agent"
    spends_money: bool = False   # l'orchestrateur vérifie le budget avant de lancer ces agents

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.report = AgentReport()
        self.log = logging.getLogger(f"precisvis.{self.name}")

    # -- à implémenter -------------------------------------------------------
    async def run(self) -> AgentReport:  # pragma: no cover
        raise NotImplementedError

    # -- utilitaires --------------------------------------------------------
    def action(self, action: str, result: Any = None, status: str | None = None, cost_eur: float = 0.0,
               error: str | None = None) -> None:
        status = status or ("simulated" if self.ctx.dry_run else "ok")
        self.ctx.db.log_action(day=self.ctx.day, run_id=self.ctx.run_id, agent=self.name, action=action,
                               status=status, result=result, cost_eur=cost_eur, error=error, dry_run=self.ctx.dry_run)

    def bullet(self, text: str) -> None:
        self.report.bullets.append(text)

    def todo(self, category: str, title: str, details: str = "", ref: str = "") -> None:
        self.ctx.db.add_todo(day=self.ctx.day, category=category, title=title, details=details, ref=ref,
                             dry_run=self.ctx.dry_run)

    def prompt_context(self) -> str:
        b = self.ctx.brand
        facts = "\n".join(f"- {f}" for f in b.get("product_facts", []))
        return (f"Date : {self.ctx.day}. Boutique : {self.ctx.cfg.get('store.name')} ({self.ctx.cfg.get('store.url')}).\n"
                f"Produit phare : {self.ctx.cfg.get('store.main_product_title')}.\n"
                f"Caractéristiques AUTORISÉES (rien d'autre) :\n{facts}\n")
