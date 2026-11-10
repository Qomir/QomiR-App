"""Planificateur (APScheduler, équivalent cron intégré au conteneur).

Chaque jour : choisit `posts_per_day` créneaux parmi ceux de la niche (le bandit favorise
les heures qui performent), fabrique chaque vidéo `lead_minutes` avant son créneau, la
publie à l'heure, collecte les stats la nuit et envoie le bilan le soir.
L'état vit dans SQLite : un redémarrage du conteneur ne perd ni ne double rien.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, learn, log, notify, pipeline, publisher, stats
from .config import load
from .publish import oauth

L = log.get("scheduler")


def _safe(name: str, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # un job en échec ne doit jamais arrêter le planificateur
        L.exception("Job %s en échec", name)
        notify.error(name, e)


def todays_slots(tz: ZoneInfo) -> list[str]:
    cfg = load()
    today = datetime.now(tz).date().isoformat()
    plan = db.kv_get("slot_plan", {})
    if plan.get("date") != today:
        pool = list(cfg["niche"]["slots"])
        n = max(1, min(cfg["schedule"]["posts_per_day"], len(pool), 4))
        chosen = []
        while len(chosen) < n:
            s = learn.choose("slot", pool)
            chosen.append(s)
            pool.remove(s)
        plan = {"date": today, "slots": sorted(chosen)}
        db.kv_set("slot_plan", plan)
        L.info("Créneaux du jour : %s", plan["slots"])
    return plan["slots"]


def produce_job(slot: str) -> None:
    cfg = load()
    tz = ZoneInfo(cfg["niche"]["timezone"])
    if slot not in todays_slots(tz):
        return
    h, m = map(int, slot.split(":"))
    now = datetime.now(tz)
    when = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if when < now - timedelta(minutes=5):
        when += timedelta(days=1)  # créneau de 00:xx fabriqué la veille au soir
    when += timedelta(minutes=random.randint(0, cfg["schedule"]["jitter_minutes"]))
    key = f"produced:{when.date().isoformat()}:{slot}"
    if db.kv_get(key):
        return  # déjà fait (redémarrage du conteneur)
    db.kv_set(key, True)
    pipeline.produce(slot=slot, scheduled_at=when.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds"))


def run() -> None:
    cfg = load()
    niche, sch = cfg["niche"], cfg["schedule"]
    tz = ZoneInfo(niche["timezone"])
    s = BlockingScheduler(timezone=tz, job_defaults={"coalesce": True, "max_instances": 1,
                                                     "misfire_grace_time": 1800})
    for slot in niche["slots"]:
        h, m = map(int, slot.split(":"))
        start = (datetime(2000, 1, 1, h, m) - timedelta(minutes=sch["lead_minutes"]))
        s.add_job(_safe, CronTrigger(hour=start.hour, minute=start.minute, timezone=tz),
                  args=[f"production {slot}", produce_job, slot], id=f"produce-{slot}")
    s.add_job(_safe, "interval", minutes=1, args=["file de publication", publisher.process_queue],
              id="queue")
    h, m = map(int, sch["stats_time"].split(":"))
    s.add_job(_safe, CronTrigger(hour=h, minute=m, timezone=tz), args=["stats", stats.collect], id="stats")
    h, m = map(int, sch["report_time"].split(":"))
    s.add_job(_safe, CronTrigger(hour=h, minute=m, timezone=tz), args=["bilan", stats.daily_report],
              id="report")
    s.add_job(_safe, CronTrigger(hour=3, minute=10, timezone=tz),
              args=["jeton Instagram", oauth.instagram_refresh], id="ig-refresh")

    notify.send(f"🚀 Autopilot démarré — niche {niche['name']}, mode {cfg['mode'].upper()}, "
                f"{sch['posts_per_day']} vidéos/jour, créneaux {todays_slots(tz)} ({niche['timezone']}), "
                f"validation : {cfg['approval']['mode']}")
    s.start()
