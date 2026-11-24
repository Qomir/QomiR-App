"""Couche Claude Agent SDK.

Chaque agent appelle `LLM.ask(...)` avec :
- son prompt système (prompts/<agent>.md),
- une consigne,
- un schéma JSON de sortie (sortie structurée validée),
- éventuellement des outils intégrés (Read pour la vision, WebSearch/WebFetch pour la veille)
  ou des serveurs MCP (ex. Sume pour la génération d'images).

En mode simulation (`--dry-run`), aucun appel n'est fait : la fonction `mock` de l'agent
fournit une réponse réaliste et un coût estimé est journalisé (marqué « simulé »).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .guardrails import Guardrails

log = logging.getLogger("precisvis.llm")

# Estimation prudente d'un appel, utilisée par le garde-fou AVANT l'appel.
DEFAULT_CALL_ESTIMATE_EUR = 0.08


class LLMError(Exception):
    pass


class LLM:
    def __init__(self, cfg, db, guard: Guardrails, day: str, dry_run: bool):
        self.cfg = cfg
        self.db = db
        self.guard = guard
        self.day = day
        self.dry_run = dry_run
        self.prompts_dir = cfg.root / "prompts"

    def system_prompt(self, agent: str) -> str:
        common = (self.prompts_dir / "_common.md").read_text(encoding="utf-8")
        own = (self.prompts_dir / f"{agent}.md").read_text(encoding="utf-8")
        return common + "\n\n" + own

    async def ask(
        self,
        agent: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        mock: Callable[[], Any],
        tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        cwd: str | Path | None = None,
        estimate_eur: float = DEFAULT_CALL_ESTIMATE_EUR,
        simulated_cost_eur: float = 0.02,
        effort: str | None = None,
        system: str | None = None,
    ) -> dict[str, Any]:
        self.guard.authorize_spend(estimate_eur, f"appel Claude ({agent})")

        if self.dry_run:
            data = mock()
            self.db.add_cost(day=self.day, agent=agent, provider="claude", kind="llm",
                             amount_eur=simulated_cost_eur, dry_run=True)
            return data

        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        usd_to_eur = float(self.cfg.get("budgets.usd_to_eur", 0.92))
        remaining_usd = max(0.01, self.guard.remaining_eur() / usd_to_eur)
        tools = tools or []
        allowed = list(tools)
        if mcp_servers:
            allowed += [f"mcp__{name}" for name in mcp_servers]

        options = ClaudeAgentOptions(
            system_prompt=system or self.system_prompt(agent),
            model=self.cfg.get("llm.model", "claude-opus-5-5"),
            effort=effort or self.cfg.get("llm.effort", "medium"),
            tools=tools,                     # outils intégrés disponibles (liste vide = aucun)
            allowed_tools=allowed,
            mcp_servers=mcp_servers or {},
            permission_mode="bypassPermissions",  # tourne sans surveillance ; la liste d'outils est restreinte
            max_turns=int(self.cfg.get("llm.max_turns", 12)),
            max_budget_usd=remaining_usd,
            output_format={"type": "json_schema", "schema": schema},
            cwd=str(cwd) if cwd else str(self.cfg.root),
            setting_sources=[],              # n'hérite d'aucun réglage local
        )

        result: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result = message

        if result is None:
            raise LLMError(f"{agent} : aucune réponse de Claude")
        cost_eur = float(result.total_cost_usd or 0) * usd_to_eur
        self.db.add_cost(day=self.day, agent=agent, provider="claude", kind="llm", amount_eur=cost_eur, dry_run=False)
        if result.is_error:
            raise LLMError(f"{agent} : erreur Claude ({result.subtype}) {result.errors or ''}")

        data = result.structured_output
        if data is None and result.result:
            data = _extract_json(result.result)
        if data is None:
            raise LLMError(f"{agent} : sortie non structurée")
        return data


def _extract_json(text: str) -> Any:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
