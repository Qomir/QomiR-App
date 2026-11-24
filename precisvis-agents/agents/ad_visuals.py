"""Agent Visuels IA (prioritaire) — créas pour Facebook, Instagram et TikTok (publication organique).

Chaque jour : N concepts d'images statiques (6 par défaut) déclinés dans tous les formats,
et M vidéos 9:16 (2 par défaut) de 10–15 s.

Chaîne pour chaque image :
1. Claude rédige le brief (scène, angle, titre ≤ 7 mots) à partir des angles de la veille
   et des créas gagnantes de l'analytics ;
2. le générateur d'images crée la scène SANS texte en partant de la vraie photo produit ;
3. le code pose titre + logo selon la charte et les zones de sécurité (core/compose.py) ;
4. Claude analyse le résultat (vision) avec la grille qualité ; score < 7/10 → régénération
   avec les remarques (3 essais max), sinon la créa est rejetée et le motif journalisé.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from core.compose import compose, thumbnail
from core.guardrails import BudgetExceeded
from tools.image_gen import ProviderUnavailable, build_image_provider
from tools.video_gen import build_video_provider, extract_frames, ffmpeg_available, overlay_texts

from .base import AgentReport, BaseAgent

CREATIVE_TYPES_FR = {
    "packshot_atelier": "Packshot atelier",
    "mise_en_situation": "Mise en situation",
    "avant_apres": "Avant / après",
    "comparatif": "Comparatif manuel vs PrecisVis",
    "gros_plan_detail": "Gros plan détail",
}

BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["images", "videos"],
    "properties": {
        "images": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["concept", "angle", "headline", "scene_prompt"],
                   "properties": {"concept": {"type": "string"}, "angle": {"type": "string"},
                                  "headline": {"type": "string"}, "scene_prompt": {"type": "string"}}}},
        "videos": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["concept", "angle", "hook", "cta", "motion_prompt", "start_from"],
                   "properties": {"concept": {"type": "string"}, "angle": {"type": "string"}, "hook": {"type": "string"},
                                  "cta": {"type": "string"}, "motion_prompt": {"type": "string"},
                                  "start_from": {"type": "integer"}}}},
    },
}

QA_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["fidelite_produit", "lisibilite", "charte", "absence_deformation", "conformite", "score", "problemes"],
    "properties": {
        "fidelite_produit": {"type": "number"}, "lisibilite": {"type": "number"}, "charte": {"type": "number"},
        "absence_deformation": {"type": "number"}, "conformite": {"type": "number"},
        "score": {"type": "number"}, "problemes": {"type": "array", "items": {"type": "string"}},
    },
}

NEGATIVE = ("No text, no letters, no watermark, no third-party brand logos (no Apple, Samsung, Nintendo, Sony, DJI, Rolex…), "
            "no recognizable real person, realistic hands with five fingers, the screwdriver must stay IDENTICAL to the reference photo "
            "(same shape, color, buttons, bits), do not invent features.")


class AdVisualsAgent(BaseAgent):
    name = "ad_visuals"
    label = "Visuels IA"
    spends_money = True

    async def run(self) -> AgentReport:
        ctx, cfg = self.ctx, self.ctx.cfg
        self.out_root = cfg.output_dir / "creatives" / ctx.day
        self.refs = sorted(p for p in (cfg.brand_dir / "product_photos").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
        if not self.refs and not ctx.dry_run:
            raise RuntimeError("Aucune vraie photo produit dans brand/product_photos/ : génération bloquée "
                               "(les visuels doivent rester fidèles au produit livré).")
        self.min_score = float(cfg.get("creatives.min_quality_score", 7))
        self.max_attempts = int(cfg.get("creatives.max_attempts", 3))
        self.formats = cfg.get("creatives.formats", [])
        self.safe = cfg.get("creatives.safe_zone_9x16", {"top": 0.14, "bottom": 0.20})

        briefs = await self._briefs()
        images_ok, rejected, cost = [], [], 0.0
        videos_ok, videos_ko = [], []
        try:
            for i, brief in enumerate(briefs["images"]):
                res = await self._produce_image(i + 1, brief)
                cost += res["cost_eur"]
                (images_ok if res["status"] == "ok" else rejected).append(res)

            for j, vb in enumerate(briefs["videos"]):
                start = next((r for r in images_ok if r["index"] == vb.get("start_from")),
                             images_ok[j % len(images_ok)] if images_ok else None)
                if not start:
                    videos_ko.append({"reason": "aucune image de départ valide"})
                    continue
                res = await self._produce_video(j + 1, vb, start)
                cost += res["cost_eur"]
                (videos_ok if res["status"] == "ok" else videos_ko).append(res)
        except BudgetExceeded as exc:   # on garde ce qui est déjà produit et on s'arrête proprement
            self.bullet(f"Production interrompue : {exc}")
            self.todo("erreur", "Plafond de coût API atteint pendant la production des visuels", str(exc),
                      ref=f"budget:{ctx.day}:{self.name}")

        n_files = sum(len(r["files"]) for r in images_ok) + sum(len(r["files"]) for r in videos_ok)
        self.bullet(f"{len(images_ok)} image(s) + {len(videos_ok)} vidéo(s) générées et validées ({n_files} fichiers, tous formats).")
        for r in rejected + videos_ko:
            self.bullet(f"Rejetée : {r.get('concept_label', 'vidéo')} — {r.get('reason')}")
        retried = sum(1 for r in images_ok + videos_ok if r["attempts"] > 1)
        if retried:
            self.bullet(f"{retried} créa(s) régénérée(s) après contrôle qualité (score < {self.min_score:g}/10).")
        if images_ok:
            best = max(images_ok, key=lambda r: r["score"])
            self.bullet(f"Meilleure image : {best['concept_label']} « {best['headline']} » ({best['score']:.1f}/10).")
        self.bullet(f"Coût génération : {cost:.2f} €.")
        ctx.db.publish_insight(day=ctx.day, source=self.name, topic="creatives_ready",
                               payload=[r["id"] for r in images_ok + videos_ok])
        self.report.data = {"images": len(images_ok), "videos": len(videos_ok), "rejected": len(rejected) + len(videos_ko)}
        return self.report

    # ------------------------------------------------------------------------------
    async def _briefs(self) -> dict[str, Any]:
        ctx, cfg = self.ctx, self.ctx.cfg
        n_img, n_vid = int(cfg.get("creatives.daily_images", 6)), int(cfg.get("creatives.daily_videos", 2))
        types = cfg.get("creatives.creative_types", list(CREATIVE_TYPES_FR))
        offset = ctx.date.toordinal() % len(types)
        plan = [types[(offset + k) % len(types)] for k in range(n_img)]
        winners = ctx.db.latest_insight("winners") or []
        angles = ctx.db.latest_insight("angles") or []
        prompt = (
            self.prompt_context()
            + f"\nStyle photo de la marque : {ctx.brand['photo_style']}\n"
            + f"Angles de la veille : {json.dumps(angles, ensure_ascii=False)}\n"
            + f"Créas gagnantes récentes (à décliner en variantes) : {json.dumps(winners, ensure_ascii=False)}\n"
            + f"Plan du jour pour les {n_img} images : {plan}. Si des gagnantes existent, remplace les derniers concepts par "
            f"des variantes de ces gagnantes (même angle, autre scène).\n"
            "Pour chaque image : concept (une valeur du plan), angle, headline (texte sur l'image en français, 7 mots MAXIMUM, "
            "lisible sur mobile, sans urgence ni promesse fausse), scene_prompt (en anglais, description précise de la scène "
            "pour le générateur d'images, avec le tournevis de la photo de référence ; appareils réparés génériques sans logo).\n"
            f"Pour {n_vid} vidéos 9:16 de 10 s : hook (≤ 7 mots, affiché dans les 2 premières secondes), cta (≤ 5 mots), "
            "motion_prompt (en anglais : mouvement de caméra et démonstration du geste), start_from (numéro 1..N de l'image de départ)."
        )
        briefs = await ctx.llm.ask(self.name, prompt, BRIEF_SCHEMA, mock=lambda: _mock_briefs(plan, n_vid),
                                   estimate_eur=0.12, simulated_cost_eur=0.07)
        briefs["images"] = briefs["images"][:n_img]
        briefs["videos"] = briefs["videos"][:n_vid]
        self.action("briefs", {"images": len(briefs["images"]), "videos": len(briefs["videos"])})
        return briefs

    def _providers(self, kind: str):
        cfg = self.ctx.cfg
        build = build_image_provider if kind == "image" else build_video_provider
        names = [cfg.get(f"creatives.{kind}_provider", "fal"), cfg.get("creatives.fallback_provider", "fal")]
        seen, out = set(), []
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            try:
                out.append(build(self.ctx, n))
            except ProviderUnavailable as exc:
                self.action(f"{kind}_provider_unavailable", {"provider": n}, status="skipped", error=str(exc))
        if not out:
            raise RuntimeError(f"Aucun fournisseur {kind} disponible (voir .env)")
        return out

    async def _generate(self, kind: str, *args):
        last: Exception | None = None
        unit = float(self.ctx.cfg.get(f"creatives.unit_costs_eur.{kind}", 0.06))
        for prov in self._providers(kind):
            self.ctx.guard.authorize_spend(unit, f"génération {kind}")
            try:
                res = await prov.generate(*args)
            except Exception as exc:  # bascule vers le fournisseur de secours
                last = exc
                self.action(f"{kind}_generation_failed", {"provider": prov.name}, status="error", error=str(exc))
                continue
            self.ctx.db.add_cost(day=self.ctx.day, agent=self.name, provider=res.provider, kind=kind,
                                 amount_eur=res.cost_eur if not self.ctx.dry_run else unit, dry_run=self.ctx.dry_run)
            return res
        raise RuntimeError(f"génération {kind} impossible : {last}")

    async def _produce_image(self, index: int, brief: dict[str, Any]) -> dict[str, Any]:
        ctx = self.ctx
        cid = f"{ctx.day}-img{index:02d}"
        concept = brief["concept"]
        label = CREATIVE_TYPES_FR.get(concept, concept)
        try:
            ctx.guard.check_on_image_text(brief["headline"])
        except Exception as exc:
            brief["headline"] = " ".join(brief["headline"].split()[:7])
            self.action("headline_fixed", {"id": cid, "reason": str(exc)})
        files: dict[str, str] = {}
        feedback, score, attempts, cost, model = "", 0.0, 0, 0.0, ""
        masters: dict[str, Path] = {}
        prompt_used = ""
        for master_aspect in ("1:1", "9:16"):
            fmts = [f for f in self.formats if (f["ratio"] == "9:16") == (master_aspect == "9:16")]
            passed = False
            for attempt in range(1, self.max_attempts + 1):
                attempts = max(attempts, attempt)
                prompt_used = f"{brief['scene_prompt']} {ctx.brand['photo_style']} {NEGATIVE}" + (f" Fix: {feedback}" if feedback else "")
                master = self.out_root / "_masters" / f"{cid}_{master_aspect.replace(':', 'x')}_a{attempt}.png"
                gen = await self._generate("image", prompt_used, self.refs, master_aspect, master)
                cost += gen.cost_eur if not ctx.dry_run else float(ctx.cfg.get("creatives.unit_costs_eur.image", 0.06))
                model = gen.model
                composed = self._compose_all(cid, gen.path, fmts, brief["headline"])
                check_path = Path(next(iter(composed.values())))
                qa = await self._quality(check_path, f"{label} — {brief['headline']}", cid, master_aspect, attempt)
                score = qa["score"]
                self.action("quality_check", {"id": cid, "format": master_aspect, "attempt": attempt, **qa})
                if score >= self.min_score:
                    files.update(composed)
                    masters[master_aspect] = gen.path
                    passed = True
                    break
                feedback = "; ".join(qa["problemes"])
            if not passed:
                self._quarantine(cid)
                reason = f"score {score:.1f}/10 après {self.max_attempts} essais ({feedback or 'qualité insuffisante'})"
                self._save_db(cid, brief, "image", files, prompt_used, model, cost, score, attempts, "rejected", reason, masters)
                return {"id": cid, "index": index, "status": "rejected", "reason": reason, "concept_label": label,
                        "cost_eur": cost, "attempts": attempts, "files": {}}
        self._save_db(cid, brief, "image", files, prompt_used, model, cost, score, attempts, "ok", None, masters)
        self._sidecars(cid, files, {"prompt": prompt_used, "model": model, "cost_eur": round(cost, 3), "score": score,
                                    "angle": brief["angle"], "concept": concept, "headline": brief["headline"]})
        thumbnail(Path(files.get("instagram/4x5") or next(iter(files.values()))), self.out_root / "_thumbs" / f"{cid}.jpg")
        return {"id": cid, "index": index, "status": "ok", "score": score, "concept_label": label,
                "headline": brief["headline"], "cost_eur": cost, "attempts": attempts, "files": files,
                "master_9x16": str(masters.get("9:16", ""))}

    def _compose_all(self, cid: str, master: Path, fmts: list[dict[str, Any]], headline: str) -> dict[str, str]:
        scene = Image.open(master)
        out = {}
        for f in fmts:
            img, _ = compose(scene, width=f["width"], height=f["height"], ratio=f["ratio"], headline=headline,
                             brand=self.ctx.brand, root=self.ctx.cfg.root, safe_zone=self.safe)
            key = f"{f['platform']}/{f['ratio'].replace(':', 'x')}"
            dest = self.out_root / f["platform"] / f["ratio"].replace(":", "x") / f"{cid}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest, "JPEG", quality=92)
            out[key] = str(dest)
        return out

    async def _quality(self, path: Path, what: str, cid: str, aspect: str, attempt: int) -> dict[str, Any]:
        ctx = self.ctx
        ref = f" Photo de référence du vrai produit : {self.refs[0].resolve()}." if self.refs else ""
        prompt = (f"Lis l'image {path.resolve()} (créa « {what} », format {aspect}).{ref}\n"
                  "Note chaque critère sur 10 : fidelite_produit (identique au produit réel, aucune fonctionnalité inventée), "
                  "lisibilite (texte lisible sur mobile), charte (style atelier, palette neutre, logo en bas à droite), "
                  "absence_deformation (mains, doigts, objets, texte parasite), conformite (aucun logo de marque tierce, "
                  "aucune personne réelle, aucun faux avis). score = le plus bas des critères si l'un est < 5, sinon la moyenne. "
                  "Liste les problèmes concrets à corriger.")
        return await ctx.llm.ask(self.name, prompt, QA_SCHEMA, tools=["Read"], cwd=ctx.cfg.root,
                                 mock=lambda: _mock_qa(cid, aspect, attempt), estimate_eur=0.06, simulated_cost_eur=0.03,
                                 effort="low")

    async def _produce_video(self, index: int, vb: dict[str, Any], start: dict[str, Any]) -> dict[str, Any]:
        ctx = self.ctx
        vid = f"{ctx.day}-vid{index:02d}"
        if not ffmpeg_available():
            return {"id": vid, "status": "rejected", "reason": "ffmpeg absent", "cost_eur": 0, "attempts": 0, "files": {}}
        start_img = Path(start["master_9x16"]) if start.get("master_9x16") else Path(next(iter(start["files"].values())))
        seconds = int(ctx.cfg.get("creatives.video_seconds", 10))
        cost, feedback, score = 0.0, "", 0.0
        font = ctx.cfg.root / ctx.brand["typography"]["headline_font"]
        logo = ctx.cfg.root / ctx.brand["logo"]["path"]
        for attempt in range(1, self.max_attempts + 1):
            raw = self.out_root / "_masters" / f"{vid}_a{attempt}_raw.mp4"
            prompt = vb["motion_prompt"] + " " + NEGATIVE + (f" Fix: {feedback}" if feedback else "")
            gen = await self._generate("video", prompt, start_img, seconds, raw)
            cost += gen.cost_eur if not ctx.dry_run else float(ctx.cfg.get("creatives.unit_costs_eur.video", 0.6))
            final = self.out_root / "tiktok" / "9x16" / f"{vid}.mp4"
            final.parent.mkdir(parents=True, exist_ok=True)
            overlay_texts(raw, final, hook=" ".join(vb["hook"].split()[:7]), cta=" ".join(vb["cta"].split()[:5]),
                          font=font, logo=logo, brand=ctx.brand, safe_top=self.safe["top"], safe_bottom=self.safe["bottom"])
            frames = extract_frames(final, self.out_root / "_masters" / f"{vid}_frames", [1.0, seconds / 2, seconds - 1.5])
            qa = await self._quality(frames[1], f"vidéo « {vb['hook']} » (image extraite au milieu)", vid, "9:16", attempt)
            score = qa["score"]
            self.action("quality_check", {"id": vid, "attempt": attempt, **qa})
            if score >= self.min_score:
                ig = self.out_root / "instagram" / "9x16" / f"{vid}.mp4"
                ig.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(final, ig)
                files = {"tiktok/9x16": str(final), "instagram/9x16": str(ig)}
                thumbnail(frames[0], self.out_root / "_thumbs" / f"{vid}.jpg")
                self._save_db(vid, {**vb, "headline": vb["hook"]}, "video", files, prompt, gen.model, cost, score,
                              attempt, "ok", None, {}, parent=start["id"])
                self._sidecars(vid, files, {"prompt": prompt, "model": gen.model, "cost_eur": round(cost, 3), "score": score,
                                            "angle": vb["angle"], "concept": vb["concept"], "hook": vb["hook"], "cta": vb["cta"],
                                            "start_image": start["id"]})
                return {"id": vid, "status": "ok", "score": score, "cost_eur": cost, "attempts": attempt, "files": files}
            feedback = "; ".join(qa["problemes"])
            final.unlink(missing_ok=True)
        reason = f"vidéo rejetée : score {score:.1f}/10 ({feedback})"
        return {"id": vid, "status": "rejected", "reason": reason, "cost_eur": cost, "attempts": self.max_attempts, "files": {}}

    def _quarantine(self, cid: str) -> None:
        """Une créa rejetée ne doit jamais rester dans les dossiers publiables."""
        dest = self.out_root / "_rejected"
        dest.mkdir(parents=True, exist_ok=True)
        for f in self.out_root.glob(f"*/*/{cid}.*"):
            if f.parts[-3].startswith("_"):
                continue
            f.rename(dest / f"{f.parts[-3]}_{f.parts[-2]}_{f.name}")

    def _save_db(self, cid, brief, kind, files, prompt, model, cost, score, attempts, status, reason, masters, parent=None):
        self.ctx.db.insert("creatives", {
            "id": cid, "day": self.ctx.day, "concept": brief["concept"], "angle": brief.get("angle"),
            "headline": brief.get("headline"), "kind": kind, "master_path": json.dumps({k: str(v) for k, v in masters.items()}),
            "files": files, "prompt": prompt, "model": model, "cost_eur": round(cost, 4), "score": score,
            "attempts": attempts, "status": status, "rejection_reason": reason, "parent_id": parent,
            "dry_run": int(self.ctx.dry_run)})

    def _sidecars(self, cid: str, files: dict[str, str], meta: dict[str, Any]) -> None:
        for key, path in files.items():
            Path(path).with_suffix(".json").write_text(json.dumps({"id": cid, "format": key, **meta}, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")


# -- simulation ----------------------------------------------------------------------------
_MOCK_HEADLINES = {
    "packshot_atelier": ("La précision, sans forcer.", "Geste d'artisan", "Oak workbench, soft window light, the screwdriver lying diagonally next to neatly arranged bits."),
    "mise_en_situation": ("Ta manette grince ? Ouvre-la.", "Réparer soi-même", "Hands opening a generic game controller with the screwdriver on a wooden workbench."),
    "avant_apres": ("Vis de 1 mm. Réglée.", "Vis minuscule", "Split composition: tiny screw struggling with tweezers on the left, the screwdriver tightening it effortlessly on the right."),
    "comparatif": ("5 minutes ou 5 secondes ?", "Manuel vs électrique", "Classic manual precision screwdriver vs the electric screwdriver side by side on brushed steel."),
    "gros_plan_detail": ("Zéro vis abîmée.", "Couple réglable", "Macro shot of the bit tip with LED light illuminating a tiny watch screw."),
}


def _mock_briefs(plan: list[str], n_vid: int) -> dict[str, Any]:
    images = []
    for c in plan:
        h, angle, scene = _MOCK_HEADLINES.get(c, _MOCK_HEADLINES["packshot_atelier"])
        images.append({"concept": c, "angle": angle, "headline": h, "scene_prompt": scene})
    videos = [
        {"concept": "mise_en_situation", "angle": "Réparer soi-même", "hook": "Cette vis fait 1 mm.", "cta": "Lien en bio",
         "motion_prompt": "Slow push-in, the screwdriver unscrews a tiny screw from a generic smartphone, LED turns on.", "start_from": 2},
        {"concept": "packshot_atelier", "angle": "Geste d'artisan", "hook": "Fini les vis qui foirent.", "cta": "Découvre PrecisVis",
         "motion_prompt": "Orbit around the screwdriver on the oak workbench, bits gently rotating.", "start_from": 1},
    ]
    return {"images": images, "videos": videos[:n_vid]}


def _mock_qa(cid: str, aspect: str, attempt: int) -> dict[str, Any]:
    import random
    r = random.Random(f"{cid}{aspect}{attempt}")
    if cid.endswith("img03") and aspect == "9:16" and attempt == 1:
        return {"fidelite_produit": 8, "lisibilite": 4.5, "charte": 7, "absence_deformation": 6, "conformite": 9,
                "score": 4.5, "problemes": ["texte illisible sur le fond clair", "reflet parasite sur le boîtier"]}
    if cid.endswith("img06") and aspect == "1:1":
        return {"fidelite_produit": 5.5, "lisibilite": 8, "charte": 7, "absence_deformation": 4, "conformite": 8,
                "score": 4.0, "problemes": ["main à six doigts", "embout différent du produit réel"]}
    vals = [round(r.uniform(7.2, 9.4), 1) for _ in range(5)]
    return {"fidelite_produit": vals[0], "lisibilite": vals[1], "charte": vals[2], "absence_deformation": vals[3],
            "conformite": vals[4], "score": round(sum(vals) / 5, 1), "problemes": []}
