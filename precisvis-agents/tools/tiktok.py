"""TikTok Content Posting API (publication organique) + Display API (statistiques).

Scopes : video.publish, video.list, user.info.basic.
Tant que l'application n'a pas passé l'audit TikTok, les vidéos ne peuvent être
publiées qu'en privé (SELF_ONLY) — voir config.yaml → social.tiktok.privacy_level.
Le jeton d'accès expire après 24 h : il est renouvelé à chaque exécution avec le
refresh token (valable 1 an), et le nouveau refresh token est conservé dans la base.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .http import ApiError, request

API = "https://open.tiktokapis.com/v2"


class TikTokClient:
    def __init__(self, client_key: str, client_secret: str, refresh_token: str,
                 save_refresh_token: Callable[[str], None]):
        self.client_key = client_key
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.save_refresh_token = save_refresh_token
        self._access: str | None = None

    def _token(self) -> str:
        if self._access:
            return self._access
        resp = request("tiktok", "POST", f"{API}/oauth/token/", data={
            "client_key": self.client_key, "client_secret": self.client_secret,
            "grant_type": "refresh_token", "refresh_token": self.refresh_token,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
        if "access_token" not in resp:
            raise ApiError("tiktok", None, f"renouvellement du jeton impossible : {resp}")
        self._access = resp["access_token"]
        if resp.get("refresh_token") and resp["refresh_token"] != self.refresh_token:
            self.refresh_token = resp["refresh_token"]
            self.save_refresh_token(self.refresh_token)
        return self._access

    def _post(self, path: str, body: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = request("tiktok", "POST", f"{API}/{path}", params=params, json=body,
                       headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json; charset=UTF-8"}).json()
        err = resp.get("error", {})
        if err.get("code") not in (None, "ok"):
            raise ApiError("tiktok", None, f"{err.get('code')}: {err.get('message')}")
        return resp.get("data", {})

    def publish_video(self, path: Path, caption: str, privacy_level: str) -> dict[str, str]:
        size = path.stat().st_size
        data = self._post("post/publish/video/init/", {
            "post_info": {"title": caption[:2200], "privacy_level": privacy_level,
                          "disable_comment": False, "disable_duet": False, "disable_stitch": False,
                          "is_aigc": True},   # contenu généré par IA : étiquetage obligatoire
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
        })
        with open(path, "rb") as fh:
            request("tiktok-upload", "PUT", data["upload_url"], content=fh.read(), timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"})
        publish_id = data["publish_id"]
        post_id = self._wait_publish(publish_id)
        return {"id": post_id or publish_id, "permalink": ""}

    def _wait_publish(self, publish_id: str, timeout_s: int = 300) -> str | None:
        start = time.time()
        while time.time() - start < timeout_s:
            st = self._post("post/publish/status/fetch/", {"publish_id": publish_id})
            if st.get("status") == "PUBLISH_COMPLETE":
                ids = st.get("publicaly_available_post_id") or []
                return str(ids[0]) if ids else None
            if st.get("status") == "FAILED":
                raise ApiError("tiktok", None, f"publication échouée : {st.get('fail_reason')}")
            time.sleep(10)
        return None

    def video_metrics(self, video_ids: list[str]) -> dict[str, dict[str, int]]:
        if not video_ids:
            return {}
        data = self._post("video/query/", {"filters": {"video_ids": video_ids[:20]}},
                          params={"fields": "id,view_count,like_count,comment_count,share_count"})
        return {v["id"]: {"views": v.get("view_count", 0), "likes": v.get("like_count", 0),
                          "comments": v.get("comment_count", 0), "shares": v.get("share_count", 0)}
                for v in data.get("videos", [])}
