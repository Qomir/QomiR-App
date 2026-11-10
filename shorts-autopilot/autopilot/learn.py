"""Boucle d'apprentissage : bandit multi-bras (échantillonnage type Thompson) sur
les dimensions `category`, `format`, `hook_style`, `template`, `slot`.

- recompute() : transforme les stats des plateformes en récompense 0..1 par vidéo,
  puis en moyenne lissée par bras.
- choose()    : tire un bras ; favorise ce qui performe, garde de l'exploration et
  interdit de reprendre la valeur de la vidéo précédente (rotation = variété).
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from . import db, log
from .config import load

L = log.get("learn")
DIMENSIONS = ("category", "format", "hook_style", "template", "slot")
PRIOR_MEAN, PRIOR_N = 0.5, 3  # lissage bayésien : un bras peu testé reste proche de 0.5


def _ranks(values: list[float]) -> list[float]:
    """Rang centile 0..1 (robuste aux vidéos virales qui écraseraient une moyenne)."""
    if len(values) < 2:
        return [0.5] * len(values)
    order = sorted(values)
    return [order.index(v) / (len(values) - 1) for v in values]


def recompute() -> dict:
    cfg = load()["learning"]
    rows = db.query(
        """SELECT s.*, v.category, v.format, v.hook_style, v.template, v.slot
           FROM stats s JOIN videos v ON v.id = s.video_id
           WHERE v.status = 'published' ORDER BY v.created_at DESC LIMIT ?""",
        (cfg["window_videos"] * 3,))
    by_platform = defaultdict(list)
    for r in rows:
        by_platform[r["platform"]].append(r)

    rewards: dict[str, list[float]] = defaultdict(list)
    meta = {}
    for plat, rs in by_platform.items():
        views = _ranks([math.log1p(r["views"] or 0) for r in rs])
        has_ret = [r for r in rs if r["avg_view_pct"] is not None]
        ret = dict(zip([r["video_id"] for r in has_ret],
                       _ranks([r["avg_view_pct"] for r in has_ret])))
        share = _ranks([(r["shares"] or 0) / max(1, r["views"] or 0) for r in rs])
        for i, r in enumerate(rs):
            w = cfg["weights"]
            if r["video_id"] in ret:
                score = (w["views"] * views[i] + w["retention"] * ret[r["video_id"]]
                         + w["shares"] * share[i])
            else:  # plateforme sans donnée de rétention (TikTok) : on renormalise
                score = (w["views"] * views[i] + w["shares"] * share[i]) / (w["views"] + w["shares"])
            rewards[r["video_id"]].append(score)
            meta[r["video_id"]] = r

    sums = defaultdict(lambda: [0, 0.0])
    for vid, scores in rewards.items():
        reward = sum(scores) / len(scores)
        for dim in DIMENSIONS:
            val = meta[vid][dim]
            if val:
                sums[(dim, val)][0] += 1
                sums[(dim, val)][1] += reward

    db.execute("DELETE FROM arms")
    for (dim, val), (n, total) in sums.items():
        mean = (total + PRIOR_MEAN * PRIOR_N) / (n + PRIOR_N)
        db.execute("INSERT INTO arms VALUES (?, ?, ?, ?)", (dim, val, n, mean))
    L.info("Bandit recalculé sur %d vidéos", len(rewards))
    return best()


def best() -> dict:
    out = {}
    for dim in DIMENSIONS:
        rows = db.query("SELECT value, n, mean FROM arms WHERE dimension = ? AND n >= 2 "
                        "ORDER BY mean DESC LIMIT 1", (dim,))
        if rows:
            out[dim] = (rows[0]["value"], round(rows[0]["mean"], 2), rows[0]["n"])
    return out


def choose(dimension: str, options: list[str], avoid: str | None = None) -> str:
    cfg = load()["learning"]
    pool = [o for o in options if o != avoid] or list(options)
    if not cfg["enabled"] or random.random() < cfg["explore_rate"]:
        return random.choice(pool)
    arms = {r["value"]: (r["n"], r["mean"]) for r in db.query(
        "SELECT value, n, mean FROM arms WHERE dimension = ?", (dimension,))}

    def sample(opt: str) -> float:
        n, mean = arms.get(opt, (0, PRIOR_MEAN))
        return random.gauss(mean, 0.25 / math.sqrt(n + 1))  # incertitude ↓ quand n ↑

    return max(pool, key=sample)


def last_value(dimension: str) -> str | None:
    rows = db.query(f"SELECT {dimension} AS v FROM videos WHERE status != 'failed' "
                    "ORDER BY created_at DESC LIMIT 1")
    return rows[0]["v"] if rows else None
