"""Contexte partagé par tous les agents pendant une exécution."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Config, load_brand
from .db import DB
from .guardrails import Guardrails
from .llm import LLM


@dataclass
class RunContext:
    cfg: Config
    db: DB
    guard: Guardrails
    llm: LLM
    tools: Any                 # tools.registry.Toolbox
    brand: dict[str, Any]
    day: str                   # AAAA-MM-JJ (heure de Paris)
    run_id: str
    dry_run: bool
    send_test_email: bool = False
    phase: str = "morning"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.cfg.get("store.timezone", "Europe/Paris"))

    def now(self) -> datetime:
        return datetime.now(self.tz)

    @property
    def date(self) -> date:
        return date.fromisoformat(self.day)

    def day_offset(self, n: int) -> str:
        return (self.date + timedelta(days=n)).isoformat()


def paris_today(cfg: Config) -> str:
    return datetime.now(ZoneInfo(cfg.get("store.timezone", "Europe/Paris"))).date().isoformat()


def build_context(cfg: Config, *, dry_run: bool, day: str | None = None, db: DB | None = None,
                  send_test_email: bool = False, phase: str = "morning") -> RunContext:
    from tools.registry import build_toolbox

    day = day or paris_today(cfg)
    db = db or DB(cfg.db_path if not dry_run else cfg.root / "data" / "precisvis_dryrun.db")
    guard = Guardrails(cfg, db, day, dry_run)
    llm = LLM(cfg, db, guard, day, dry_run)
    ctx = RunContext(cfg=cfg, db=db, guard=guard, llm=llm, tools=None, brand=load_brand(cfg), day=day,
                     run_id=f"{day}-{phase}-{uuid.uuid4().hex[:6]}", dry_run=dry_run,
                     send_test_email=send_test_email, phase=phase)
    ctx.tools = build_toolbox(ctx)
    return ctx
