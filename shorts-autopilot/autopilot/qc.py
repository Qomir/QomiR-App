"""Contrôle qualité automatique avant toute publication. Une vidéo qui échoue n'est jamais publiée."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import log
from .config import load
from .render import probe

L = log.get("qc")


def _audio_levels(path: Path) -> tuple[float, float]:
    """(volume moyen en dB, plus long silence en secondes)."""
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af",
                        "volumedetect,silencedetect=noise=-40dB:d=0.5", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    silences = [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", p.stderr)]
    return (float(mean.group(1)) if mean else -99.0), max(silences, default=0.0)


def check(video: Path, words: list[dict], n_script_words: int, n_sub_events: int,
          match_ratio: float, voice_duration: float) -> dict:
    cfg = load()["qc"]
    issues, warnings = [], []
    info = probe(video)
    dur = float(info["format"]["duration"])
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

    if not (cfg["min_seconds"] <= dur <= cfg["max_seconds"]):
        issues.append(f"durée {dur:.1f}s hors plage {cfg['min_seconds']}-{cfg['max_seconds']}s")
    if not v or (v["width"], v["height"]) != (1080, 1920):
        issues.append("vidéo absente ou pas en 1080x1920")
    if not a:
        issues.append("piste audio absente")
    else:
        mean, silence = _audio_levels(video)
        if mean < cfg["min_mean_volume_db"]:
            issues.append(f"audio trop faible ({mean:.1f} dB)")
        if silence > cfg["max_silence_seconds"]:
            issues.append(f"silence de {silence:.1f}s détecté")

    # Sous-titres : complets, ordonnés, calés sur la voix
    if len(words) != n_script_words or n_sub_events != n_script_words:
        issues.append(f"sous-titres incomplets ({n_sub_events}/{n_script_words} mots)")
    if any(w2["start"] < w1["start"] for w1, w2 in zip(words, words[1:])):
        issues.append("sous-titres non chronologiques")
    if words and abs(words[-1]["end"] - voice_duration) > 1.5:
        issues.append("fin des sous-titres décalée par rapport à la voix")
    if match_ratio < 0:
        warnings.append("synchro non vérifiée par Whisper (timing proportionnel)")
    elif match_ratio < cfg["min_whisper_match"]:
        issues.append(f"voix ≠ sous-titres ({match_ratio:.0%} de mots reconnus)")

    size_mb = video.stat().st_size / 1e6
    if size_mb > cfg["max_size_mb"]:
        issues.append(f"fichier trop lourd ({size_mb:.0f} Mo)")

    report = {"ok": not issues, "issues": issues, "warnings": warnings,
              "duration": round(dur, 2), "size_mb": round(size_mb, 1),
              "whisper_match": round(match_ratio, 2)}
    L.info("QC %s : %s", "OK" if report["ok"] else "ÉCHEC", issues or warnings or "RAS")
    return report
