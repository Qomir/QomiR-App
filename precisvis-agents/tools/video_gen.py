"""Génération de vidéos 9:16 (10–15 s) + incrustation des textes avec ffmpeg.

La vidéo part d'une image « packshot » validée (elle-même issue de la vraie photo produit).
Accroche dans les 2 premières secondes, démonstration, appel à l'action à la fin.
Les textes sont posés dans la zone de sécurité (ni dans les 14 % du haut, ni dans les 20 % du bas).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .http import ApiError, request
from .image_gen import GenResult, ProviderUnavailable, data_uri, download


class FalVideoProvider:
    name = "fal"

    def __init__(self, key: str | None, model: str, unit_cost: float):
        if not key:
            raise ProviderUnavailable("FAL_KEY manquant")
        self.key, self.model, self.unit_cost = key, model, unit_cost

    async def generate(self, prompt: str, start_image: Path, seconds: int, out: Path) -> GenResult:
        headers = {"Authorization": f"Key {self.key}"}
        payload = {"prompt": prompt, "image_url": data_uri(start_image), "duration": "10" if seconds >= 10 else "5",
                   "aspect_ratio": "9:16", "negative_prompt": "texte, logo, marque, déformation, doigts en trop, flou"}
        sub = request("fal", "POST", f"https://queue.fal.run/{self.model}", json=payload, headers=headers).json()
        start = time.time()
        while time.time() - start < 900:
            st = request("fal", "GET", sub["status_url"], headers=headers).json()
            if st.get("status") == "COMPLETED":
                res = request("fal", "GET", sub["response_url"], headers=headers).json()
                download(res["video"]["url"], out)
                return GenResult(out, self.model, self.name, self.unit_cost)
            if st.get("status") in ("FAILED", "ERROR"):
                raise ApiError("fal", None, str(st)[:300])
            time.sleep(8)
        raise ApiError("fal", None, "délai de génération vidéo dépassé")


class SumeVideoProvider:
    name = "sume"

    def __init__(self, ctx, url: str | None, token: str | None, model: str, unit_cost: float):
        if not url or not token:
            raise ProviderUnavailable("SUME_MCP_URL / SUME_MCP_TOKEN manquants")
        self.ctx, self.model, self.unit_cost = ctx, model, unit_cost
        self.servers = {"sume": {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {token}"}}}

    async def generate(self, prompt: str, start_image: Path, seconds: int, out: Path) -> GenResult:
        from .image_gen import SUME_SYSTEM
        image_url = self.ctx.tools.hosting.public_url(start_image)
        key = hashlib.sha1(f"{prompt}{time.time()}".encode()).hexdigest()[:24]
        instruction = (
            f"Appelle generate_video avec idempotency_key='{key}' et payload = "
            f"{{'model': '{self.model}', 'prompt': {prompt!r}, 'image_url': '{image_url}', "
            f"'aspect_ratio': '9:16', 'duration': {seconds}}}. Attends le résultat et renvoie son URL."
        )
        data = await self.ctx.llm.ask(
            "ad_visuals", instruction,
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
            mock=lambda: {"url": ""}, mcp_servers=self.servers, system=SUME_SYSTEM.replace("UNE image", "UNE vidéo")
            .replace("generate_image", "generate_video"),
            estimate_eur=0.05 + self.unit_cost, simulated_cost_eur=0.01, effort="low",
        )
        if not data.get("url"):
            raise ApiError("sume", None, "aucune URL renvoyée")
        download(data["url"], out)
        return GenResult(out, self.model, self.name, self.unit_cost)


class PlaceholderVideoProvider:
    """Simulation : lent zoom (effet Ken Burns) sur l'image de départ, encodé localement."""
    name = "placeholder"
    model = "placeholder-ffmpeg"

    async def generate(self, prompt: str, start_image: Path, seconds: int, out: Path) -> GenResult:
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = 24
        frames = seconds * fps
        vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:s=1080x1920:fps={fps},format=yuv420p")
        _ffmpeg(["-loop", "1", "-i", str(start_image), "-vf", vf, "-t", str(seconds),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(out)])
        return GenResult(out, self.model, self.name, 0.0)


def build_video_provider(ctx, name: str):
    cfg = ctx.cfg
    cost = float(cfg.get("creatives.unit_costs_eur.video", 0.6))
    if ctx.dry_run or name == "placeholder":
        return PlaceholderVideoProvider()
    if name == "fal":
        return FalVideoProvider(cfg.secret("FAL_KEY"), cfg.get("creatives.fal.video_model"), cost)
    if name == "sume":
        return SumeVideoProvider(ctx, cfg.secret("SUME_MCP_URL"), cfg.secret("SUME_MCP_TOKEN"),
                                 cfg.get("creatives.sume.video_model"), cost)
    raise ProviderUnavailable(f"fournisseur vidéo inconnu : {name}")


# -- ffmpeg ------------------------------------------------------------------------------
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffmpeg(args: list[str]) -> None:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg n'est pas installé")
    proc = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg : {proc.stderr[-400:]}")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def overlay_texts(src: Path, dest: Path, *, hook: str, cta: str, font: Path, logo: Path | None,
                  brand: dict[str, Any], safe_top: float = 0.14, safe_bottom: float = 0.20) -> Path:
    """Accroche 0–2,5 s en haut de la zone sûre, CTA sur les 3 dernières secondes, logo permanent."""
    dur = probe_duration(src)
    charcoal = brand["palette"]["charcoal"].lstrip("#")
    bone = brand["palette"]["bone"].lstrip("#")
    y_hook = int(1920 * safe_top + 40)
    y_cta = int(1920 * (1 - safe_bottom) - 220)
    common = f"fontfile='{font}':fontsize=64:fontcolor=0x{charcoal}:box=1:boxcolor=0x{bone}@0.85:boxborderw=28:x=(w-text_w)/2"
    vf = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          f"drawtext={common}:y={y_hook}:text='{_escape(hook)}':enable='between(t,0,2.5)',"
          f"drawtext={common}:y={y_cta}:text='{_escape(cta)}':enable='gte(t,{max(0.0, dur - 3):.2f})'[v]")
    inputs = ["-i", str(src)]
    if logo and logo.exists():
        inputs += ["-i", str(logo)]
        lw = int(1080 * brand["logo"].get("width_ratio", 0.18))
        margin = int(1080 * brand["logo"].get("margin_ratio", 0.04))
        vf += (f";[1:v]scale={lw}:-1[lg];[v][lg]overlay=x=W-w-{margin}:y={int(1920 * (1 - safe_bottom))}-h-{margin}[v]")
    _ffmpeg([*inputs, "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)])
    return dest


def probe_duration(path: Path) -> float:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 10.0


def extract_frames(src: Path, out_dir: Path, times: list[float]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, t in enumerate(times):
        dest = out_dir / f"frame_{i}.jpg"
        _ffmpeg(["-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dest)])
        frames.append(dest)
    return frames
