"""Point d'entrée PrecisVis.

Exemples :
    python main.py day --dry-run                     # journée complète simulée, rien n'est dépensé ni envoyé
    python main.py day --dry-run --send-test-email   # idem, mais l'e-mail bilan de test part vraiment
    python main.py morning                           # 07:00 — agents du matin (réel)
    python main.py publish                           # 12:30 / 18:30 — publications programmées
    python main.py evening                           # 20:00 — analytics + e-mail bilan
    python main.py evening --only-at-paris-hour 20   # utilisé par GitHub Actions (gestion heure d'été/hiver)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.orchestrator import Orchestrator  # noqa: E402
from agents.reporting import send_failure_alert  # noqa: E402
from core.config import load_config  # noqa: E402
from core.context import build_context  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Système multi-agents PrecisVis")
    p.add_argument("phase", choices=["morning", "publish", "evening", "day"])
    p.add_argument("--dry-run", action="store_true", help="simulation : aucune dépense, aucune publication, aucun envoi")
    p.add_argument("--send-test-email", action="store_true", help="avec --dry-run : envoie réellement l'e-mail bilan de test")
    p.add_argument("--date", help="date simulée AAAA-MM-JJ (simulation uniquement)")
    p.add_argument("--only-at-paris-hour", type=int, help="ne rien faire si l'heure de Paris n'est pas celle-ci")
    p.add_argument("--scheduled-utc-hour", type=int,
                   help="heure UTC du cron qui a déclenché l'exécution (sert à --only-at-paris-hour malgré les retards GitHub)")
    p.add_argument("--config", help="chemin vers un autre config.yaml")
    p.add_argument("--fresh", action="store_true", help="avec --dry-run : repart d'une base de simulation vide")
    return p.parse_args(argv)


async def amain(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    tz = ZoneInfo(cfg.get("store.timezone", "Europe/Paris"))
    if args.only_at_paris_hour is not None:
        now_utc = datetime.now(timezone.utc)
        ref = now_utc.replace(hour=args.scheduled_utc_hour, minute=0) if args.scheduled_utc_hour is not None else now_utc
        if ref.astimezone(tz).hour != args.only_at_paris_hour:
            print(f"Ce déclenchement correspond à {ref.astimezone(tz):%H:%M} à Paris, pas {args.only_at_paris_hour}h : "
                  "rien à faire (doublon de cron heure d'été / heure d'hiver).")
            return 0
    if args.date and not args.dry_run:
        print("--date n'est autorisé qu'en simulation (--dry-run).")
        return 2
    if args.dry_run and args.fresh:
        (cfg.root / "data" / "precisvis_dryrun.db").unlink(missing_ok=True)

    ctx = build_context(cfg, dry_run=args.dry_run, day=args.date, send_test_email=args.send_test_email, phase=args.phase)
    orch = Orchestrator(ctx)
    try:
        if args.phase == "morning":
            result = await orch.morning()
        elif args.phase == "publish":
            result = await orch.publish()
        elif args.phase == "evening":
            result = await orch.evening()
        else:
            result = await orch.full_day()
    except Exception:  # échec complet de l'exécution → alerte immédiate
        err = traceback.format_exc()
        logging.getLogger("precisvis").error(err)
        await send_failure_alert(ctx, err)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.dry_run:
        print(f"\nSimulation terminée. Base : {ctx.db.path}\nE-mails simulés : {cfg.output_dir / 'reports' / ctx.day}")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    sys.exit(asyncio.run(amain(parse_args())))


if __name__ == "__main__":
    main()
