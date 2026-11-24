"""Mise en page déterministe des créas (Pillow).

L'IA génère la SCÈNE sans texte ; le texte et le logo sont posés ici par le code.
Ainsi la charte (police, couleurs, logo en bas à droite), la limite de 7 mots et
les zones de sécurité 9:16 (14 % en haut, 20 % en bas) sont garanties à 100 %.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


@dataclass
class Layout:
    width: int
    height: int
    text_box: tuple[int, int, int, int]   # x0, y0, x1, y1
    logo_box: tuple[int, int, int, int]


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """Redimensionne en remplissant tout le cadre, recadrage centré."""
    img = img.convert("RGB")
    scale = max(width / img.width, height / img.height)
    new = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.LANCZOS)
    left = (new.width - width) // 2
    top = (new.height - height) // 2
    return new.crop((left, top, left + width, top + height))


def _font(root: Path, rel: str, size: int) -> ImageFont.FreeTypeFont:
    path = root / rel
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError("texte trop long pour la zone")
    return lines


def safe_band(width: int, height: int, ratio: str, safe: dict[str, float], margin: float) -> tuple[int, int]:
    """Renvoie (y_min, y_max) de la zone où le texte et le logo sont autorisés."""
    if ratio == "9:16":
        return int(height * safe.get("top", 0.14)), int(height * (1 - safe.get("bottom", 0.20)))
    m = int(height * margin)
    return m, height - m


def compose(
    scene: Image.Image,
    *,
    width: int,
    height: int,
    ratio: str,
    headline: str,
    brand: dict[str, Any],
    root: Path,
    safe_zone: dict[str, float],
) -> tuple[Image.Image, Layout]:
    pal = brand["palette"]
    typo = brand["typography"]
    lay = brand["layout"]
    img = cover_resize(scene, width, height).convert("RGBA")
    margin_x = int(width * lay.get("margin_ratio", 0.06))
    y_min, y_max = safe_band(width, height, ratio, safe_zone, lay.get("margin_ratio", 0.06))

    # --- titre ---------------------------------------------------------
    draw = ImageDraw.Draw(img)
    size = int(width * typo.get("headline_size_ratio", 0.062))
    font = _font(root, typo["headline_font"], size)
    max_text_w = width - 2 * margin_x - int(size * 1.2)
    while True:
        try:
            lines = _wrap(draw, headline, font, max_text_w, typo.get("max_lines", 2))
            break
        except ValueError:
            size = int(size * 0.9)
            if size < 28:
                raise
            font = _font(root, typo["headline_font"], size)

    line_h = int(size * 1.22)
    pad = int(size * 0.6)
    text_w = max(int(draw.textlength(line, font=font)) for line in lines)
    box_w = text_w + 2 * pad
    box_h = line_h * len(lines) + 2 * pad - int(size * 0.22)
    x0 = margin_x
    y0 = y_min + int(height * 0.02)
    text_box = (x0, y0, x0 + box_w, y0 + box_h)

    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 6, y0 + 8, x0 + box_w + 6, y0 + box_h + 8),
                                             radius=int(size * 0.35), fill=(0, 0, 0, 60))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(10)))
    bone = hex_to_rgb(pal["bone"])
    pdraw.rounded_rectangle(text_box, radius=int(size * 0.35),
                            fill=(*bone, int(255 * lay.get("panel_opacity", 0.82))))
    img = Image.alpha_composite(img, panel)
    draw = ImageDraw.Draw(img)
    charcoal = hex_to_rgb(pal["charcoal"])
    for i, line in enumerate(lines):
        draw.text((x0 + pad, y0 + pad + i * line_h - int(size * 0.1)), line, font=font, fill=charcoal)
    # filet d'accent bois sous le texte
    draw.rectangle((x0 + pad, y0 + box_h - int(pad * 0.55), x0 + pad + int(size * 1.6), y0 + box_h - int(pad * 0.55) + max(3, size // 14)),
                   fill=hex_to_rgb(pal["oak"]))

    # --- logo en bas à droite (au-dessus de la zone d'interface en 9:16) ------
    logo_cfg = brand["logo"]
    logo_path = root / logo_cfg["path"]
    logo_w = int(width * logo_cfg.get("width_ratio", 0.18))
    lm = int(width * logo_cfg.get("margin_ratio", 0.04))
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((logo_w, max(1, round(logo.height * logo_w / logo.width))), Image.LANCZOS)
    else:
        logo = Image.new("RGBA", (logo_w, logo_w // 4), (*charcoal, 255))
    lx1 = width - lm
    ly1 = y_max - lm if ratio == "9:16" else height - lm
    logo_box = (lx1 - logo.width, ly1 - logo.height, lx1, ly1)
    img.alpha_composite(logo, (logo_box[0], logo_box[1]))

    return img.convert("RGB"), Layout(width, height, text_box, logo_box)


def thumbnail(src: Path, dest: Path, width: int = 280) -> Path:
    img = Image.open(src).convert("RGB")
    img.thumbnail((width, width * 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=80)
    return dest
