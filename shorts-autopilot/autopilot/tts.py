"""Voix off open-source, 100 % locale et sur CPU : Kokoro (défaut) ou Piper.

Chaque segment du script est synthétisé séparément : on connaît donc exactement
le début et la fin de chaque segment (calage des plans B-roll et des sous-titres).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

from . import log
from .config import MODELS_DIR, load

L = log.get("tts")
KOKORO_FILES = {
    "kokoro-v1.0.int8.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_kokoro = None


def _download(url: str, dest: Path) -> Path:
    if not dest.exists():
        L.info("Téléchargement du modèle %s (une seule fois)…", dest.name)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.rename(dest)
    return dest


def _kokoro_engine():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        paths = [_download(u, MODELS_DIR / n) for n, u in KOKORO_FILES.items()]
        _kokoro = Kokoro(str(paths[0]), str(paths[1]))
    return _kokoro


def _synth_kokoro(text: str, voice: str, speed: float, lang: str) -> tuple[np.ndarray, int]:
    samples, sr = _kokoro_engine().create(text, voice=voice, speed=speed, lang=lang)
    return np.asarray(samples, dtype=np.float32), sr


def _synth_piper(text: str, voice: str, speed: float, lang: str) -> tuple[np.ndarray, int]:
    # voice = ex. "en_US-ryan-high" ou "fr_FR-siwis-medium" (catalogue rhasspy/piper-voices)
    loc, name, quality = voice.split("-")
    rel = f"{loc[:2]}/{loc}/{name}/{quality}/{voice}.onnx"
    model = _download(f"{PIPER_BASE}/{rel}", MODELS_DIR / f"{voice}.onnx")
    _download(f"{PIPER_BASE}/{rel}.json", MODELS_DIR / f"{voice}.onnx.json")
    out = MODELS_DIR / "_piper_tmp.wav"
    subprocess.run(["piper", "--model", str(model), "--length_scale", f"{1 / speed:.2f}",
                    "--output_file", str(out)], input=text.encode(), check=True,
                   capture_output=True)
    data, sr = sf.read(out, dtype="float32")
    return data, sr


def _trim(x: np.ndarray, sr: int, thresh: float = 0.01) -> np.ndarray:
    """Coupe les silences de début/fin pour un rythme serré entre segments."""
    idx = np.where(np.abs(x) > thresh)[0]
    if not len(idx):
        return x
    pad = int(0.03 * sr)
    return x[max(0, idx[0] - pad): idx[-1] + pad]


def synthesize(segments: list[str], voice: str, out_wav: Path) -> list[dict]:
    """Écrit out_wav et renvoie [{text, start, end}] en secondes."""
    cfg = load()
    t, niche = cfg["tts"], cfg["niche"]
    synth = _synth_piper if t["engine"] == "piper" else _synth_kokoro
    gap = t["gap_seconds"]
    chunks, timeline, cursor, sr = [], [], 0.0, 24000
    for i, text in enumerate(segments):
        audio, sr = synth(text, voice, t["speed"], niche["tts_lang"])
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = _trim(audio, sr)
        dur = len(audio) / sr
        timeline.append({"text": text, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
        chunks.append(audio)
        cursor += dur
        if i < len(segments) - 1:
            chunks.append(np.zeros(int(gap * sr), dtype=np.float32))
            cursor += gap
    full = np.concatenate(chunks)
    peak = float(np.max(np.abs(full))) or 1.0
    sf.write(out_wav, full / peak * 0.95, sr, subtype="PCM_16")
    L.info("Voix off : %.1fs (%s, %s)", cursor, t["engine"], voice)
    return timeline
