import asyncio
import json

from agents.base import AgentReport, BaseAgent
from agents.orchestrator import MAX_ATTEMPTS, Orchestrator


class Flaky(BaseAgent):
    name = "flaky"
    label = "Flaky"

    def __init__(self, ctx, fail_times):
        super().__init__(ctx)
        self.fail_times, self.calls = fail_times, 0

    async def run(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("boom")
        self.bullet("fini")
        return self.report


def test_retries_then_success(make_ctx):
    ctx = make_ctx()
    agent = Flaky(ctx, fail_times=2)
    assert asyncio.run(Orchestrator(ctx).run_agent(agent)) == "ok"
    assert agent.calls == 3


def test_gives_up_after_3_attempts_and_reports(make_ctx):
    ctx = make_ctx()
    agent = Flaky(ctx, fail_times=10)
    assert asyncio.run(Orchestrator(ctx).run_agent(agent)) == "failed"
    assert agent.calls == MAX_ATTEMPTS
    assert any("Agent en échec" in t["title"] for t in ctx.db.open_todos())


def test_budget_exhausted_skips_spending_agent(make_ctx):
    ctx = make_ctx()
    ctx.db.add_cost(day=ctx.day, agent="t", provider="claude", kind="llm", amount_eur=99, dry_run=True)
    agent = Flaky(ctx, 0)
    agent.spends_money = True
    assert asyncio.run(Orchestrator(ctx).run_agent(agent)) == "skipped"
    assert agent.calls == 0


def test_full_simulated_day(make_ctx):
    ctx = make_ctx(day="2026-11-23")   # un lundi : propositions de produits
    result = asyncio.run(Orchestrator(ctx).full_day())
    assert all(v == "ok" for phase in result.values() for v in phase.values()), result
    # créas : 6 concepts dont 1 rejeté (simulation), 2 vidéos
    rows = ctx.db.query("SELECT kind, status FROM creatives")
    assert sum(r["kind"] == "image" and r["status"] == "ok" for r in rows) == 5
    assert sum(r["kind"] == "video" and r["status"] == "ok" for r in rows) == 2
    # produits : 2 brouillons créés, le produit beauté refusé
    assert len(ctx.tools.shopify.created) == 2
    assert all("ongle" not in p["title"].lower() for p in ctx.tools.shopify.created)
    # rien de payant, toutes les publications parties en organique
    posts = ctx.db.query("SELECT status FROM posts")
    assert posts and all(p["status"] == "published" for p in posts)
    # remboursement jamais envoyé seul, litige escaladé
    cats = {t["category"] for t in ctx.db.open_todos()}
    assert {"remboursement", "litige", "produit_brouillon"} <= cats
    # e-mail bilan : objet et 8 sections
    mail = ctx.tools.report_sender.sent[-1]
    assert "Bilan du 23/11" in mail["subject"] and "ventes" in mail["subject"]
    for title in ["1. La journée en bref", "2. Chiffres clés", "3. À traiter", "4. Ce que chaque agent a fait",
                  "5. Créas du jour", "6. Publications organiques", "7. Coûts du système", "8. Plan pour demain"]:
        assert title in mail["html"]
    assert len(mail["images"]) >= 5


def test_kill_switch_cancels_and_stops(make_ctx):
    ctx = make_ctx()
    orch = Orchestrator(ctx)
    asyncio.run(orch.morning())
    assert ctx.db.query("SELECT COUNT(*) n FROM posts WHERE status='queued'")[0]["n"] > 0
    ctx.cfg.raw["kill_switch"] = True
    try:
        assert asyncio.run(orch.publish()) == {"orchestrator": "stopped"}
        assert ctx.db.query("SELECT COUNT(*) n FROM posts WHERE status='queued'")[0]["n"] == 0
        assert ctx.db.query("SELECT COUNT(*) n FROM posts WHERE status='published'")[0]["n"] == 0
    finally:
        ctx.cfg.raw["kill_switch"] = False
