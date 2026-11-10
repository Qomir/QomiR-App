"""Instagram Graph API (officielle) : publication de Reels par envoi résumable
(aucun hébergement public nécessaire) + insights.

Prérequis : compte Instagram PROFESSIONNEL (Créateur ou Business), permission
instagram_business_content_publish (+ instagram_business_manage_insights pour les stats).
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .. import log
from ..config import load
from . import oauth

L = log.get("instagram")


def _base() -> str:
    return f"https://graph.instagram.com/{load()['platforms']['instagram']['api_version']}"


def _check(r: requests.Response, what: str) -> dict:
    data = r.json() if r.content else {}
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"Instagram {what} : {data.get('error', {}).get('message', r.text[:300])}")
    return data


def upload(video: Path, cap: dict) -> dict:
    cfg = load()
    pcfg = cfg["platforms"]["instagram"]
    token, user_id = oauth.instagram_token()
    auth = {"Authorization": f"Bearer {token}"}

    # Quota de publication (fenêtre glissante de 24 h) : on vérifie avant d'envoyer
    q = requests.get(f"{_base()}/{user_id}/content_publishing_limit", headers=auth, timeout=30,
                     params={"fields": "quota_usage,config"}).json().get("data", [{}])[0]
    if q and q.get("quota_usage", 0) >= q.get("config", {}).get("quota_total", 50):
        raise RuntimeError("Quota de publication Instagram atteint pour 24 h")

    params = {"media_type": "REELS", "upload_type": "resumable", "caption": cap["caption"],
              "share_to_feed": str(pcfg["share_to_feed"]).lower()}
    warning = None
    if cfg["ai_disclosure"]["instagram_ai_flag"]:
        params["is_ai_generated"] = "true"  # étiquette « AI info » (paramètre ajouté par Meta en 2026)
    r = requests.post(f"{_base()}/{user_id}/media", headers=auth, data=params, timeout=60)
    if r.status_code != 200 and "is_ai_generated" in r.text:
        # Version d'API trop ancienne pour ce paramètre : la mention reste présente en légende
        params.pop("is_ai_generated")
        warning = ("Instagram a refusé le paramètre is_ai_generated (mettez à jour api_version) : "
                   "mention IA présente en légende uniquement.")
        r = requests.post(f"{_base()}/{user_id}/media", headers=auth, data=params, timeout=60)
    container = _check(r, "création du conteneur")
    cid = container["id"]
    uri = container.get("uri") or \
        f"https://rupload.facebook.com/ig-api-upload/{pcfg['api_version']}/{cid}"

    size = video.stat().st_size
    with open(video, "rb") as f:
        r = requests.post(uri, data=f, timeout=1800, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    _check(r, "envoi du fichier")

    for _ in range(60):  # encodage côté Instagram
        time.sleep(5)
        st = _check(requests.get(f"{_base()}/{cid}", headers=auth, timeout=30,
                                 params={"fields": "status_code,status"}), "statut")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram a refusé la vidéo : {st.get('status')}")
    else:
        raise RuntimeError("Instagram : encodage toujours en cours après 5 minutes")

    media = _check(requests.post(f"{_base()}/{user_id}/media_publish", headers=auth,
                                 data={"creation_id": cid}, timeout=60), "publication")
    link = requests.get(f"{_base()}/{media['id']}", headers=auth, timeout=30,
                        params={"fields": "permalink"}).json().get("permalink", "")
    out = {"remote_id": media["id"], "url": link}
    if warning:
        out["warning"] = warning
    return out


def stats(media_ids: list[str]) -> dict[str, dict]:
    token, _ = oauth.instagram_token()
    out = {}
    for mid in media_ids:
        try:
            r = requests.get(f"{_base()}/{mid}/insights", timeout=30,
                             headers={"Authorization": f"Bearer {token}"},
                             params={"metric": "views,likes,comments,shares,ig_reels_avg_watch_time"})
            vals = {d["name"]: d["values"][0]["value"] for d in _check(r, "insights")["data"]}
            avg_ms = vals.get("ig_reels_avg_watch_time")
            out[mid] = {"views": vals.get("views", 0), "likes": vals.get("likes", 0),
                        "comments": vals.get("comments", 0), "shares": vals.get("shares", 0),
                        "avg_view_sec": avg_ms / 1000 if avg_ms else None, "avg_view_pct": None}
        except Exception as e:
            L.warning("Insights Instagram %s : %s", mid, e)
    return out
