"""Génération d'images — fournisseur choisi dans config.yaml (creatives.image_provider).

- sume        : via le serveur MCP Sume, piloté par le Claude Agent SDK (SUME_MCP_URL + SUME_MCP_TOKEN)
- fal         : fal.ai (Flux Kontext, édition à partir de la vraie photo produit)
- placeholder : image locale générée sans IA (mode simulation)

Toutes les images partent des vraies photos du produit (brand/product_photos/) en référence.
La scène est générée SANS texte : le texte et le logo sont ajoutés ensuite par core/compose.py.
"""
from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from .http import ApiError, request


@dataclass
class GenResult:
    path: Path
    model: str
    provider: str
    cost_eur: float


class ProviderUnavailable(Exception):
    pass


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(request("download", "GET", url, timeout=300).content)
    return dest


# --------------------------------------------------------------------------------------
class FalImageProvider:
    name = "fal"

    def __init__(self, key: str | None, model: str, unit_cost: float):
        if not key:
            raise ProviderUnavailable("FAL_KEY manquant")
        self.key, self.model, self.unit_cost = key, model, unit_cost

    def _run(self, model: str, payload: dict[str, Any], timeout_s: int = 600) -> dict[str, Any]:
        headers = {"Authorization": f"Key {self.key}"}
        sub = request("fal", "POST", f"https://queue.fal.run/{model}", json=payload, headers=headers).json()
        start = time.time()
        while time.time() - start < timeout_s:
            st = request("fal", "GET", sub["status_url"], headers=headers).json()
            if st.get("status") == "COMPLETED":
                return request("fal", "GET", sub["response_url"], headers=headers).json()
            if st.get("status") in ("FAILED", "ERROR"):
                raise ApiError("fal", None, str(st)[:300])
            time.sleep(4)
        raise ApiError("fal", None, "délai de génération dépassé")

    async def generate(self, prompt: str, references: list[Path], aspect: str, out: Path) -> GenResult:
        payload: dict[str, Any] = {"prompt": prompt, "aspect_ratio": aspect, "output_format": "png",
                                   "num_images": 1, "safety_tolerance": "2"}
        if references:
            payload["image_url"] = data_uri(references[0])
        res = self._run(self.model, payload)
        download(res["images"][0]["url"], out)
        return GenResult(out, self.model, self.name, self.unit_cost)


# --------------------------------------------------------------------------------------
SUME_SYSTEM = """Tu es un opérateur technique. Tu génères exactement UNE image avec l'outil
generate_image du serveur Sume, tu attends la fin du job (jobs_wait avec include_results=true,
en relançant tant que timed_out est vrai), puis tu renvoies uniquement l'URL du résultat
dans le JSON demandé. Tu n'utilises aucun autre outil payant et tu ne génères rien d'autre."""


class SumeImageProvider:
    """Sume n'a pas d'API REST publique documentée : on passe par son serveur MCP.

    Nécessite dans .env : SUME_MCP_URL (adresse du serveur MCP Sume) et SUME_MCP_TOKEN.
    """
    name = "sume"

    def __init__(self, ctx, url: str | None, token: str | None, model: str, unit_cost: float):
        if not url or not token:
            raise ProviderUnavailable("SUME_MCP_URL / SUME_MCP_TOKEN manquants")
        self.ctx, self.model, self.unit_cost = ctx, model, unit_cost
        self.servers = {"sume": {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {token}"}}}

    async def generate(self, prompt: str, references: list[Path], aspect: str, out: Path) -> GenResult:
        ref_urls = [self.ctx.tools.hosting.public_url(p) for p in references[:2]]
        key = hashlib.sha1(f"{prompt}{aspect}{time.time()}".encode()).hexdigest()[:24]
        instruction = (
            f"Appelle generate_image avec idempotency_key='{key}' et payload = "
            f"{{'model': '{self.model}', 'prompt': {prompt!r}, 'aspect_ratio': '{aspect}', "
            f"'image_urls': {ref_urls!r}, 'n': 1}}. Attends le résultat et renvoie son URL."
        )
        data = await self.ctx.llm.ask(
            "ad_visuals", instruction,
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
            mock=lambda: {"url": ""}, mcp_servers=self.servers, system=SUME_SYSTEM,
            estimate_eur=0.05 + self.unit_cost, simulated_cost_eur=0.01, effort="low",
        )
        if not data.get("url"):
            raise ApiError("sume", None, "aucune URL renvoyée")
        download(data["url"], out)
        return GenResult(out, self.model, self.name, self.unit_cost)


# --------------------------------------------------------------------------------------
class PlaceholderImageProvider:
    """Mode simulation : scène « atelier » dessinée localement, avec la vraie photo produit
    incrustée si elle existe dans brand/product_photos/."""
    name = "placeholder"
    model = "placeholder-local"

    def __init__(self, brand: dict[str, Any]):
        self.brand = brand

    async def generate(self, prompt: str, references: list[Path], aspect: str, out: Path) -> GenResult:
        w, h = {"1:1": (1080, 1080), "9:16": (1080, 1920), "3:4": (1080, 1440)}.get(aspect, (1080, 1080))
        rnd = random.Random(hashlib.md5((prompt + aspect).encode()).hexdigest())
        img = Image.new("RGB", (w, h), (226, 220, 209))
        d = ImageDraw.Draw(img)
        # mur clair + lumière de fenêtre
        for y in range(int(h * 0.55)):
            t = y / (h * 0.55)
            d.line([(0, y), (w, y)], fill=(int(236 - 18 * t), int(231 - 18 * t), int(222 - 20 * t)))
        # établi en bois : planches + veinage
        top = int(h * 0.55)
        for i, y0 in enumerate(range(top, h, max(40, h // 9))):
            base = (176 - i * 6, 138 - i * 5, 91 - i * 4)
            d.rectangle([0, y0, w, y0 + h // 9], fill=base)
            for _ in range(14):
                yy = y0 + rnd.randint(4, h // 9 - 4)
                d.line([(0, yy), (w, yy + rnd.randint(-6, 6))], fill=tuple(max(0, c - 18) for c in base), width=2)
        img = img.filter(ImageFilter.GaussianBlur(1.2))
        d = ImageDraw.Draw(img)
        # produit : vraie photo si disponible, sinon silhouette stylisée
        cx, cy = w // 2 + rnd.randint(-60, 60), int(h * 0.62)
        if references:
            ph = Image.open(references[0]).convert("RGB")
            ph.thumbnail((int(w * 0.62), int(h * 0.42)))
            img.paste(ph, (cx - ph.width // 2, cy - ph.height // 2))
        else:
            body_w, body_h = int(w * 0.11), int(h * 0.34 if aspect == "9:16" else h * 0.42)
            d.ellipse([cx - body_w // 2 + 14, cy + body_h // 2 - 10, cx + body_w // 2 + 40, cy + body_h // 2 + 30], fill=(120, 92, 60))
            d.rounded_rectangle([cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2],
                                radius=body_w // 2, fill=(64, 66, 70))
            d.rounded_rectangle([cx - body_w // 2 + 8, cy - body_h // 2 + 30, cx - body_w // 2 + 22, cy + body_h // 2 - 30],
                                radius=6, fill=(150, 155, 162))
            d.rectangle([cx - 6, cy + body_h // 2, cx + 6, cy + body_h // 2 + int(h * 0.06)], fill=(170, 174, 180))
            d.ellipse([cx - 10, cy - body_h // 2 + 18, cx + 10, cy - body_h // 2 + 38], fill=(255, 240, 200))
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "PNG")
        return GenResult(out, self.model, self.name, 0.0)


def build_image_provider(ctx, name: str):
    cfg = ctx.cfg
    cost = float(cfg.get("creatives.unit_costs_eur.image", 0.06))
    if ctx.dry_run or name == "placeholder":
        return PlaceholderImageProvider(ctx.brand)
    if name == "fal":
        return FalImageProvider(cfg.secret("FAL_KEY"), cfg.get("creatives.fal.image_model"), cost)
    if name == "sume":
        return SumeImageProvider(ctx, cfg.secret("SUME_MCP_URL"), cfg.secret("SUME_MCP_TOKEN"),
                                 cfg.get("creatives.sume.image_model"), cost)
    raise ProviderUnavailable(f"fournisseur d'images inconnu : {name}")


def image_bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, quality=92)
    return buf.getvalue()
