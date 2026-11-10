"""TikTok Content Posting API (officielle).

Deux modes (config `platforms.tiktok.mode`) :
- direct : Direct Post (scope video.publish). Tant que l'app n'a pas passé l'AUDIT TikTok,
  les vidéos sont forcées en privé (SELF_ONLY) et le compte doit être privé.
- inbox  : envoi en brouillon (scope video.upload) ; vous finalisez dans l'app TikTok.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .. import log
from ..config import load
from . import oauth

L = log.get("tiktok")
API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024  # 10 Mo (TikTok : 5 à 64 Mo par morceau, le dernier absorbe le reste)


def _post(path: str, body: dict | None = None, params: dict | None = None) -> dict:
    r = requests.post(f"{API}{path}", json=body or {}, params=params, timeout=60, headers={
        "Authorization": f"Bearer {oauth.tiktok_token()}",
        "Content-Type": "application/json; charset=UTF-8"})
    data = r.json() if r.content else {}
    err = data.get("error", {})
    if r.status_code != 200 or err.get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok {path} : {err.get('code')} — {err.get('message')}")
    return data.get("data", {})


def upload(video: Path, cap: dict) -> dict:
    cfg = load()
    pcfg = cfg["platforms"]["tiktok"]
    size = video.stat().st_size
    if size <= 64 * 1024 * 1024:
        chunk, count = size, 1
    else:
        chunk, count = CHUNK, size // CHUNK
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
              "total_chunk_count": count}
    warning = None

    if pcfg["mode"] == "inbox":
        init = _post("/post/publish/inbox/video/init/", {"source_info": source})
    else:
        # Obligatoire avant chaque Direct Post : options autorisées pour ce créateur
        info = _post("/post/publish/creator_info/query/")
        options = info.get("privacy_level_options", [])
        privacy = pcfg["privacy"]
        if privacy not in options:
            warning = (f"TikTok n'autorise pas « {privacy} » (options : {options}). Publiée en "
                       "privé : l'app n'est probablement pas encore auditée.")
            privacy = "SELF_ONLY"
        if info.get("max_video_post_duration_sec", 600) < 75:
            L.warning("Durée max autorisée pour ce compte : %ss", info["max_video_post_duration_sec"])
        init = _post("/post/publish/video/init/", {
            "post_info": {"title": cap["caption"], "privacy_level": privacy,
                          "disable_duet": bool(info.get("duet_disabled", False)),
                          "disable_stitch": bool(info.get("stitch_disabled", False)),
                          "disable_comment": bool(info.get("comment_disabled", False)),
                          "brand_content_toggle": False, "brand_organic_toggle": False,
                          # Étiquette « Creator labeled as AI-generated »
                          "is_aigc": bool(cfg["ai_disclosure"]["tiktok_aigc_flag"])},
            "source_info": source})

    with open(video, "rb") as f:
        for i in range(count):
            start = i * chunk
            data = f.read() if i == count - 1 else f.read(chunk)
            end = start + len(data) - 1
            r = requests.put(init["upload_url"], data=data, timeout=900, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(data)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if r.status_code not in (201, 206):
                raise RuntimeError(f"TikTok envoi morceau {i + 1}/{count} : HTTP {r.status_code} {r.text[:200]}")

    publish_id = init["publish_id"]
    for _ in range(40):  # traitement côté TikTok : jusqu'à ~5 min
        time.sleep(8)
        st = _post("/post/publish/status/fetch/", {"publish_id": publish_id})
        status = st.get("status")
        if status == "FAILED":
            raise RuntimeError(f"TikTok a refusé la vidéo : {st.get('fail_reason')}")
        if status == "SEND_TO_USER_INBOX":
            return {"remote_id": publish_id, "url": "",
                    "warning": "Brouillon envoyé dans votre boîte TikTok : ouvrez l'app pour publier."}
        if status == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or []  # (sic : orthographe de l'API)
            remote = str(ids[0]) if ids else publish_id
            out = {"remote_id": remote, "url": ""}
            if warning:
                out["warning"] = warning
            return out
    raise RuntimeError("TikTok : traitement toujours en cours après 5 minutes")


def stats(posts: list[dict]) -> dict[str, dict]:
    """posts = [{remote_id, title}]. Associe par id, sinon par début de légende."""
    out: dict[str, dict] = {}
    cursor, pages = None, 0
    fields = "id,title,view_count,like_count,comment_count,share_count"
    videos = []
    while pages < 5:
        body = {"max_count": 20, **({"cursor": cursor} if cursor else {})}
        data = _post("/video/list/", body, params={"fields": fields})
        videos += data.get("videos", [])
        pages += 1
        if not data.get("has_more"):
            break
        cursor = data.get("cursor")
    for p in posts:
        match = next((v for v in videos if str(v["id"]) == p["remote_id"]), None) or \
                next((v for v in videos if p["title"] and (v.get("title") or "").startswith(p["title"][:40])), None)
        if match:
            out[p["remote_id"]] = {"views": match.get("view_count", 0), "likes": match.get("like_count", 0),
                                   "comments": match.get("comment_count", 0),
                                   "shares": match.get("share_count", 0),
                                   "avg_view_pct": None, "avg_view_sec": None}  # non fourni par l'API
    return out
