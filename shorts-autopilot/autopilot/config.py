"""Chargement de la configuration : config/config.yaml + config/niches/<niche>.yaml + .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(os.environ.get("AUTOPILOT_ROOT", Path(__file__).resolve().parent.parent))
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
CACHE_DIR = DATA_DIR / "cache"
MODELS_DIR = Path(os.environ.get("MODELS_DIR", DATA_DIR / "models"))
ASSETS_DIR = ROOT / "assets"

for _d in (DATA_DIR, OUTPUT_DIR, CACHE_DIR, MODELS_DIR, DATA_DIR / "logs"):
    _d.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    """Config globale fusionnée avec la niche active (clé `niche`)."""
    cfg_path = Path(env("CONFIG_FILE") or ROOT / "config" / "config.yaml")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    niche_name = env("NICHE") or cfg["niche"]
    niche_path = cfg_path.parent / "niches" / f"{niche_name}.yaml"
    niche = yaml.safe_load(niche_path.read_text(encoding="utf-8"))
    niche["name"] = niche_name
    # La niche peut surcharger n'importe quelle section globale via `overrides:`
    cfg = _deep_merge(cfg, niche.pop("overrides", {}) or {})
    cfg["niche"] = niche
    # MODE dans .env prime sur le YAML : "test" (défaut) ou "live"
    cfg["mode"] = (env("MODE") or cfg.get("mode", "test")).lower()
    return cfg


def is_live() -> bool:
    return load()["mode"] == "live"
