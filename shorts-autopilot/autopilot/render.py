"""Montage FFmpeg : 9:16 1080x1920 30 i/s, coupes rapides, zooms/panoramiques,
sous-titres incrustés, voix normalisée, musique à bas volume avec ducking automatique.

Deux passes : 1) chaque plan est recadré/animé et encodé ; 2) concaténation, étalonnage,
sous-titres et mixage audio. Tout tourne sur CPU (PC ou Oracle Cloud ARM sans GPU).
"""
from __future__ import annotations

import json
import math
import random
import subprocess
from pathlib import Path

from . import log
from .config import ASSETS_DIR, load

L = log.get("render")
FPS, W, H = 30, 1080, 1920


def run(cmd: list[str], cwd: Path | None = None) -> None:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué : {p.stderr[-800:]}")


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                          "-show_streams", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def _motion(kind: str, frames: int) -> str:
    d = frames / FPS
    if kind == "zoom_in":  # sur-échantillonnage ×1,5 pour un zoom fluide, sans tremblement
        return (f"scale=1620:2880,zoompan=z='1+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}")
    if kind == "zoom_out":
        return (f"scale=1620:2880,zoompan=z='1.12-0.12*on/{frames}':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}")
    if kind == "pan_left":
        return f"scale=1210:2152,crop={W}:{H}:x='(iw-ow)*(1-t/{d:.3f})':y='(ih-oh)/2'"
    if kind == "pan_right":
        return f"scale=1210:2152,crop={W}:{H}:x='(iw-ow)*t/{d:.3f}':y='(ih-oh)/2'"
    if kind == "pan_up":
        return f"scale=1210:2152,crop={W}:{H}:x='(iw-ow)/2':y='(ih-oh)*(1-t/{d:.3f})'"
    return "null"


def plan_shots(timeline: list[dict], total: float, max_shot: float) -> list[dict]:
    """Découpe chaque segment du script en plans ≤ max_shot. Bornes calées à l'image près."""
    shots = []
    for i, seg in enumerate(timeline):
        start = 0.0 if i == 0 else seg["start"]
        end = timeline[i + 1]["start"] if i + 1 < len(timeline) else total
        n = max(1, math.ceil((end - start) / max_shot))
        if (end - start) / n < 1.0:
            n = max(1, int((end - start) // 1.0))
        for k in range(n):
            f0 = round((start + (end - start) * k / n) * FPS)
            f1 = round((start + (end - start) * (k + 1) / n) * FPS)
            if f1 > f0:
                shots.append({"seg": i, "frames": f1 - f0})
    return shots


def render_shot(clip: Path, frames: int, motion: str, out: Path) -> None:
    need = frames / FPS
    clip_dur = duration(clip)
    offset = random.uniform(0, clip_dur - need - 0.2) if clip_dur > need + 0.5 else 0.0
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"{_motion(motion, frames)},setsar=1,format=yuv420p")
    run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-ss", f"{offset:.2f}",
         "-i", str(clip), "-frames:v", str(frames), "-vf", vf, "-an", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "17", "-r", str(FPS), str(out)])


def pick_music() -> Path | None:
    cfg = load()["music"]
    if not cfg["enabled"]:
        return None
    tracks = [p for p in (ASSETS_DIR / "music").glob("*")
              if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac")]
    return random.choice(tracks) if tracks else None


def compose(shot_files: list[Path], voice: Path, subs: Path, tpl: dict, total: float,
            music: Path | None, out: Path) -> None:
    work = subs.parent
    concat = work / "shots.txt"
    concat.write_text("".join(f"file '{p.name}'\n" for p in shot_files), encoding="utf-8")
    mcfg = load()["music"]

    inputs = ["-f", "concat", "-safe", "0", "-i", concat.name, "-i", str(voice)]
    vchain = f"[0:v]{tpl['grade']},ass={subs.name}[vs]"
    if tpl["progress_bar"]:
        vchain += (f";color=c={tpl['progress_bar']}:s={W}x10:r={FPS}[bar];"
                   f"[vs][bar]overlay=x='-W+W*t/{total:.3f}':y=0:shortest=1[v]")
    else:
        vchain += ";[vs]null[v]"
    achain = "[1:a]aresample=48000,loudnorm=I=-15:TP=-1.5:LRA=11,apad=pad_dur=1"
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fade_out = max(0.0, total - 1.2)
        achain += (",asplit[vo][sc];"
                   f"[2:a]aresample=48000,volume={mcfg['volume']},afade=t=in:d=0.8,"
                   f"afade=t=out:st={fade_out:.2f}:d=1.2[m];"
                   "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[md];"
                   "[vo][md]amix=inputs=2:normalize=0:duration=first[a]")
    else:
        achain += "[a]"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{vchain};{achain}",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", str(out)], cwd=work)
    L.info("Vidéo rendue : %s", out.name)
