"""Templates de montage qui tournent (dimension `template` du bandit).

Chaque template change réellement le rendu : rythme de coupe, mouvements de caméra,
typo/position/couleurs des sous-titres, nombre de mots affichés, habillage (barre de
progression, titre incrusté), étalonnage. Ajoutez les vôtres ici.
Couleurs au format ASS &HBBGGRR (bleu-vert-rouge).
"""
from __future__ import annotations

import subprocess
from functools import lru_cache

YELLOW, GREEN, CYAN, RED, WHITE = "&H00E5FF", "&H66FF4D", "&HFFE04D", "&H4D4DFF", "&HFFFFFF"

TEMPLATES = {
    # Gros sous-titres centrés en capitales, coupes rapides, zooms alternés
    "bold_center": {
        "fonts": ["Montserrat ExtraBold", "Montserrat", "DejaVu Sans"], "size": 96,
        "uppercase": True, "y": 1100, "chunk_words": 2, "active": YELLOW, "keyword": YELLOW,
        "outline": 9, "box": False, "max_shot": 2.6,
        "motions": ["zoom_in", "zoom_out", "pan_left", "zoom_in", "pan_right"],
        "progress_bar": "yellow", "headline": "none",
        "grade": "eq=contrast=1.08:saturation=1.15:brightness=-0.04",
    },
    # Lecture confortable en bas d'écran, fond boîte, titre en intro, rythme posé
    "clean_lower": {
        "fonts": ["Montserrat SemiBold", "Montserrat", "DejaVu Sans"], "size": 76,
        "uppercase": False, "y": 1420, "chunk_words": 3, "active": GREEN, "keyword": WHITE,
        "outline": 4, "box": True, "max_shot": 4.0,
        "motions": ["zoom_in", "static", "pan_up", "zoom_in"],
        "progress_bar": None, "headline": "intro",
        "grade": "eq=contrast=1.03:saturation=1.05:brightness=-0.06",
    },
    # Style documentaire : titre permanent en haut, panoramiques lents, vignette
    "docu": {
        "fonts": ["Bebas Neue", "Montserrat ExtraBold", "DejaVu Sans"], "size": 100,
        "uppercase": True, "y": 1330, "chunk_words": 3, "active": CYAN, "keyword": CYAN,
        "outline": 7, "box": False, "max_shot": 4.8,
        "motions": ["pan_left", "pan_right", "zoom_out", "pan_up"],
        "progress_bar": None, "headline": "persistent",
        "grade": "eq=contrast=1.1:saturation=0.9:brightness=-0.08,vignette=PI/4.5",
    },
    # Un mot à la fois, très gros, coupes très rapides (rétention maximale)
    "one_word": {
        "fonts": ["Montserrat Black", "Montserrat ExtraBold", "DejaVu Sans"], "size": 128,
        "uppercase": True, "y": 1000, "chunk_words": 1, "active": WHITE, "keyword": RED,
        "outline": 10, "box": False, "max_shot": 2.0,
        "motions": ["zoom_in", "zoom_in", "zoom_out", "pan_right", "pan_left"],
        "progress_bar": "white", "headline": "none",
        "grade": "eq=contrast=1.12:saturation=1.2:brightness=-0.05",
    },
}


@lru_cache(maxsize=1)
def _installed_fonts() -> str:
    try:
        return subprocess.run(["fc-list", ":", "family", "style"], capture_output=True,
                              text=True, timeout=20).stdout.lower()
    except Exception:
        return ""


def resolve_font(candidates: list[str]) -> tuple[str, bool]:
    """Première police installée de la liste. Renvoie (famille ASS, gras synthétique)."""
    fonts = _installed_fonts()
    for name in candidates:
        family = name
        for style in (" ExtraBold", " SemiBold", " Black"):
            family = family.replace(style, "")
        style = name[len(family):].strip().lower()
        if family.lower() in fonts and (not style or style in fonts):
            return name, name == family  # sans graisse dédiée → on force le gras
    return "DejaVu Sans", True
