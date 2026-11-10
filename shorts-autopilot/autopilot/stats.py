"""Collecte quotidienne des statistiques via les API officielles + bilan Telegram."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db, learn, log, notify
from .config import load
from .publish import instagram, tiktok, youtube

L = log.get("stats")


def collect() -> int:
    days = load()["learning"]["track_days"]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    posts = db.query("""SELECT p.video_id, p.platform, p.remote_id, v.title FROM posts p
                        JOIN videos v ON v.id = p.video_id
                        WHERE p.status = 'ok' AND p.published_at > ?""", (since,))
    by = {"youtube": [], "tiktok": [], "instagram": []}
    for p in posts:
        by[p["platform"]].append(p)
    n = 0
    fetchers = {
        "youtube": lambda ps: youtube.stats([p["remote_id"] for p in ps]),
        "tiktok": lambda ps: tiktok.stats([{"remote_id": p["remote_id"], "title": p["title"]} for p in ps]),
        "instagram": lambda ps: instagram.stats([p["remote_id"] for p in ps]),
    }
    for plat, ps in by.items():
        if not ps:
            continue
        try:
            data = fetchers[plat](ps)
        except Exception as e:
            notify.error(f"stats {plat}", e)
            continue
        for p in ps:
            s = data.get(p["remote_id"])
            if s:
                db.execute("INSERT OR REPLACE INTO stats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (p["video_id"], plat, db.now(), s["views"], s["likes"], s["comments"],
                            s["shares"], s["avg_view_pct"], s["avg_view_sec"]))
                n += 1
    L.info("Stats mises à jour : %d publications", n)
    learn.recompute()
    return n


def daily_report() -> str:
    day = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    vids = db.query("SELECT status, COUNT(*) c FROM videos WHERE created_at > ? GROUP BY status", (day,))
    counts = {r["status"]: r["c"] for r in vids}
    errors = db.query("SELECT platform, error FROM posts WHERE status = 'error' AND published_at > ?", (day,))
    totals = db.query("""SELECT platform, COUNT(*) n, SUM(views) v, SUM(likes) l, SUM(shares) s,
                                AVG(avg_view_pct) r FROM stats GROUP BY platform""")
    top = db.query("""SELECT v.title, SUM(s.views) views FROM stats s JOIN videos v ON v.id = s.video_id
                      WHERE v.created_at > ? GROUP BY v.id ORDER BY views DESC LIMIT 3""",
                   ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),))
    lines = [f"📊 Bilan du jour ({load()['niche']['name']}, mode {load()['mode']})",
             "Vidéos 24 h : " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "aucune")]
    for t in totals:
        ret = f", rétention moy. {t['r']:.0f} %" if t["r"] else ""
        lines.append(f"• {t['platform']} : {t['v'] or 0} vues, {t['l'] or 0} likes, "
                     f"{t['s'] or 0} partages sur {t['n']} vidéos suivies{ret}")
    if top:
        lines.append("Top 7 jours : " + " | ".join(f"{r['title'][:40]} ({r['views']})" for r in top))
    best = learn.best()
    if best:
        lines.append("Ce qui marche : " + ", ".join(f"{d}={v[0]}" for d, v in best.items()))
    if errors:
        lines.append(f"⚠️ {len(errors)} échec(s) de publication : " +
                     "; ".join(f"{e['platform']}: {(e['error'] or '')[:60]}" for e in errors[:3]))
    text = "\n".join(lines)
    notify.send(text)
    return text
