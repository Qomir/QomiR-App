import pytest

from core.guardrails import BudgetExceeded, GuardrailError, KillSwitchActive


def test_budget_daily_cap_blocks_spend(make_ctx):
    ctx = make_ctx()
    ctx.db.add_cost(day=ctx.day, agent="t", provider="fal", kind="image", amount_eur=4.95, dry_run=True)
    ctx.guard.authorize_spend(0.05, "ok")          # pile au plafond : autorisé
    with pytest.raises(BudgetExceeded):
        ctx.guard.authorize_spend(0.06, "trop")


def test_budget_monthly_cap(make_ctx):
    ctx = make_ctx(overrides={"budgets": {"api_monthly_eur": 10, "api_daily_eur": 50}})
    ctx.db.add_cost(day="2026-11-02", agent="t", provider="claude", kind="llm", amount_eur=9.99, dry_run=True)
    with pytest.raises(BudgetExceeded):
        ctx.guard.authorize_spend(0.5, "mensuel")
    assert ctx.guard.remaining_eur() == pytest.approx(0.01)


def test_kill_switch_blocks_any_spend(make_ctx):
    ctx = make_ctx(overrides={"kill_switch": True})
    with pytest.raises(KillSwitchActive):
        ctx.guard.authorize_spend(0.01, "x")


def test_paid_ads_must_stay_disabled(make_ctx):
    ctx = make_ctx()
    ctx.guard.check_paid_ads_disabled()
    ctx.cfg.raw["paid_ads"]["daily_budget_eur"] = 10
    with pytest.raises(GuardrailError):
        ctx.guard.check_paid_ads_disabled()
    ctx.cfg.raw["paid_ads"]["daily_budget_eur"] = 0


@pytest.mark.parametrize("title", ["Kit manucure électrique", "Pinceaux de maquillage pro", "Lisseur à cheveux", "Recourbe-cils", "Faux ongles adhésifs"])
def test_beauty_products_refused(make_ctx, title):
    ctx = make_ctx()
    with pytest.raises(GuardrailError):
        ctx.guard.check_product_candidate({"title": title, "purchase_price_eur": 30})


def test_tool_products_accepted_and_price_range(make_ctx):
    ctx = make_ctx()
    ctx.guard.check_product_candidate({"title": "Spatule d'ouverture et kit de réparation", "purchase_price_eur": 25})
    for price in (19.99, 60.01):
        with pytest.raises(GuardrailError):
            ctx.guard.check_product_candidate({"title": "Loupe d'établi", "purchase_price_eur": price})


def test_listing_requires_photos_and_legal_mentions(make_ctx):
    ctx = make_ctx()
    ok, problems = ctx.guard.listing_publishable({"title": "X", "images": [], "description_html": "<p>super</p>"})
    assert not ok and "aucune photo" in problems and len(problems) == 4
    body = "".join(ctx.guard.legal_mentions())
    ok, problems = ctx.guard.listing_publishable({"title": "X", "images": ["u"], "description_html": body})
    assert ok, problems


@pytest.mark.parametrize("text", ["Plus que 2 en stock !", "Stock limité, foncez", "-50% aujourd'hui", "Au lieu de 79 €",
                                  "Compatible iPhone et Switch", "Le meilleur du monde", "Garanti à vie"])
def test_forbidden_copy_detected(make_ctx, text):
    assert make_ctx().guard.copy_violations(text)


def test_clean_copy_passes(make_ctx):
    assert make_ctx().guard.copy_violations("Le couple réglable serre juste ce qu'il faut. Lien en bio.") == []


def test_on_image_text_max_7_words(make_ctx):
    ctx = make_ctx()
    ctx.guard.check_on_image_text("La précision, sans forcer.")
    with pytest.raises(GuardrailError):
        ctx.guard.check_on_image_text("un deux trois quatre cinq six sept huit")
