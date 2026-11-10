"""Ligne de commande.  python -m autopilot <commande>

  doctor                 vérifie l'installation, les clés, les flux RSS et les connexions
  generate [-n 10]       fabrique N vidéos maintenant dans output/ (rien n'est publié en mode test)
  generate --demo        vidéo de démonstration sans aucune clé API (teste voix + montage)
  run                    lance le planificateur (c'est ce que fait Docker)
  auth youtube|tiktok|instagram   connexion OAuth à une plateforme
  publish <id> [-p youtube]       publie manuellement une vidéo déjà générée
  stats                  collecte les stats maintenant et recalcule l'apprentissage
  report                 envoie le bilan maintenant
"""
from __future__ import annotations

import argparse
import shutil
import sys

from . import log
from .config import env, load

L = log.get("cli")


def doctor() -> int:
    import requests
    cfg = load()
    niche = cfg["niche"]
    ok = True

    def line(good, label, hint=""):
        nonlocal ok
        print(("✅ " if good else "❌ ") + label + (f"  → {hint}" if hint and not good else ""))
        return good

    print(f"Niche : {niche['name']} · mode : {cfg['mode']} · validation : {cfg['approval']['mode']}\n")
    ok &= line(bool(shutil.which("ffmpeg")), "FFmpeg installé")
    from .templates import TEMPLATES, resolve_font
    for name, t in TEMPLATES.items():
        font, _ = resolve_font(t["fonts"])
        line(font != "DejaVu Sans", f"Police du template {name} : {font}",
             "police de secours utilisée (normal hors Docker)")
    llm_ok = bool(env("GEMINI_API_KEY")) or "ollama" in cfg["llm"]["providers"]
    ok &= line(llm_ok, "LLM configuré (GEMINI_API_KEY ou Ollama)", "ajoutez GEMINI_API_KEY dans .env")
    ok &= line(bool(env("PEXELS_API_KEY") or env("PIXABAY_API_KEY")), "Clé B-roll (Pexels/Pixabay)",
               "sans clé : fonds dégradés uniquement")
    line(bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID")), "Telegram configuré",
         "notifications désactivées")
    from .config import ASSETS_DIR
    line(any((ASSETS_DIR / "music").glob("*.mp3")) or any((ASSETS_DIR / "music").glob("*.wav")),
         "Musique dans assets/music/", "vidéos sans musique")
    print("\nFlux RSS :")
    for url in niche["rss_feeds"]:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            line(r.status_code == 200, url, f"HTTP {r.status_code} : retirez ou remplacez ce flux")
        except Exception as e:
            line(False, url, str(e)[:80])
    print("\nPlateformes :")
    from .publish import oauth
    for plat, c in cfg["platforms"].items():
        if not c.get("enabled"):
            print(f"➖ {plat} désactivé")
            continue
        try:
            {"youtube": oauth.youtube_token, "tiktok": oauth.tiktok_token,
             "instagram": oauth.instagram_token}[plat]()
            line(True, f"{plat} connecté")
        except Exception as e:
            line(False, f"{plat}", str(e)[:120])
            if cfg["mode"] == "live":
                ok = False
    print("\n" + ("Tout est prêt." if ok else "Des points bloquants restent à corriger (❌)."))
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="autopilot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    g = sub.add_parser("generate")
    g.add_argument("-n", "--count", type=int, default=1)
    g.add_argument("--demo", action="store_true")
    sub.add_parser("run")
    a = sub.add_parser("auth")
    a.add_argument("platform", choices=["youtube", "tiktok", "instagram"])
    pb = sub.add_parser("publish")
    pb.add_argument("video_id")
    pb.add_argument("-p", "--platform", action="append")
    sub.add_parser("stats")
    sub.add_parser("report")
    args = p.parse_args()

    if args.cmd == "doctor":
        return doctor()
    if args.cmd == "generate":
        from . import pipeline
        made = [v for v in (pipeline.produce(demo=args.demo) for _ in range(args.count)) if v]
        print(f"\n{len(made)}/{args.count} vidéo(s) générée(s) : {made}")
        return 0 if made else 1
    if args.cmd == "run":
        from . import scheduler
        scheduler.run()
    elif args.cmd == "auth":
        from .publish import oauth
        getattr(oauth, f"{args.platform}_login")()
    elif args.cmd == "publish":
        from . import publisher
        return 0 if publisher.publish_video(args.video_id, args.platform) else 1
    elif args.cmd == "stats":
        from . import stats
        stats.collect()
    elif args.cmd == "report":
        from . import stats
        print(stats.daily_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
