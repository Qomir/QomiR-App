"""Écriture du script (hook, structure rétention, CTA) + garde-fous factuels.

Deux passes LLM : 1) rédaction en JSON strict, 2) vérification indépendante des faits
contre le texte source. Plus un contrôle déterministe : tout chiffre prononcé doit
figurer dans la source (anti-hallucination, crucial en finance).
"""
from __future__ import annotations

import re

from . import llm, log
from .config import load

L = log.get("script")

# Styles de hook qui tournent (dimension apprise par le bandit)
HOOK_STYLES = {
    "question": "Open with a sharp question the viewer genuinely wants answered.",
    "number": "Open with the single most striking number or fact from the source.",
    "contrarian": "Open by challenging a common belief, then immediately justify it with a fact.",
    "stakes": "Open with what the viewer concretely gains or loses (time, money, risk).",
    "curiosity": "Open with a curiosity gap: tease the surprising outcome without revealing it yet.",
    "direct": "Open by naming the audience and the payoff: 'If you X, here is Y'.",
}

# Formats éditoriaux qui tournent (structure différente = contenu non répétitif)
FORMATS = {
    "news_explainer": "Structure: what happened -> why it matters -> what it means for the viewer.",
    "list": "Structure: a numbered list of 3 concrete points, each one standalone and useful.",
    "myth_fact": "Structure: state a widespread myth -> debunk it with facts -> the correct takeaway.",
    "how_to": "Structure: a problem -> 3 actionable steps the viewer can apply today.",
    "deep_fact": "Structure: one surprising fact -> the mechanism behind it -> a practical consequence.",
    "comparison": "Structure: option A vs option B -> the key difference -> who should pick which.",
}

SYSTEM = """You are a senior short-form video scriptwriter and a rigorous fact-checker.
You write for vertical videos (YouTube Shorts, TikTok, Reels). Rules you never break:
- Only state facts supported by the SOURCE (or, when no source is given, only
  well-established, uncontroversial facts). Never invent numbers, names, dates or quotes.
- No clickbait that the video does not pay off. No financial promises, no guaranteed
  returns, no personalised investment/medical/legal advice. No fear-mongering.
- Add your own angle: explain, contextualise, give a takeaway. Never just paraphrase.
- Spoken style: short sentences, concrete words, second person, no emojis, no hashtags
  and no stage directions inside spoken text. Write numbers the way they are spoken.
- Output valid JSON only."""


def _prompt(topic: dict, source_text: str, fmt: str, hook: str, avoid_openers: list[str]) -> str:
    cfg = load()
    niche, s = cfg["niche"], cfg["script"]
    lo, hi = s["min_words"], s["max_words"]
    src = (f"SOURCE (the only allowed basis for facts):\nTitle: {topic['title']}\n"
           f"Summary: {topic['summary']}\nArticle extract: {source_text or '(none)'}\n"
           if topic["grounded"] else
           f"TOPIC (evergreen, no source): {topic['title']}\nUse only well-established facts. "
           "Do NOT cite precise statistics, prices, dates or percentages.\n")
    return f"""Write a {niche['language_name']} voice-over script for a {niche['label']} channel.
Audience: {niche['audience']}.
Channel angle (keep this editorial voice): {niche['angle']}

{src}
FORMAT: {FORMATS[fmt]}
HOOK STYLE: {HOOK_STYLES[hook]} The hook must land in under 2 seconds (max 12 words).
Do not start like these recent videos: {avoid_openers or 'n/a'}.

RETENTION: every segment must make the next one necessary (open loops, 'but', 'here is
the catch'). No filler, no greeting, no 'in this video'. Final segment: one-line takeaway
plus this call to action idea, rephrased naturally: "{niche['cta']}".
LENGTH: {lo}-{hi} spoken words in total, 6 to 10 segments, 1-2 sentences per segment.

Return JSON with exactly these keys:
{{
 "title": "platform title, max 70 chars, {niche['language_name']}, no hashtags",
 "headline": "on-screen headline, max 5 words",
 "segments": [{{"text": "spoken text (first segment = the hook)",
               "visual": "2-4 word ENGLISH stock-footage search query, concrete and filmable",
               "keywords": ["1-2 words from this text to highlight in subtitles"]}}],
 "description": "2 sentences, {niche['language_name']}, plain and useful",
 "hashtags": ["5 relevant hashtags without #"],
 "claims": [{{"claim": "each factual claim you make", "evidence": "verbatim quote from SOURCE"}}]
}}"""


def narration(script: dict) -> str:
    return " ".join(seg["text"].strip() for seg in script["segments"])


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,.]*", text)}


def validate(script: dict, topic: dict, source_text: str) -> list[str]:
    """Contrôles déterministes. Renvoie la liste des problèmes (vide = OK)."""
    cfg = load()
    s, niche = cfg["script"], cfg["niche"]
    issues = []
    if not isinstance(script, dict):
        return ["la réponse n'est pas un objet JSON"]
    segs = script.get("segments") or []
    if not (5 <= len(segs) <= 12):
        issues.append(f"{len(segs)} segments (attendu 6-10)")
    if not isinstance(segs, list) or not segs or \
            any(not isinstance(x, dict) or not isinstance(x.get("text"), str) or not x["text"].strip()
                for x in segs):
        return issues + ["segments absents, vides ou mal formés"]
    text = narration(script)
    words = len(text.split())
    if not (s["min_words"] * 0.85 <= words <= s["max_words"] * 1.1):
        issues.append(f"{words} mots (attendu {s['min_words']}-{s['max_words']})")
    if len(segs[0]["text"].split()) > 16:
        issues.append("hook trop long (> 16 mots)")
    if not script.get("title"):
        issues.append("titre manquant")
    low = text.lower()
    for phrase in niche.get("forbidden_phrases", []):
        if phrase.lower() in low:
            issues.append(f"formulation interdite : « {phrase} »")
    if re.search(r"[#@]|https?://|\[|\]|\*", text):
        issues.append("caractères non prononçables dans le texte parlé")
    src_nums = _numbers(f"{topic['title']} {topic['summary']} {source_text}")
    for n in _numbers(text):
        if topic["grounded"]:
            if n not in src_nums:
                issues.append(f"chiffre « {n} » absent de la source")
        elif not (n.isdigit() and int(n) <= 10):
            issues.append(f"chiffre précis « {n} » dans un sujet sans source")
    return issues


def fact_check(script: dict, topic: dict, source_text: str) -> list[str]:
    """Seconde passe LLM, à froid, qui ne voit que la source et le script."""
    if not load()["script"]["fact_check"]:
        return []
    basis = (f"SOURCE:\n{topic['title']}\n{topic['summary']}\n{source_text}"
             if topic["grounded"] else
             "No source: accept only claims that are well-established common knowledge "
             "among experts; reject anything precise, disputed or time-sensitive.")
    res = llm.generate_json(
        "You are a strict fact-checker for a media company. Output JSON only.",
        f"""{basis}

SCRIPT:
{narration(script)}

List every factual claim in the SCRIPT that is NOT supported by the basis above, that
exaggerates it, or that is misleading, a financial promise or personalised advice.
Return JSON: {{"unsupported": ["claim ..."], "verdict": "pass" or "fail"}}""",
        temperature=0.0)
    bad = [str(x) for x in res.get("unsupported") or []]
    if res.get("verdict") == "fail" and not bad:
        bad = ["verdict fail sans détail"]
    return [f"fact-check : {b}" for b in bad]


def write(topic: dict, source_text: str, fmt: str, hook: str,
          avoid_openers: list[str]) -> dict | None:
    """Renvoie un script validé, ou None si le sujet doit être abandonné."""
    feedback = ""
    for attempt in range(load()["script"]["max_attempts"]):
        try:
            script = llm.generate_json(
                SYSTEM, _prompt(topic, source_text, fmt, hook, avoid_openers) + feedback)
        except llm.LLMError:
            raise
        except Exception as e:
            L.warning("Script illisible : %s", e)
            continue
        issues = validate(script, topic, source_text)
        if not issues:
            issues = fact_check(script, topic, source_text)
        if not issues:
            script["hashtags"] = [re.sub(r"[^\w]", "", h) for h in script.get("hashtags", [])][:5]
            return script
        L.info("Script refusé (essai %d) : %s", attempt + 1, issues)
        feedback = ("\n\nYour previous draft was REJECTED for these reasons, fix all of them "
                    "(remove any unsupported claim rather than rewording it):\n- " + "\n- ".join(issues))
    return None
