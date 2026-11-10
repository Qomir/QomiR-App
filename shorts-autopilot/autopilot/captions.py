"""Titre / légende / hashtags adaptés à chaque plateforme, avec mention IA et source."""
from __future__ import annotations

from .config import load


def _tags(script: dict, n: int) -> list[str]:
    niche = load()["niche"]
    seen, out = set(), []
    for h in list(script.get("hashtags", [])) + list(niche.get("base_hashtags", [])):
        h = h.strip("# ").replace(" ", "")
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:n]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def build(script: dict, topic: dict) -> dict:
    cfg = load()
    niche, ai = cfg["niche"], cfg["ai_disclosure"]
    title = script["title"].strip()
    desc = script.get("description", "").strip()
    source = f"{niche['source_label']} {topic['url']}" if topic.get("url") else ""
    notice = niche["ai_notice"] if ai["caption_notice"] else ""
    disclaimer = niche.get("disclaimer", "")
    extras = "\n".join(x for x in (source, disclaimer, notice) if x)

    yt_tags = _tags(script, 8)
    return {
        "youtube": {
            "title": _cut(title, 95),
            "description": _cut(f"{desc}\n\n{extras}\n\n" + " ".join(f"#{t}" for t in yt_tags[:3]), 4900),
            "tags": yt_tags,
            "category_id": str(niche.get("youtube_category_id", 27)),
            "language": niche["language"],
        },
        # TikTok : légende courte, 3-5 hashtags ciblés (le reste est géré par l'étiquette IA native)
        "tiktok": {"caption": _cut(f"{title} " + " ".join(f"#{t}" for t in _tags(script, 5)), 2150)},
        "instagram": {"caption": _cut(
            f"{title}\n\n{desc}\n\n{extras}\n\n" + " ".join(f"#{t}" for t in _tags(script, 5)), 2150)},
    }
