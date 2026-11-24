"""Meta Graph API : publication ORGANIQUE (Page Facebook + compte Instagram professionnel),
statistiques des posts, et Bibliothèque publicitaire (veille concurrentielle, lecture seule).

Aucun appel à la Marketing API (campagnes payantes) n'existe dans ce fichier.
Permissions : pages_manage_posts, pages_read_engagement, read_insights,
instagram_basic, instagram_content_publish, instagram_manage_insights ;
Bibliothèque publicitaire : identité vérifiée sur facebook.com/ID + accès à l'API Ad Library.
"""
from __future__ import annotations

import time
from typing import Any

from .http import ApiError, request

GRAPH = "https://graph.facebook.com/v23.0"


class MetaClient:
    def __init__(self, page_id: str | None, page_token: str | None, ig_user_id: str | None,
                 ad_library_token: str | None = None):
        self.page_id = page_id
        self.token = page_token
        self.ig = ig_user_id
        self.ad_library_token = ad_library_token or page_token

    def _get(self, path: str, params: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        return request("meta", "GET", f"{GRAPH}/{path}", params={**params, "access_token": token or self.token}).json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return request("meta", "POST", f"{GRAPH}/{path}", data={**data, "access_token": self.token}).json()

    # -- Facebook ---------------------------------------------------------------
    def publish_facebook_photo(self, image_url: str, message: str) -> dict[str, str]:
        res = self._post(f"{self.page_id}/photos", {"url": image_url, "message": message, "published": "true"})
        post_id = res.get("post_id") or res["id"]
        return {"id": post_id, "permalink": f"https://www.facebook.com/{post_id}"}

    def publish_facebook_video(self, video_url: str, description: str) -> dict[str, str]:
        res = self._post(f"{self.page_id}/videos", {"file_url": video_url, "description": description})
        return {"id": res["id"], "permalink": f"https://www.facebook.com/{res['id']}"}

    def facebook_post_metrics(self, post_id: str) -> dict[str, int]:
        data = self._get(post_id, {"fields": "reactions.summary(true).limit(0),comments.summary(true).limit(0),shares"})
        metrics = {
            "likes": data.get("reactions", {}).get("summary", {}).get("total_count", 0),
            "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
            "shares": data.get("shares", {}).get("count", 0),
        }
        try:
            ins = self._get(f"{post_id}/insights", {"metric": "post_impressions_unique,post_clicks"})
            for item in ins.get("data", []):
                key = {"post_impressions_unique": "views", "post_clicks": "clicks"}.get(item["name"])
                if key:
                    metrics[key] = item["values"][0]["value"]
        except ApiError:
            pass  # certaines métriques ne sont plus exposées selon la version de l'API
        return metrics

    # -- Instagram ----------------------------------------------------------------
    def _wait_container(self, container_id: str, timeout_s: int = 300) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            status = self._get(container_id, {"fields": "status_code"}).get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ApiError("instagram", None, f"conteneur {container_id} : {status}")
            time.sleep(8)
        raise ApiError("instagram", None, "délai dépassé pour le traitement de la vidéo")

    def publish_instagram_image(self, image_url: str, caption: str) -> dict[str, str]:
        container = self._post(f"{self.ig}/media", {"image_url": image_url, "caption": caption})["id"]
        self._wait_container(container, 120)
        media_id = self._post(f"{self.ig}/media_publish", {"creation_id": container})["id"]
        link = self._get(media_id, {"fields": "permalink"}).get("permalink", "")
        return {"id": media_id, "permalink": link}

    def publish_instagram_reel(self, video_url: str, caption: str) -> dict[str, str]:
        container = self._post(f"{self.ig}/media", {"media_type": "REELS", "video_url": video_url,
                                                     "caption": caption, "share_to_feed": "true"})["id"]
        self._wait_container(container)
        media_id = self._post(f"{self.ig}/media_publish", {"creation_id": container})["id"]
        link = self._get(media_id, {"fields": "permalink"}).get("permalink", "")
        return {"id": media_id, "permalink": link}

    def instagram_media_metrics(self, media_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        try:
            ins = self._get(f"{media_id}/insights", {"metric": "reach,views,likes,comments,shares,saved"})
            names = {"reach": "reach", "views": "views", "likes": "likes", "comments": "comments",
                     "shares": "shares", "saved": "saves"}
            for item in ins.get("data", []):
                if item["name"] in names:
                    out[names[item["name"]]] = item["values"][0]["value"]
        except ApiError:
            data = self._get(media_id, {"fields": "like_count,comments_count"})
            out = {"likes": data.get("like_count", 0), "comments": data.get("comments_count", 0)}
        return out

    # -- Bibliothèque publicitaire (veille, lecture seule) -----------------------------
    def ad_library_search(self, terms: str, country: str = "FR", limit: int = 40) -> list[dict[str, Any]]:
        data = self._get("ads_archive", {
            "search_terms": terms, "ad_reached_countries": f'["{country}"]', "ad_active_status": "ACTIVE",
            "ad_type": "ALL", "limit": limit,
            "fields": "page_name,ad_creative_bodies,ad_creative_link_titles,ad_delivery_start_time,"
                      "ad_snapshot_url,publisher_platforms",
        }, token=self.ad_library_token)
        return data.get("data", [])
