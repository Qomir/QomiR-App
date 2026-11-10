"""Sous-titres dynamiques mot par mot (style TikTok) au format ASS, incrustés par FFmpeg/libass.

Les mots sont groupés en petits blocs ; le mot prononcé est mis en couleur à l'instant
exact où il est dit, les mots-clés du script restent en couleur d'accent.
"""
from __future__ import annotations

import re
from pathlib import Path

from .templates import resolve_font

W, H = 1080, 1920


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _display(word: str, upper: bool) -> str:
    w = re.sub(r"[.,;:«»\"“”()]+$|^[«\"“(]+", "", word).replace("{", "").replace("}", "")
    return w.upper() if upper else w


def chunk_words(words: list[dict], max_words: int, max_chars: int = 18) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        too_long = sum(len(x["w"]) for x in cur) + len(w["w"]) > max_chars
        if cur and (len(cur) >= max_words or too_long or cur[-1]["seg"] != w["seg"]
                    or cur[-1]["w"][-1] in ".!?"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[dict], keywords: set[str], tpl: dict, headline: str,
              total: float, out: Path) -> int:
    """Écrit le fichier .ass. Renvoie le nombre d'événements de sous-titres."""
    font, fake_bold = resolve_font(tpl["fonts"])
    bold = -1 if fake_bold else 0
    border = 3 if tpl["box"] else 1
    back = "&H96000000" if tpl["box"] else "&H00000000"
    head_size = int(tpl["size"] * 0.62)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{tpl['size']},&H00FFFFFF,&H00FFFFFF,{back if tpl['box'] else '&H00000000'},{back},{bold},0,0,0,100,100,0,0,{border},{tpl['outline']},{0 if tpl['box'] else 3},5,60,60,0,1
Style: Head,{font},{head_size},&H00FFFFFF,&H00FFFFFF,&HC8000000,&HC8000000,{bold},0,0,0,100,100,1,0,3,14,0,8,70,70,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if headline and tpl["headline"] != "none":
        end = total if tpl["headline"] == "persistent" else min(3.2, total)
        fade = r"{\fad(150,300)}" if tpl["headline"] == "intro" else r"{\fad(150,0)}"
        text = _display(headline, True).replace("\n", " ")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end)},Head,,0,0,0,,{fade}{text}")

    kw = {re.sub(r"[^\wà-ÿ]", "", k.lower()) for k in keywords}
    safe_w = W - 120                                   # marge de sécurité des interfaces
    per_char = tpl["size"] * 0.62                      # largeur moyenne d'un caractère gras
    chunks = chunk_words(words, tpl["chunk_words"], max_chars=max(8, int(safe_w / per_char) - 1))
    n_events = 0
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        for wi, w in enumerate(chunk):
            start = w["start"]
            end = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else min(w["end"] + 0.25, next_start)
            if end - start < 0.04:
                end = start + 0.04
            parts = []
            for xi, x in enumerate(chunk):
                txt = _display(x["w"], tpl["uppercase"])
                if not txt:
                    continue
                is_kw = re.sub(r"[^\wà-ÿ]", "", x["w"].lower()) in kw
                if xi == wi:
                    # template « un mot » : le mot-clé prend la couleur d'accent quand il est dit
                    col = tpl["keyword"] if is_kw and tpl["chunk_words"] == 1 else tpl["active"]
                    grow = "" if tpl["box"] else r"\fscx108\fscy108"
                    parts.append(rf"{{\c{col}&{grow}}}{txt}{{\c&HFFFFFF&\fscx100\fscy100}}")
                elif is_kw:
                    parts.append(rf"{{\c{tpl['keyword']}&}}{txt}{{\c&HFFFFFF&}}")
                else:
                    parts.append(txt)
            pop = r"\fscx82\fscy82\t(0,90,\fscx100\fscy100)" if wi == 0 and not tpl["box"] else ""
            width = sum(len(_display(x["w"], True)) + 1 for x in chunk) * per_char
            fit = rf"\fs{int(tpl['size'] * safe_w / width)}" if width > safe_w else ""
            tag = rf"{{\an5\pos({W // 2},{tpl['y']}){fit}{pop}}}"
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{tag}{' '.join(parts)}")
            n_events += 1
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return n_events
