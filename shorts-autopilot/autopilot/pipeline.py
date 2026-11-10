"""Chaîne de création complète : sujet → script vérifié → voix → sous-titres → B-roll →
montage → contrôle qualité → dossier de sortie (+ file d'attente de publication en mode live)."""
from __future__ import annotations

import json
import random
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from . import align, broll, captions, db, learn, log, notify, qc, render, script as scriptmod
from . import subtitles, topics, tts
from .config import CACHE_DIR, OUTPUT_DIR, load
from .templates import TEMPLATES

L = log.get("pipeline")

# Script de démonstration : permet de tester voix + montage + sous-titres sans aucune clé API
DEMO_TOPIC = {"title": "Why your phone battery ages (demo)", "summary": "", "url": "",
              "source": "demo", "category": "demo", "grounded": False, "score": 0}
DEMO_SCRIPT = {
    "title": "Why your phone battery ages faster than it should",
    "headline": "Battery myths",
    "segments": [
        {"text": "Your phone battery is aging faster than it should, and one habit is to blame.",
         "visual": "smartphone charging night", "keywords": ["battery", "habit"]},
        {"text": "Lithium batteries hate two things: heat, and staying completely full for hours.",
         "visual": "phone on desk close up", "keywords": ["heat", "full"]},
        {"text": "So charging overnight on a soft bed is the worst combination. The phone gets warm, and it sits at the top of its charge until morning.",
         "visual": "person sleeping phone bed", "keywords": ["overnight", "warm"]},
        {"text": "But here is the catch. You do not need to babysit the charger.",
         "visual": "charger cable plug", "keywords": ["catch"]},
        {"text": "Most recent phones include an optimized charging mode. It pauses near the top and finishes just before you wake up.",
         "visual": "phone settings screen", "keywords": ["optimized", "pauses"]},
        {"text": "Turn it on, keep the phone on a hard surface, and take off thick cases while charging.",
         "visual": "phone on wooden table", "keywords": ["hard", "cases"]},
        {"text": "Small habits, and your battery stays healthy much longer. Follow for more tech you can actually use.",
         "visual": "person smiling using phone", "keywords": ["healthy", "Follow"]},
    ],
    "description": "Heat and a full charge are what wear out lithium batteries. Here is the simple fix.",
    "hashtags": ["tech", "battery", "smartphone", "techtips", "howto"],
    "claims": [],
}


def _pick_topics() -> list[dict]:
    cfg = load()["topics"]
    news, ever = topics.candidates()[: cfg["try_top"]], topics.evergreen()
    random.shuffle(ever)
    # Mix éditorial : une part de sujets intemporels, le reste collé à l'actualité
    if ever and (not news or random.random() < cfg["evergreen_ratio"]):
        return ever[:2] + news
    return news + ever[:2]


def _recent_openers(n: int = 8) -> list[str]:
    out = []
    for r in db.query("SELECT script_json FROM videos WHERE status != 'failed' "
                      "ORDER BY created_at DESC LIMIT ?", (n,)):
        try:
            out.append(" ".join(json.loads(r["script_json"])["segments"][0]["text"].split()[:6]))
        except Exception:
            pass
    return out


def _build(video_id: str, work: Path, script: dict, tpl_name: str, voice: str) -> dict:
    """Voix, alignement, B-roll, montage, QC. Renvoie le rapport QC (+ chemins)."""
    cfg = load()
    tpl = TEMPLATES[tpl_name]
    segs = script["segments"]
    voice_wav = work / "voice.wav"
    timeline = tts.synthesize([s["text"] for s in segs], voice, voice_wav)
    voice_dur = timeline[-1]["end"]
    total = voice_dur + cfg["render"]["tail_seconds"]
    if not (cfg["qc"]["min_seconds"] <= total <= cfg["qc"]["max_seconds"]):
        return {"ok": False, "issues": [f"voix off de {total:.1f}s hors plage"], "warnings": []}

    words, ratio = align.align(voice_wav, timeline)
    shots = render.plan_shots(timeline, total, tpl["max_shot"])

    niche = cfg["niche"]
    taken: set[str] = set()
    seg_clips: dict[int, list[Path]] = {}
    for i, seg in enumerate(segs):
        need = sum(1 for s in shots if s["seg"] == i)
        queries = [seg.get("visual", ""), *random.sample(niche["fallback_visuals"],
                                                         k=min(2, len(niche["fallback_visuals"])))]
        found = broll.clips_for([q for q in queries if q], need, taken)
        seg_clips[i] = [p for _, p in found]
    n_real = sum(len(v) for v in seg_clips.values())
    if n_real == 0:
        L.warning("Aucun B-roll (clé Pexels/Pixabay absente ?) : fonds générés utilisés")

    shot_files = []
    for n, shot in enumerate(shots):
        clips = seg_clips[shot["seg"]]
        k = sum(1 for s in shots[:n] if s["seg"] == shot["seg"])
        clip = clips[k % len(clips)] if clips else broll.generated_background(
            shot["frames"] / render.FPS + 1, seed=n + hash(video_id) % 5)
        out = work / f"shot_{n:03d}.mp4"
        render.render_shot(clip, shot["frames"], tpl["motions"][n % len(tpl["motions"])], out)
        shot_files.append(out)

    keywords = {k for s in segs for k in s.get("keywords", [])}
    subs = work / "subs.ass"
    n_events = subtitles.build_ass(words, keywords, tpl, script.get("headline", ""), total, subs)
    final = work / "video.mp4"
    render.compose(shot_files, voice_wav, subs, tpl, total, render.pick_music(), final)

    n_words = sum(len(s["text"].split()) for s in segs)
    report = qc.check(final, words, n_words, n_events, ratio, voice_dur)
    report.update(video=final, broll_ids=sorted(taken), shots=len(shots), real_clips=n_real)
    return report


def produce(slot: str | None = None, scheduled_at: str | None = None,
            demo: bool = False) -> str | None:
    """Produit UNE vidéo. Renvoie son id, ou None si rien de publiable n'a pu être produit."""
    cfg = load()
    niche, mode = cfg["niche"], cfg["mode"]
    fmt = learn.choose("format", niche["formats"], avoid=learn.last_value("format"))
    hook = learn.choose("hook_style", list(scriptmod.HOOK_STYLES), avoid=learn.last_value("hook_style"))
    tpl_name = learn.choose("template", cfg["render"]["templates"], avoid=learn.last_value("template"))
    voice = random.choice(niche["voices"])

    candidates = [DEMO_TOPIC] if demo else _pick_topics()
    if not candidates:
        notify.error("veille", "Aucun sujet disponible (flux RSS injoignables ?)")
        return None

    for topic in candidates[: cfg["topics"]["try_top"] + 2]:
        video_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        work = CACHE_DIR / "work" / video_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            if demo:
                script = DEMO_SCRIPT
            else:
                source = topics.fetch_article_text(topic["url"]) if topic["url"] else ""
                script = scriptmod.write(topic, source, fmt, hook, _recent_openers())
            if not script:
                L.info("Sujet abandonné (script non validé) : %s", topic["title"])
                continue
            report = _build(video_id, work, script, tpl_name, voice)
            if not report["ok"]:
                L.warning("Vidéo rejetée par le QC : %s", report["issues"])
                continue

            out_dir = OUTPUT_DIR / ("live" if mode == "live" else "review") / video_id
            out_dir.mkdir(parents=True, exist_ok=True)
            final = out_dir / "video.mp4"
            shutil.move(str(report.pop("video")), final)
            broll.mark_used(report["broll_ids"])
            caps = captions.build(script, topic)
            meta = {"id": video_id, "topic": topic, "format": fmt, "hook_style": hook,
                    "template": tpl_name, "voice": voice, "script": script, "captions": caps,
                    "qc": report}
            (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
            status = "queued" if mode == "live" and not demo else "test"
            db.insert_video({
                "id": video_id, "created_at": db.now(), "status": status, "mode": mode,
                "topic_title": topic["title"], "topic_url": topic["url"],
                "topic_key": topics.topic_key(topic["title"]), "category": topic["category"],
                "format": fmt, "hook_style": hook, "template": tpl_name, "voice": voice,
                "slot": slot, "title": script["title"],
                "script_json": json.dumps(script, ensure_ascii=False), "path": str(final),
                "duration": report["duration"], "scheduled_at": scheduled_at or db.now(),
                "qc_json": json.dumps(report, ensure_ascii=False)})
            approval = cfg["approval"]["mode"]
            caption = (f"🎬 {'[TEST] ' if status == 'test' else ''}{script['title']}\n"
                       f"{report['duration']}s · {tpl_name} · {fmt} · hook {hook}\n"
                       f"Sujet : {topic['title']}")
            if status == "queued" and approval != "off":
                caption += ("\nPublication prévue : " + (scheduled_at or "dès que possible") +
                            ("\n⚠️ En attente de votre validation." if approval == "required"
                             else "\nSans action de votre part, elle sera publiée."))
            notify.send_video(final, caption, video_id,
                              with_buttons=status == "queued" and approval != "off")
            L.info("Vidéo prête : %s", final)
            return video_id
        except Exception as e:
            L.exception("Échec de production")
            notify.error(f"production ({topic['title'][:60]})", e)
            if "Aucun LLM disponible" in str(e):
                return None  # inutile d'essayer les autres sujets
        finally:
            shutil.rmtree(work, ignore_errors=True)
    notify.error("production", "Aucun sujet n'a passé les contrôles (script/QC) sur ce créneau.")
    return None
