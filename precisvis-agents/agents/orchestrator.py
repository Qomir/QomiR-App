"""Agent Orchestrateur — lance les agents dans l'ordre, gère les échecs et les garde-fous.

Phases (heure de Paris) :
- morning  (07:00) : Veille → Catalogue → Visuels → Copywriting → Planning des posts → Commandes → SAV → Analytics (veille)
- publish  (12:30, 18:30) : publication des posts programmés
- evening  (20:00) : Analytics du jour → Reporting (e-mail bilan)

Chaque agent : 3 tentatives au total (1 + 2 nouvelles), puis passage au suivant ;
l'échec est enregistré et apparaît dans le bilan. Un agent qui dépense de l'argent n'est
lancé que s'il reste du budget API. Si toute la phase échoue, un e-mail d'alerte part immédiatement.
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime
from typing import Any

from core.context import RunContext
from core.db import now_iso
from core.guardrails import BudgetExceeded, GuardrailError, KillSwitchActive

from .ad_copy import AdCopyAgent
from .ad_visuals import AdVisualsAgent
from .analytics import AnalyticsAgent
from .base import BaseAgent
from .catalog import CatalogAgent
from .customer_service import CustomerServiceAgent
from .orders import OrdersAgent
from .product_research import ProductResearchAgent
from .reporting import ReportingAgent, send_failure_alert
from .social_publisher import SocialPublisherAgent

log = logging.getLogger("precisvis.orchestrator")

MAX_ATTEMPTS = 3            # 1 essai + 2 nouvelles tentatives
RETRY_DELAY_S = 20


class Orchestrator:
    def __init__(self, ctx: RunContext, retry_delay_s: float = RETRY_DELAY_S):
        self.ctx = ctx
        self.retry_delay_s = retry_delay_s if not ctx.dry_run else 0

    # -- exécution d'un agent avec reprises ------------------------------------------------
    async def run_agent(self, agent: BaseAgent, method: str = "run", **kwargs: Any) -> str:
        ctx = self.ctx
        started = now_iso()
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            agent.report.bullets.clear()
            try:
                if agent.spends_money and ctx.guard.remaining_eur() <= 0:
                    raise BudgetExceeded("plafond API atteint avant le lancement de l'agent")
                report = await getattr(agent, method)(**kwargs)
            except (KillSwitchActive, BudgetExceeded, GuardrailError) as exc:
                # Les garde-fous ne se « réessaient » pas : on s'arrête net pour cet agent.
                self._record(agent, "skipped", attempt, agent.report.bullets + [f"Arrêté par un garde-fou : {exc}"], {}, str(exc), started)
                if isinstance(exc, BudgetExceeded):
                    agent.todo("erreur", f"Plafond de coût API atteint ({agent.label})", str(exc), ref=f"budget:{ctx.day}:{agent.name}")
                return "skipped"
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("%s — tentative %s/%s échouée : %s", agent.name, attempt, MAX_ATTEMPTS, last_error)
                ctx.db.log_action(day=ctx.day, run_id=ctx.run_id, agent=agent.name, action=method, status="error",
                                  error=traceback.format_exc()[-2000:], dry_run=ctx.dry_run)
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(self.retry_delay_s * attempt)
                continue
            self._record(agent, "ok", attempt, report.bullets, report.data, None, started)
            return "ok"
        self._record(agent, "failed", MAX_ATTEMPTS, [], {}, last_error, started)
        agent.todo("erreur", f"Agent en échec : {agent.label}", last_error, ref=f"failed:{ctx.day}:{agent.name}:{ctx.phase}")
        return "failed"

    def _record(self, agent, status, attempts, bullets, data, error, started) -> None:
        ctx = self.ctx
        ctx.db.insert("agent_runs", {
            "run_id": ctx.run_id, "day": ctx.day, "agent": agent.name, "phase": ctx.phase, "status": status, "attempts": attempts,
            "bullets": json.dumps(bullets, ensure_ascii=False),
            "data": json.dumps({k: v for k, v in (data or {}).items() if k != "html"}, ensure_ascii=False, default=str),
            "error": error, "started": started, "finished": now_iso(), "dry_run": int(ctx.dry_run)})

    # -- phases --------------------------------------------------------------------------------
    async def _guard_start(self) -> bool:
        ctx = self.ctx
        try:
            ctx.guard.check_paid_ads_disabled()
        except GuardrailError as exc:
            ctx.db.add_todo(day=ctx.day, category="erreur", title="Configuration publicité refusée", details=str(exc),
                            ref=f"paid_ads:{ctx.day}", dry_run=ctx.dry_run)
            await send_failure_alert(ctx, str(exc))
            return False
        if ctx.cfg.kill_switch:
            n = SocialPublisherAgent(ctx).cancel_all("kill switch activé")
            ctx.db.log_action(day=ctx.day, run_id=ctx.run_id, agent="orchestrator", action="kill_switch",
                              result={"posts_cancelled": n}, dry_run=ctx.dry_run)
            return False
        return True

    async def morning(self) -> dict[str, str]:
        ctx = self.ctx
        ctx.phase = "morning"
        if not await self._guard_start():
            return {"orchestrator": "stopped"}
        results = {}
        sequence: list[BaseAgent] = [ProductResearchAgent(ctx), CatalogAgent(ctx), AdVisualsAgent(ctx), AdCopyAgent(ctx),
                                     SocialPublisherAgent(ctx), OrdersAgent(ctx), CustomerServiceAgent(ctx),
                                     AnalyticsAgent(ctx, target_day=ctx.day_offset(-1))]
        for agent in sequence:
            results[agent.name] = await self.run_agent(agent)
        await self._alert_if_all_failed(results)
        return results

    async def publish(self, now: datetime | None = None) -> dict[str, str]:
        ctx = self.ctx
        ctx.phase = "publish"
        if not await self._guard_start():
            return {"orchestrator": "stopped"}
        res = {"social_publisher": await self.run_agent(SocialPublisherAgent(ctx), "publish_due", now=now)}
        await self._alert_if_all_failed(res)
        return res

    async def evening(self) -> dict[str, str]:
        ctx = self.ctx
        ctx.phase = "evening"
        results = {}
        if not ctx.cfg.kill_switch:
            results["analytics"] = await self.run_agent(AnalyticsAgent(ctx, target_day=ctx.day))
        results["reporting"] = await self.run_agent(ReportingAgent(ctx))
        if results["reporting"] != "ok":
            await send_failure_alert(ctx, "L'e-mail bilan n'a pas pu être généré : voir le journal (table agent_runs).")
        return results

    async def full_day(self) -> dict[str, Any]:
        """Journée complète (utilisée en simulation) : matin → 2 créneaux → soir."""
        ctx = self.ctx
        out: dict[str, Any] = {"morning": await self.morning()}
        for slot in ctx.cfg.get("schedule.publish_slots", ["12:30", "18:30"]):
            h, m = (int(x) for x in slot.split(":"))
            when = datetime.fromisoformat(ctx.day).replace(hour=h, minute=m, tzinfo=ctx.tz)
            out[f"publish_{slot}"] = await self.publish(now=when)
        out["evening"] = await self.evening()
        return out

    async def _alert_if_all_failed(self, results: dict[str, str]) -> None:
        if results and all(v == "failed" for v in results.values()):
            errors = self.ctx.db.query("SELECT agent, error FROM agent_runs WHERE run_id = ? AND status = 'failed'", [self.ctx.run_id])
            await send_failure_alert(self.ctx, "\n".join(f"{e['agent']}: {e['error']}" for e in errors))
