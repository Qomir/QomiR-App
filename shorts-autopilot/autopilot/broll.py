"""B-roll libres de droits via les API officielles gratuites Pexels et Pixabay.

Les clips sont choisis d'après la requête visuelle écrite par le LLM pour chaque
segment, mis en cache sur disque, et un même clip n'est pas réutilisé avant N jours.
Sans clé API (ou si rien n'est trouvé) : fond animé généré par FFmpeg.
"""
from __future__ import annotations

import random
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import db, log
from .config import CACHE_DIR, env, load

L = log.get("broll")
DIR = CACHE_DIR / "broll"
DIR.mkdir(parents=True, exist_ok=True)


def _pexels(query: str) -> list[dict]:
    key = env("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait", "per_page": 15,
                             "size": "medium"}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 1280]
        if not files or v.get("duration", 0) < 3:
            continue
        best = min(files, key=lambda f: abs((f.get("height") or 0) - 1920))
        out.append({"id": f"pexels_{v['id']}", "url": best["link"], "credit": v.get("url", "")})
    return out


def _pixabay(query: str) -> list[dict]:
    key = env("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/videos/", timeout=30,
                     params={"key": key, "q": query, "per_page": 15, "safesearch": "true"})
    r.raise_for_status()
    out = []
    for v in r.json().get("hits", []):
        f = v.get("videos", {}).get("large") or {}
        if not f.get("url") or (f.get("height") or 0) < 1080:
            f = v.get("videos", {}).get("medium") or {}
        if f.get("url") and v.get("duration", 0) >= 3:
            out.append({"id": f"pixabay_{v['id']}", "url": f["url"], "credit": v.get("pageURL", "")})
    return out


def _recently_used() -> set[str]:
    since = (datetime.now(timezone.utc) - timedelta(days=load()["broll"]["reuse_days"])).isoformat()
    return {r["asset_id"] for r in db.query(
        "SELECT asset_id FROM used_assets WHERE used_at > ?", (since,))}


def _download(item: dict) -> Path | None:
    dest = DIR / f"{item['id']}.mp4"
    if dest.exists():
        return dest
    try:
        with requests.get(item["url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            tmp.rename(dest)
        return dest
    except Exception as e:
        L.warning("Téléchargement B-roll raté (%s) : %s", item["id"], e)
        return None


def generated_background(seconds: float, seed: int) -> Path:
    """Fond dégradé animé (repli 100 % hors-ligne, aucun droit d'auteur)."""
    palettes = [("0x0f2027", "0x2c5364"), ("0x1a1a2e", "0x533483"), ("0x0b3d2e", "0x145a5a"),
                ("0x2b1055", "0x3a6073"), ("0x141e30", "0x35577d")]
    c0, c1 = palettes[seed % len(palettes)]
    dest = DIR / f"gen_{seed % len(palettes)}_{int(seconds) + 1}.mp4"
    if not dest.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"gradients=s=540x960:c0={c0}:c1={c1}:x0=0:y0=0:x1=540:y1=960:speed=0.015:"
             f"d={int(seconds) + 1}:r=30", "-vf", "scale=1080:1920,noise=alls=6:allf=t",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
             str(dest)], check=True)
    return dest


def clips_for(queries: list[str], count: int, taken: set[str]) -> list[tuple[str, Path]]:
    """Jusqu'à `count` clips pour la première requête qui donne des résultats.
    `taken` = ids déjà utilisés dans cette vidéo (pas deux fois le même plan)."""
    used = _recently_used() | taken
    providers = [p for p in (_pexels, _pixabay)]
    random.shuffle(providers) if load()["broll"]["shuffle_providers"] else None
    found: list[tuple[str, Path]] = []
    for q in queries:
        for provider in providers:
            try:
                items = provider(q)
            except Exception as e:
                L.warning("Recherche B-roll « %s » en échec : %s", q, e)
                continue
            fresh = [i for i in items if i["id"] not in used] or \
                    [i for i in items if i["id"] not in taken]
            random.shuffle(fresh)
            for item in fresh[: count - len(found)]:
                path = _download(item)
                if path:
                    found.append((item["id"], path))
                    taken.add(item["id"])
            if len(found) >= count:
                return found
        if found:
            return found
    return found


def mark_used(ids: list[str]) -> None:
    for i in ids:
        db.execute("INSERT OR REPLACE INTO used_assets VALUES (?, ?)", (i, db.now()))
