"""Veille de sujets via sources gratuites : flux RSS de la niche, Reddit (RSS public),
Google Trends (flux RSS officiel « Trending now »). Dédoublonnage contre l'historique."""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import feedparser
import requests

from . import db, log
from .config import load

L = log.get("topics")
UA = {"User-Agent": "Mozilla/5.0 (compatible; shorts-autopilot/1.0; RSS reader)"}
STOP = set("""a an the of to in on for and or with from by is are was be this that it as at
le la les un une des de du et ou en au aux pour par sur dans est sont ce cette qui que""".split())


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def topic_key(title: str) -> str:
    return " ".join(sorted(tokens(title)))


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / max(1, min(len(ta), len(tb))) if ta and tb else 0.0


def _fetch_feed(url: str) -> list:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        return feedparser.parse(r.content).entries
    except Exception as e:
        L.warning("Flux indisponible %s : %s", url, e)
        return []


def _entry_time(e) -> datetime:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime.fromtimestamp(time.mktime(t), timezone.utc) if t else datetime.now(timezone.utc)


def categorize(text: str, categories: dict[str, list[str]]) -> str | None:
    low = f" {text.lower()} "
    best, hits = None, 0
    for cat, words in categories.items():
        n = sum(1 for w in words if w.lower() in low)
        if n > hits:
            best, hits = cat, n
    return best


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and len(data.strip()) > 40:
            self.out.append(data.strip())


def fetch_article_text(url: str, limit: int = 6000) -> str:
    """Texte brut de l'article source : sert de base factuelle au script et au fact-check."""
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        p = _Text()
        p.feed(r.text)
        return " ".join(p.out)[:limit]
    except Exception as e:
        L.info("Article non récupéré (%s) : %s", url, e)
        return ""


def recent_titles(days: int) -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return [r["topic_title"] for r in db.query(
        "SELECT topic_title FROM videos WHERE created_at > ? AND status != 'failed'", (since,))]


def is_duplicate(title: str, history: list[str], threshold: float) -> bool:
    return any(similarity(title, h) >= threshold for h in history)


def candidates() -> list[dict]:
    """Liste triée des sujets candidats (meilleur score d'abord)."""
    cfg = load()
    niche, tcfg = cfg["niche"], cfg["topics"]
    cats = niche["categories"]
    now = datetime.now(timezone.utc)
    items: list[dict] = []

    feeds = [(u, "rss", 1.0) for u in niche.get("rss_feeds", [])]
    feeds += [(f"https://www.reddit.com/r/{s}/top/.rss?t=day", "reddit", 0.9)
              for s in niche.get("subreddits", [])]
    for url, kind, weight in feeds:
        for e in _fetch_feed(url)[:25]:
            title = _clean(e.get("title", ""))
            summary = _clean(e.get("summary", "") or (e.get("content") or [{}])[0].get("value", ""))
            age_h = (now - _entry_time(e)).total_seconds() / 3600
            if not title or age_h > tcfg["max_age_hours"]:
                continue
            items.append({"title": title, "summary": summary[:1500], "url": e.get("link", ""),
                          "source": kind, "weight": weight, "age_h": age_h})

    # Google Trends : sert de bonus de pertinence (un sujet RSS qui est aussi en tendance monte)
    trending: list[str] = []
    geo = niche.get("trends_geo")
    if geo:
        trending = [_clean(e.get("title", "")) for e in
                    _fetch_feed(f"https://trends.google.com/trending/rss?geo={geo}")]

    weights = {r["value"]: r["mean"] for r in db.query(
        "SELECT value, mean FROM arms WHERE dimension = 'category'")}
    history = recent_titles(tcfg["dedupe_days"])
    banned = [b.lower() for b in niche.get("banned_keywords", [])]
    out, seen = [], []
    for it in items:
        text = f"{it['title']} {it['summary']}"
        cat = categorize(text, cats)
        if not cat or any(b in text.lower() for b in banned):
            continue  # hors niche ou sujet à risque (démonétisation / désinformation)
        if is_duplicate(it["title"], history + seen, tcfg["dedupe_threshold"]):
            continue
        seen.append(it["title"])
        freshness = max(0.0, 1 - it["age_h"] / tcfg["max_age_hours"])
        trend = 0.3 if any(similarity(it["title"], t) >= 0.5 for t in trending) else 0.0
        learned = weights.get(cat, 0.5)  # 0..1, appris des stats (voir learn.py)
        it.update(category=cat, grounded=True,
                  score=it["weight"] * (0.5 + freshness) + trend + learned)
        out.append(it)

    out.sort(key=lambda x: x["score"], reverse=True)
    L.info("%d sujets d'actualité retenus (sur %d entrées)", len(out), len(items))
    return out


def evergreen() -> list[dict]:
    """Sujets intemporels de la niche (repli si l'actualité est pauvre + mix éditorial)."""
    cfg = load()
    history = recent_titles(cfg["topics"]["evergreen_dedupe_days"])
    out = []
    for cat, titles in cfg["niche"].get("evergreen_topics", {}).items():
        for t in titles:
            if not is_duplicate(t, history, 0.8):
                out.append({"title": t, "summary": "", "url": "", "source": "evergreen",
                            "category": cat, "grounded": False, "score": 0.0})
    return out
