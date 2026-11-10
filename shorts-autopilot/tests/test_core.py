"""Tests hors-ligne de la logique (aucune clé API, aucun réseau)."""
import random

from autopilot import align, captions, db, learn, render, script, subtitles, topics
from autopilot.config import load
from autopilot.templates import TEMPLATES

TIMELINE = [{"text": "Your phone is slow.", "start": 0.0, "end": 1.5},
            {"text": "Here is the 1 fix, and why it works.", "start": 1.62, "end": 4.4}]


def _script(words_per_seg=22, n=7, text=None):
    seg = text or " ".join(["word"] * words_per_seg)
    return {"title": "T", "headline": "H", "description": "D", "hashtags": ["a b", "#tech"],
            "segments": [{"text": "Short hook here." if i == 0 else seg, "visual": "x",
                          "keywords": []} for i in range(n)]}


def test_proportional_alignment_is_complete_and_monotonic():
    words = align.proportional(TIMELINE)
    assert [w["w"] for w in words] == " ".join(t["text"] for t in TIMELINE).split()
    assert all(a["start"] <= b["start"] for a, b in zip(words, words[1:]))
    assert words[0]["start"] == 0.0 and abs(words[-1]["end"] - 4.4) < 0.01
    assert words[4]["start"] >= 1.62  # le 2e segment ne commence pas avant sa voix


def test_whisper_timings_are_mapped_onto_script_words(monkeypatch):
    # Whisper entend « one » là où le script écrit « 1 » : le texte affiché reste celui du script
    heard = [("your", 0.1, 0.3), ("phone", 0.3, 0.7), ("is", 0.7, 0.8), ("slow", 0.8, 1.4),
             ("here", 1.7, 1.9), ("is", 1.9, 2.0), ("the", 2.0, 2.1), ("one", 2.1, 2.4),
             ("fix", 2.4, 2.8), ("and", 2.9, 3.0), ("why", 3.0, 3.3), ("it", 3.3, 3.4),
             ("works", 3.4, 4.3)]
    monkeypatch.setattr(align, "_whisper_words",
                        lambda wav, lang: [{"w": w, "start": s, "end": e} for w, s, e in heard])
    words, ratio = align.align("x.wav", TIMELINE)
    assert [w["w"] for w in words][7] == "1"
    assert abs(words[7]["start"] - 2.1) < 0.01          # timing de « one » appliqué à « 1 »
    assert abs(words[1]["start"] - 0.3) < 0.01
    assert ratio > 0.9
    assert all(a["start"] <= b["start"] for a, b in zip(words, words[1:]))


def test_ass_has_one_event_per_word_and_highlights(tmp_path):
    words = align.proportional(TIMELINE)
    for name, tpl in TEMPLATES.items():
        out = tmp_path / f"{name}.ass"
        n = subtitles.build_ass(words, {"fix"}, tpl, "Big headline", 5.0, out)
        text = out.read_text()
        assert n == len(words)
        assert text.count("Dialogue: 0,") == len(words)
        assert tpl["active"] in text or tpl["keyword"] in text
        assert ("Head,," in text) == (tpl["headline"] != "none")


def test_chunks_never_cross_sentences_or_segments():
    words = align.proportional(TIMELINE)
    for chunk in subtitles.chunk_words(words, 3):
        assert len({w["seg"] for w in chunk}) == 1
        assert all(w["w"][-1] not in ".!?" for w in chunk[:-1])


def test_shot_plan_covers_exact_frame_count():
    for max_shot in (2.0, 2.6, 4.8):
        shots = render.plan_shots(TIMELINE, 5.0, max_shot)
        assert sum(s["frames"] for s in shots) == round(5.0 * render.FPS)
        assert all(s["frames"] / render.FPS <= max_shot + 0.04 for s in shots)


def test_duplicate_topics_are_detected():
    a = "Apple announces new iPhone battery feature in iOS update"
    assert topics.is_duplicate("New iPhone battery feature announced by Apple", [a], 0.6)
    assert not topics.is_duplicate("Google launches a new Pixel camera mode", [a], 0.6)


def test_categorize_and_off_niche():
    cats = load()["niche"]["categories"]
    assert topics.categorize("OpenAI ships a new AI model", cats) == "ai"
    assert topics.categorize("Local bakery wins award", cats) is None


def test_script_rejects_numbers_missing_from_source():
    topic = {"title": "Chip maker ships 40 million units", "summary": "", "grounded": True}
    good = _script(text="The company shipped 40 million units " + " ".join(["word"] * 16))
    bad = _script(text="The company shipped 75 million units " + " ".join(["word"] * 16))
    assert script.validate(good, topic, "") == []
    assert any("75" in i for i in script.validate(bad, topic, ""))


def test_script_rejects_forbidden_promises_and_bad_length():
    topic = {"title": "t", "summary": "", "grounded": False}
    promise = _script(text="This is guaranteed to work " + " ".join(["word"] * 17))
    assert any("guaranteed" in i for i in script.validate(promise, topic, ""))
    assert any("mots" in i for i in script.validate(_script(words_per_seg=3), topic, ""))
    stats = _script(text="Exactly 37 percent of people do this " + " ".join(["word"] * 15))
    assert any("37" in i for i in script.validate(stats, topic, ""))  # pas de stat sans source


def test_captions_respect_limits_and_carry_ai_notice():
    caps = captions.build(_script(), {"url": "https://example.com/a"})
    assert len(caps["youtube"]["title"]) <= 100
    assert "https://example.com/a" in caps["youtube"]["description"]
    assert "AI" in caps["youtube"]["description"] and "AI" in caps["instagram"]["caption"]
    assert caps["tiktok"]["caption"].count("#") <= 5
    assert "ab" in caps["youtube"]["tags"]  # hashtags nettoyés


def test_bandit_learns_the_better_template():
    random.seed(1)
    db.execute("DELETE FROM videos"); db.execute("DELETE FROM stats"); db.execute("DELETE FROM arms")
    for i in range(30):
        tpl = "docu" if i % 2 else "one_word"
        db.insert_video({"id": f"v{i}", "created_at": f"2026-01-{i + 1:02d}", "status": "published",
                         "category": "ai", "format": "list", "hook_style": "question",
                         "template": tpl, "slot": "12:20", "topic_title": f"t{i}"})
        views = 50_000 + i if tpl == "docu" else 300 + i
        db.execute("INSERT INTO stats VALUES (?, 'youtube', '', ?, 0, 0, 0, ?, 0)",
                   (f"v{i}", views, 80.0 if tpl == "docu" else 30.0))
    best = learn.recompute()
    assert best["template"][0] == "docu"
    picks = [learn.choose("template", ["docu", "one_word", "bold_center"]) for _ in range(300)]
    assert picks.count("docu") > picks.count("one_word") * 2
    assert picks.count("bold_center") > 0            # l'exploration reste vivante
    assert learn.choose("template", ["docu", "one_word"], avoid="docu") == "one_word"


def test_script_write_retries_with_feedback_then_passes(monkeypatch):
    topic = {"title": "Chip maker ships 40 million units", "summary": "s", "grounded": True, "url": ""}
    bad = _script(text="The company shipped 75 million units " + " ".join(["word"] * 16))
    good = _script(text="The company shipped 40 million units " + " ".join(["word"] * 16))
    prompts, replies = [], [bad, good, {"unsupported": [], "verdict": "pass"}]
    from autopilot import llm

    def fake(system, prompt, temperature=0.8):
        prompts.append(prompt)
        return replies.pop(0)
    monkeypatch.setattr(llm, "generate_json", fake)
    out = script.write(topic, "", "list", "question", [])
    assert out is good and out["hashtags"] == ["ab", "tech"]
    assert "REJECTED" in prompts[1] and "75" in prompts[1]   # le défaut est renvoyé au LLM


def test_script_write_gives_up_when_fact_check_keeps_failing(monkeypatch):
    topic = {"title": "t", "summary": "s", "grounded": True, "url": ""}
    from autopilot import llm
    monkeypatch.setattr(llm, "generate_json", lambda s, p, temperature=0.8:
                        {"unsupported": ["x"], "verdict": "fail"} if "strict fact-checker" in s else _script())
    assert script.validate({"verdict": "x"}, topic, "") != []      # JSON inattendu : rejet propre
    assert script.validate({"segments": [{"text": None}] * 6}, topic, "") != []
    assert script.write(topic, "", "list", "question", []) is None


def _queued(tmp_path, vid, due, approval="pending"):
    import json
    d = tmp_path / vid
    d.mkdir()
    (d / "video.mp4").write_bytes(b"x")
    (d / "meta.json").write_text(json.dumps({"captions": {"youtube": {}, "instagram": {}, "tiktok": {}}}))
    db.insert_video({"id": vid, "created_at": db.now(), "status": "queued", "title": vid,
                     "path": str(d / "video.mp4"), "scheduled_at": due, "approval": approval,
                     "topic_title": vid})


def test_queue_respects_mode_schedule_and_approval(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    from autopilot import notify, publisher
    cfg = load()
    sent, calls, decisions = [], [], []
    monkeypatch.setattr(notify, "send", sent.append)
    monkeypatch.setattr(notify, "poll_decisions", lambda: decisions)
    monkeypatch.setitem(publisher.UPLOADERS, "youtube",
                        lambda p, c: calls.append(("yt", p.parent.name)) or {"remote_id": "Y1", "url": "u"})

    def ig_fail(p, c):
        raise RuntimeError("boom")
    monkeypatch.setitem(publisher.UPLOADERS, "instagram", ig_fail)
    now = datetime.now(timezone.utc)
    past, future = (now - timedelta(minutes=2)).isoformat(), (now + timedelta(hours=1)).isoformat()
    db.execute("DELETE FROM videos"); db.execute("DELETE FROM posts")
    _queued(tmp_path, "due", past)
    _queued(tmp_path, "later", future)
    _queued(tmp_path, "vetoed", past)
    decisions.append(("vetoed", "rejected"))

    status = lambda v: db.query("SELECT status FROM videos WHERE id = ?", (v,))[0]["status"]
    publisher.process_queue()                       # mode test : rien ne part
    assert calls == [] and status("due") == "queued"

    monkeypatch.setitem(cfg, "mode", "live")
    monkeypatch.setitem(cfg["approval"], "mode", "veto")
    publisher.process_queue()
    assert calls == [("yt", "due")]
    assert status("due") == "published" and status("later") == "queued" and status("vetoed") == "rejected"
    posts = {r["platform"]: r["status"] for r in db.query("SELECT * FROM posts WHERE video_id = 'due'")}
    assert posts == {"youtube": "ok", "instagram": "error"}
    publisher.process_queue()                       # pas de double publication
    assert calls == [("yt", "due")]

    monkeypatch.setitem(cfg["approval"], "mode", "required")
    _queued(tmp_path, "needs_ok", past)
    publisher.process_queue()
    assert status("needs_ok") == "queued"           # attend le clic « Publier »
    decisions[:] = [("needs_ok", "approved")]
    publisher.process_queue()
    assert status("needs_ok") == "published"
