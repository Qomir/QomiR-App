"""File de publication : envoie les vidéos dues sur chaque plateforme activée, via les API
officielles uniquement, en respectant le mode de validation Telegram."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, log, notify
from .config import is_live, load
from .publish import instagram, tiktok, youtube

L = log.get("publisher")
UPLOADERS = {"youtube": youtube.upload, "tiktok": tiktok.upload, "instagram": instagram.upload}


def enabled_platforms() -> list[str]:
    return [p for p, c in load()["platforms"].items() if c.get("enabled")]


def publish_video(video_id: str, only: list[str] | None = None) -> bool:
    row = db.query("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not row:
        raise ValueError(f"Vidéo inconnue : {video_id}")
    row = row[0]
    meta = json.loads((Path(row["path"]).parent / "meta.json").read_text(encoding="utf-8"))
    done = {r["platform"] for r in db.query(
        "SELECT platform FROM posts WHERE video_id = ? AND status = 'ok'", (video_id,))}
    ok_any, lines = bool(done), []
    for plat in only or enabled_platforms():
        if plat in done:
            continue  # jamais deux fois la même vidéo sur une plateforme
        if plat == "youtube" and db.kv_get("yt_quota_day") == datetime.now(timezone.utc).date().isoformat():
            lines.append("⏸ youtube : quota du jour épuisé, reportée")
            continue
        try:
            res = UPLOADERS[plat](Path(row["path"]), meta["captions"][plat])
            db.execute("INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?, 'ok', NULL)",
                       (video_id, plat, res["remote_id"], res.get("url", ""), db.now()))
            ok_any = True
            lines.append(f"✅ {plat} {res.get('url', '')}".strip())
            if res.get("warning"):
                lines.append(f"   ⚠️ {res['warning']}")
        except youtube.QuotaExceeded as e:
            db.kv_set("yt_quota_day", datetime.now(timezone.utc).date().isoformat())
            lines.append(f"⏸ youtube : {e}")
        except Exception as e:
            L.exception("Publication %s en échec", plat)
            db.execute("INSERT OR REPLACE INTO posts VALUES (?, ?, NULL, NULL, ?, 'error', ?)",
                       (video_id, plat, db.now(), str(e)[:500]))
            lines.append(f"❌ {plat} : {e}")
    db.update_video(video_id, status="published" if ok_any else "failed")
    notify.send(f"📤 {row['title']}\n" + "\n".join(lines))
    return ok_any


def process_queue() -> None:
    """Appelée chaque minute : applique les décisions Telegram puis publie ce qui est dû."""
    for vid, decision in notify.poll_decisions():
        db.execute("UPDATE videos SET approval = ? WHERE id = ? AND status = 'queued'", (decision, vid))
        L.info("Décision Telegram : %s → %s", vid, decision)
    if not is_live():
        return
    mode = load()["approval"]["mode"]
    now = datetime.now(timezone.utc)
    for row in db.query("SELECT * FROM videos WHERE status = 'queued' ORDER BY scheduled_at"):
        due = datetime.fromisoformat(row["scheduled_at"])
        if row["approval"] == "rejected":
            db.update_video(row["id"], status="rejected")
            notify.send(f"⛔ Rejetée, non publiée : {row['title']}")
        elif now >= due + timedelta(hours=12):
            db.update_video(row["id"], status="expired")  # trop tard : l'actu n'est plus fraîche
            notify.send(f"⌛ Expirée sans validation, non publiée : {row['title']}")
        elif now >= due and (mode != "required" or row["approval"] == "approved"):
            publish_video(row["id"])
