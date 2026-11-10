"""Timing mot par mot des sous-titres.

Whisper (faster-whisper, CPU) transcrit la voix off avec horodatage par mot ; on recale
ensuite ces temps sur les mots EXACTS du script (Whisper peut mal orthographier un nom
ou un chiffre : on affiche toujours le texte du script, avec le timing de Whisper).
Repli sans Whisper : répartition proportionnelle à l'intérieur de chaque segment TTS.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from . import log
from .config import MODELS_DIR, load

L = log.get("align")
_model = None


def _norm(w: str) -> str:
    return re.sub(r"[^\wà-ÿ]", "", w.lower())


def proportional(timeline: list[dict]) -> list[dict]:
    """Répartit la durée de chaque segment entre ses mots (poids = longueur du mot)."""
    words = []
    for seg_idx, seg in enumerate(timeline):
        toks = seg["text"].split()
        weights = [len(_norm(t)) + 2 + (3 if t[-1] in ".,;:!?" else 0) for t in toks]
        total, cursor = sum(weights), seg["start"]
        for tok, w in zip(toks, weights):
            d = (seg["end"] - seg["start"]) * w / total
            words.append({"w": tok, "start": round(cursor, 3), "end": round(cursor + d, 3),
                          "seg": seg_idx})
            cursor += d
    return words


def _whisper_words(wav: Path, language: str) -> list[dict]:
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel(load()["subtitles"]["whisper_model"], device="cpu",
                              compute_type="int8", download_root=str(MODELS_DIR / "whisper"))
    segs, _ = _model.transcribe(str(wav), language=language, word_timestamps=True,
                                vad_filter=False, beam_size=5)
    return [{"w": w.word.strip(), "start": w.start, "end": w.end} for s in segs for w in s.words]


def align(wav: Path, timeline: list[dict]) -> tuple[list[dict], float]:
    """Renvoie (mots horodatés, taux de correspondance Whisper/script 0..1).

    Le taux sert au contrôle qualité : s'il est bas, la voix ne dit pas ce que les
    sous-titres affichent (TTS raté) et la vidéo est rejetée."""
    words = proportional(timeline)
    if not load()["subtitles"]["use_whisper"]:
        return words, 1.0
    try:
        heard = _whisper_words(wav, load()["niche"]["language"])
    except Exception as e:
        L.warning("Whisper indisponible (%s) : timing proportionnel utilisé", e)
        return words, -1.0  # -1 = synchro non vérifiée

    a, b = [_norm(w["w"]) for w in words], [_norm(h["w"]) for h in heard]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    matched = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                words[i1 + k].update(start=heard[j1 + k]["start"], end=heard[j1 + k]["end"],
                                     ok=True)
            matched += i2 - i1
        elif tag == "replace" and j2 > j1:
            # même plage audio, découpage différent (ex. « 25% » vs « twenty five percent »)
            t0, t1 = heard[j1]["start"], heard[j2 - 1]["end"]
            n = i2 - i1
            for k in range(n):
                words[i1 + k].update(start=t0 + (t1 - t0) * k / n,
                                     end=t0 + (t1 - t0) * (k + 1) / n, ok=True)
    # Sécurité : temps strictement croissants et bornés au segment TTS
    prev_end = 0.0
    for w in words:
        seg = timeline[w["seg"]]
        w["start"] = max(prev_end, min(max(w["start"], seg["start"] - 0.15), seg["end"]))
        w["end"] = max(w["start"] + 0.06, min(w["end"], seg["end"] + 0.15))
        prev_end = w["start"]
        w["start"], w["end"] = round(w["start"], 3), round(w["end"], 3)
    ratio = matched / max(1, len(words))
    L.info("Alignement Whisper : %.0f%% des mots reconnus", ratio * 100)
    return words, ratio
