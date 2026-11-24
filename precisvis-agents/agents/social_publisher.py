"""Agent Publication organique (remplace l'agent « Pubs » : AUCUNE campagne payante).

Matin  : choisit les meilleures créas validées du jour, leur associe une variante de texte
         (rotation A/B/C pour apprendre ce qui marche) et programme les posts aux créneaux
         de config.yaml → schedule.publish_slots.
Créneau : publie les posts arrivés à échéance sur la Page Facebook, Instagram (fil + Reels)
         et TikTok. Chaque publication est journalisée (avant/après, raison).
Kill switch : tous les posts en attente sont annulés et plus rien n'est publié.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from core.guardrails import KillSwitchActive
from tools.image_gen import download

from .base import AgentReport, BaseAgent


class SocialPublisherAgent(BaseAgent):
    name = "social_publisher"
    label = "Publication organique"

    # -- matin : planification ---------------------------------------------------------
    async def run(self) -> AgentReport:
        ctx = self.ctx
        if ctx.cfg.kill_switch:
            self.cancel_all("kill switch activé")
            raise KillSwitchActive("kill switch")
        ctx.guard.check_paid_ads_disabled()
        creatives = ctx.db.query("SELECT * FROM creatives WHERE day = ? AND status = 'ok' ORDER BY score DESC", [ctx.day])
        images = [c for c in creatives if c["kind"] == "image"]
        videos = [c for c in creatives if c["kind"] == "video"]
        social = ctx.cfg.get("social", {})
        wanted: list[tuple[str, str, list[dict[str, Any]], str, int]] = []
        if social.get("facebook", {}).get("enabled"):
            wanted.append(("facebook", "feed", images, "facebook/4x5", int(social["facebook"].get("posts_per_day", 0))))
        if social.get("instagram", {}).get("enabled"):
            wanted.append(("instagram", "feed", images, "instagram/4x5", int(social["instagram"].get("feed_per_day", 0))))
            wanted.append(("instagram", "reel", videos, "instagram/9x16", int(social["instagram"].get("reels_per_day", 0))))
        if social.get("tiktok", {}).get("enabled"):
            wanted.append(("tiktok", "video", videos, "tiktok/9x16", int(social["tiktok"].get("videos_per_day", 0))))

        already = {(p["creative_id"], p["platform"]) for p in ctx.db.query("SELECT creative_id, platform FROM posts WHERE day = ?", [ctx.day])}
        slots = ctx.cfg.get("schedule.publish_slots", ["12:30", "18:30"])
        planned = []
        for platform, placement, pool, fmt, n in wanted:
            chosen = [c for c in pool if (c["id"], platform) not in already and fmt in json.loads(c["files"] or "{}")][:n]
            for k, c in enumerate(chosen):
                slot = slots[k % len(slots)]
                copy = self._pick_copy(c["id"], platform)
                caption = self._caption(copy, platform, c["id"]) if copy else c["headline"]
                media = json.loads(c["files"])[fmt]
                media_url = ctx.tools.hosting.public_url(Path(media))   # hébergé dès maintenant pour les créneaux suivants
                ctx.db.insert("posts", {"day": ctx.day, "creative_id": c["id"], "platform": platform, "placement": placement,
                                        "copy_id": copy["id"] if copy else None, "caption": caption, "media_path": media,
                                        "media_url": media_url,
                                        "scheduled_at": f"{ctx.day}T{slot}:00", "status": "queued", "dry_run": int(ctx.dry_run)})
                planned.append(f"{platform}/{placement} {slot}")
        self.action("posts_planned", {"count": len(planned), "detail": planned})
        by_platform: dict[str, int] = {}
        for p in planned:
            by_platform[p.split("/")[0]] = by_platform.get(p.split("/")[0], 0) + 1
        detail = ", ".join(f"{k} {v}" for k, v in by_platform.items()) or "aucun"
        self.bullet(f"{len(planned)} publication(s) organique(s) programmée(s) aux créneaux {', '.join(slots)} ({detail}).")
        self.bullet("Aucune campagne payante : publicité payante désactivée par configuration.")
        self.report.data = {"planned": len(planned)}
        return self.report

    def _pick_copy(self, creative_id: str, platform: str) -> dict[str, Any] | None:
        n = self.ctx.db.one("SELECT COUNT(*) AS n FROM posts WHERE platform = ?", [platform])["n"]
        variant = "ABC"[n % 3]
        rows = self.ctx.db.query("SELECT * FROM copies WHERE creative_id = ? AND platform = ? ORDER BY variant", [creative_id, platform])
        if not rows:
            return None
        return next((r for r in rows if r["variant"] == variant), rows[0])

    def _caption(self, copy: dict[str, Any], platform: str, creative_id: str) -> str:
        tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in json.loads(copy["hashtags"] or "[]"))
        parts = [copy["hook"], copy["body"], copy["cta"]]
        if platform == "facebook":
            utm = urlencode({"utm_source": "facebook", "utm_medium": "social",
                             "utm_campaign": self.ctx.cfg.get("social.utm_campaign", "organique"), "utm_content": creative_id})
            parts.append(f"{self.ctx.cfg.get('store.url')}/products/{self.ctx.cfg.get('store.main_product_handle')}?{utm}")
        if platform == "tiktok":
            parts.append("Contenu créé avec l'aide de l'IA.")
        return "\n\n".join(p for p in parts if p) + ("\n\n" + tags if tags else "")

    # -- créneau : publication -------------------------------------------------------------
    async def publish_due(self, now: datetime | None = None) -> AgentReport:
        ctx = self.ctx
        if ctx.cfg.kill_switch:
            n = self.cancel_all("kill switch activé")
            self.bullet(f"Kill switch : {n} publication(s) annulée(s).")
            return self.report
        now = now or ctx.now()
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S")
        due = ctx.db.query("SELECT * FROM posts WHERE status = 'queued' AND scheduled_at <= ? ORDER BY scheduled_at", [stamp])
        ok, failed = 0, 0
        for post in due:
            if post["day"] < ctx.day:   # post de la veille jamais parti : on ne publie pas en retard
                ctx.db.update("posts", "id", post["id"], {"status": "cancelled", "error": "créneau dépassé"})
                continue
            try:
                res = self._publish(post)
            except Exception as exc:
                failed += 1
                ctx.db.update("posts", "id", post["id"], {"status": "failed", "error": str(exc)[:500]})
                self.action("publish", {"post": post["id"], "platform": post["platform"]}, status="error", error=str(exc))
                continue
            ok += 1
            ctx.db.update("posts", "id", post["id"], {"status": "published", "external_id": res["id"],
                                                      "permalink": res.get("permalink", ""), "published_at": stamp})
            self.action("publish", {"post": post["id"], "platform": post["platform"], "placement": post["placement"],
                                    "before": "queued", "after": "published", "external_id": res["id"],
                                    "reason": f"créneau {post['scheduled_at'][11:16]}"})
        if due:
            self.bullet(f"{ok} publication(s) en ligne" + (f", {failed} échec(s)" if failed else "") + f" (créneau {stamp[11:16]}).")
        self.report.data = {"published": ok, "failed": failed}
        return self.report

    def _publish(self, post: dict[str, Any]) -> dict[str, str]:
        tools = self.ctx.tools
        path = Path(post["media_path"])
        url = post.get("media_url") or tools.hosting.public_url(path)
        platform, placement, caption = post["platform"], post["placement"], post["caption"]
        if platform == "tiktok":
            privacy = self.ctx.cfg.get("social.tiktok.privacy_level", "SELF_ONLY")
            if not path.exists():   # autre machine que celle du matin : on récupère la vidéo hébergée
                path = download(url, self.ctx.cfg.output_dir / "tmp" / path.name)
            return tools.tiktok.publish_video(path, caption, privacy)
        if platform == "facebook":
            if placement == "feed" and path.suffix == ".mp4":
                return tools.meta.publish_facebook_video(url, caption)
            return tools.meta.publish_facebook_photo(url, caption)
        if platform == "instagram":
            if placement == "reel":
                return tools.meta.publish_instagram_reel(url, caption)
            return tools.meta.publish_instagram_image(url, caption)
        raise ValueError(f"plateforme inconnue : {platform}")

    def cancel_all(self, reason: str) -> int:
        rows = self.ctx.db.query("SELECT id FROM posts WHERE status = 'queued'")
        for r in rows:
            self.ctx.db.update("posts", "id", r["id"], {"status": "cancelled", "error": reason})
        if rows:
            self.action("cancel_all", {"count": len(rows), "reason": reason})
        return len(rows)
