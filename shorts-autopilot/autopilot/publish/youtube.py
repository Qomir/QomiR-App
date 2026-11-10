"""YouTube Data API v3 (officielle) : envoi résumable + statistiques (Data API + Analytics API)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

from .. import log
from ..config import load
from . import oauth

L = log.get("youtube")
API = "https://www.googleapis.com/youtube/v3"


class QuotaExceeded(RuntimeError):
    pass


def _raise(r: requests.Response, what: str):
    if r.status_code == 403 and "quota" in r.text.lower():
        raise QuotaExceeded("Quota YouTube du jour épuisé (remis à zéro à minuit, heure du Pacifique)")
    raise RuntimeError(f"YouTube {what} : HTTP {r.status_code} {r.text[:300]}")


def upload(video: Path, cap: dict) -> dict:
    cfg = load()
    token = oauth.youtube_token()
    body = {
        "snippet": {"title": cap["title"], "description": cap["description"], "tags": cap["tags"],
                    "categoryId": cap["category_id"], "defaultLanguage": cap["language"],
                    "defaultAudioLanguage": cap["language"]},
        "status": {"privacyStatus": cfg["platforms"]["youtube"]["privacy"],
                   "selfDeclaredMadeForKids": False,
                   # Déclaration « contenu modifié ou synthétique » exigée par YouTube
                   "containsSyntheticMedia": bool(cfg["ai_disclosure"]["youtube_synthetic_flag"])},
    }
    size = video.stat().st_size
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos",
                      params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={"Authorization": f"Bearer {token}",
                               "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(size)},
                      json=body, timeout=60)
    if r.status_code != 200:
        _raise(r, "init")
    with open(video, "rb") as f:
        r = requests.put(r.headers["Location"], data=f, timeout=1800,
                         headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    if r.status_code not in (200, 201):
        _raise(r, "envoi")
    res = r.json()
    out = {"remote_id": res["id"], "url": f"https://youtube.com/shorts/{res['id']}"}
    got = res.get("status", {}).get("privacyStatus")
    if got != body["status"]["privacyStatus"]:
        # Projet Google Cloud non audité : YouTube force « privé » (voir README §6)
        out["warning"] = (f"YouTube a forcé la visibilité « {got} » : votre projet API n'a pas "
                          "encore passé l'audit de conformité YouTube.")
    return out


def stats(video_ids: list[str]) -> dict[str, dict]:
    if not video_ids:
        return {}
    token = oauth.youtube_token()
    h = {"Authorization": f"Bearer {token}"}
    out: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        r = requests.get(f"{API}/videos", headers=h, timeout=30,
                         params={"part": "statistics", "id": ",".join(batch)})
        if r.status_code != 200:
            _raise(r, "stats")
        for it in r.json().get("items", []):
            s = it["statistics"]
            out[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                             "comments": int(s.get("commentCount", 0)), "shares": 0,
                             "avg_view_pct": None, "avg_view_sec": None}
    # Rétention et partages : YouTube Analytics API (données disponibles avec ~2 jours de délai)
    try:
        r = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=h, timeout=30,
                         params={"ids": "channel==MINE",
                                 "startDate": (date.today() - timedelta(days=60)).isoformat(),
                                 "endDate": date.today().isoformat(),
                                 "metrics": "views,averageViewDuration,averageViewPercentage,shares",
                                 "dimensions": "video", "filters": "video==" + ",".join(video_ids[:200])})
        if r.status_code == 200:
            for vid, _views, avd, avp, shares in r.json().get("rows", []):
                if vid in out:
                    out[vid].update(avg_view_sec=avd, avg_view_pct=avp, shares=int(shares))
        else:
            L.warning("YouTube Analytics : HTTP %s %s", r.status_code, r.text[:200])
    except Exception as e:
        L.warning("YouTube Analytics indisponible : %s", e)
    return out
